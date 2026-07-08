from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .contracts import (
    AgentBridgePublicationIndexV0,
    AgentExecutionReadinessPublicationV0,
    AgentMarketRuntimeSnapshotV0,
    DirectionImpulseFeaturesV0,
    ExhaustionLateEntryFeaturesV0,
    LiquidityMicrostructureFeaturesV0,
    PublishedFeatureFamiliesV0,
    PublishedMarketSymbolV0,
    RegimeStructureFeaturesV0,
    VolatilityCostFeaturesV0,
)
from .execution_readiness import build_execution_readiness_snapshot
from .parity_governance import FilterParityHistoryStore


MARKET_FILENAME = "market_snapshot_v0.json"
READINESS_FILENAME = "execution_readiness_v0.json"
INDEX_FILENAME = "publication_index_v0.json"
MAX_PUBLICATION_BYTES = 256 * 1024
MAX_SYMBOLS = 12
T = TypeVar("T", bound=BaseModel)


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _payload(event: Any) -> Dict[str, Any]:
    if isinstance(event, dict):
        candidate = event.get("pld", event)
    else:
        candidate = getattr(event, "pld", None)
    return dict(candidate) if isinstance(candidate, dict) else {}


class AtomicPublicationStore:
    """Fixed-name, same-directory atomic JSON publication store."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory).resolve()

    def write(self, filename: str, model: BaseModel) -> Path:
        if filename not in {MARKET_FILENAME, READINESS_FILENAME, INDEX_FILENAME}:
            raise ValueError("unsupported publication filename")
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / filename
        serialized = model.model_dump_json(exclude_none=True)
        encoded = serialized.encode("utf-8")
        if len(encoded) > MAX_PUBLICATION_BYTES:
            raise ValueError("publication exceeds byte cap")
        fd, temp_name = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=str(self.directory))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(5):
                try:
                    os.replace(str(temp_path), str(destination))
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.02 * (attempt + 1))
            self._fsync_parent()
            return destination
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    def read(self, filename: str, model: Type[T]) -> tuple[Optional[T], list[str]]:
        if filename not in {MARKET_FILENAME, READINESS_FILENAME, INDEX_FILENAME}:
            return None, ["publication_filename_rejected"]
        path = self.directory / filename
        try:
            size = path.stat().st_size
            if size <= 0 or size > MAX_PUBLICATION_BYTES:
                return None, [f"publication_size_invalid:{size}"]
            raw = path.read_bytes()
            return model.model_validate_json(raw), [f"runtime_publication:{filename}", f"publication_bytes:{size}"]
        except FileNotFoundError:
            return None, [f"publication_missing:{filename}"]
        except (OSError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            return None, [f"publication_invalid:{filename}:{type(exc).__name__}"]

    def _fsync_parent(self) -> None:
        if os.name == "nt":
            return
        try:
            descriptor = os.open(str(self.directory), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass


class AgentBridgeRuntimePublisher:
    """Main-process event listener that publishes compact immutable snapshots."""

    def __init__(
        self,
        *,
        event_bus: Any | None,
        execution_position: Any | None,
        output_dir: Path,
        symbols: Iterable[str],
        readiness_interval_ms: int = 30_000,
        source_owner: str = "aurora_main_event_bus",
        publisher_version: str = "p3.v0",
        public_exchange_info: Any | None = None,
        parity_history_dir: Path | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.execution_position = execution_position
        self.store = AtomicPublicationStore(output_dir)
        self.symbols = list(dict.fromkeys(str(item).strip().upper() for item in symbols if str(item).strip()))[:MAX_SYMBOLS]
        self.readiness_interval_ms = max(1_000, int(readiness_interval_ms))
        self.source_owner = source_owner
        self.publisher_version = publisher_version
        self.public_exchange_info = public_exchange_info
        self.parity_history = (
            FilterParityHistoryStore(parity_history_dir)
            if parity_history_dir is not None else None
        )
        self._lock = threading.RLock()
        self._features: Dict[tuple[str, int], PublishedMarketSymbolV0] = {}
        self._regimes: Dict[str, Dict[str, Any]] = {}
        self._last_readiness_publish_ms = 0
        if event_bus is not None and hasattr(event_bus, "listen"):
            event_bus.listen("EVT:FEATURES_CALCULATED", self._on_features)
            event_bus.listen("EVT:REGIME_DETECTED", self._on_regime)
        if self.public_exchange_info is not None:
            self.public_exchange_info.start()

    def stop(self) -> None:
        if self.public_exchange_info is not None:
            self.public_exchange_info.stop()

    def publish_initial(self, now_ms: Optional[int] = None) -> None:
        observed = int(now_ms or time.time() * 1000)
        with self._lock:
            self._write_market(observed)
            self._write_readiness(observed)
            self._write_index(observed)

    def tick(self, now_ms: Optional[int] = None) -> None:
        observed = int(now_ms or time.time() * 1000)
        if observed - self._last_readiness_publish_ms < self.readiness_interval_ms:
            return
        with self._lock:
            self._write_readiness(observed)
            self._write_index(observed)

    def ingest_mirror_record(self, record: Dict[str, Any]) -> None:
        regime = record.get("regime")
        if regime is not None:
            self._regimes[str(record.get("symbol") or "").upper()] = {
                "regime": regime,
                "confidence": record.get("regime_confidence"),
                "ts_ms": record.get("ts_ms"),
            }
        self._ingest_feature_payload(record)

    def _on_features(self, event: Any) -> None:
        self._ingest_feature_payload(_payload(event))

    def _on_regime(self, event: Any) -> None:
        value = _payload(event)
        symbol = str(value.get("symbol") or "").upper()
        if not symbol or (self.symbols and symbol not in self.symbols):
            return
        with self._lock:
            self._regimes[symbol] = value
            for key, current in list(self._features.items()):
                if key[0] != symbol:
                    continue
                self._features[key] = current.model_copy(update={
                    "regime_label": str(value.get("regime")) if value.get("regime") is not None else None,
                    "regime_confidence": _finite(value.get("confidence")),
                    "raw_refs": list(dict.fromkeys(current.raw_refs + [f"aurora-event://REGIME_DETECTED/{symbol}/{value.get('ts_ms') or value.get('ts') or 'unknown'}"]))[:8],
                })
            observed = int(time.time() * 1000)
            self._write_market(observed)
            self._write_index(observed)

    def _ingest_feature_payload(self, value: Dict[str, Any]) -> None:
        symbol = str(value.get("symbol") or "").upper()
        try:
            tf_sec = int(value.get("tf_sec") or 0)
            feature_ts = int(value.get("ts_ms") or value.get("ts") or 0)
        except (TypeError, ValueError):
            return
        if not symbol or tf_sec < 60 or feature_ts <= 0:
            return
        if self.symbols and symbol not in self.symbols:
            return
        raw_features = value.get("features") if isinstance(value.get("features"), dict) else {}
        bar = value.get("bar") if isinstance(value.get("bar"), dict) else {}
        bar_close = int(value.get("bar_close_ts") or value.get("bar_close_ts_ms") or bar.get("close_ts") or bar.get("ts") or feature_ts)
        regime_value = value.get("regime") if value.get("regime") is not None else self._regimes.get(symbol, {})
        if isinstance(regime_value, dict):
            regime_label = regime_value.get("regime") or regime_value.get("label") or regime_value.get("name")
            regime_confidence = _finite(regime_value.get("confidence"))
        else:
            regime_label = regime_value
            regime_confidence = _finite(value.get("regime_confidence"))
        price = _finite(value.get("price") or raw_features.get("price") or bar.get("close") or bar.get("c"))
        families = PublishedFeatureFamiliesV0(
            direction_impulse=DirectionImpulseFeaturesV0(**self._select(raw_features, DirectionImpulseFeaturesV0)),
            exhaustion_late_entry=ExhaustionLateEntryFeaturesV0(**self._select(raw_features, ExhaustionLateEntryFeaturesV0)),
            liquidity_microstructure=LiquidityMicrostructureFeaturesV0(**self._select(raw_features, LiquidityMicrostructureFeaturesV0)),
            volatility_cost_viability=VolatilityCostFeaturesV0(**self._select(raw_features, VolatilityCostFeaturesV0)),
            regime_structure=RegimeStructureFeaturesV0(**self._select(raw_features, RegimeStructureFeaturesV0)),
        )
        missing = []
        if price is None:
            missing.append("last_price")
        if regime_label is None:
            missing.append("regime_label")
        if all(item is None for group in families.model_dump().values() for item in group.values()):
            missing.append("feature_families")
        snapshot = PublishedMarketSymbolV0(
            symbol=symbol,
            tf_sec=tf_sec,
            source_ts_ms=max(feature_ts, int((self._regimes.get(symbol) or {}).get("ts_ms") or 0)),
            bar_close_ts_ms=bar_close,
            feature_ts_ms=feature_ts,
            last_price=price,
            regime_label=str(regime_label) if regime_label is not None else None,
            regime_confidence=regime_confidence,
            feature_freshness="missing" if "feature_families" in missing else "fresh",
            features=families,
            missing_fields=missing,
            source_owner=self.source_owner,
            raw_refs=[f"aurora-event://FEATURES_CALCULATED/{symbol}/{feature_ts}"],
        )
        with self._lock:
            self._features[(symbol, tf_sec)] = snapshot
            observed = int(time.time() * 1000)
            self._write_market(observed)
            self._write_index(observed)

    @staticmethod
    def _select(raw: Dict[str, Any], model: Type[BaseModel]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for name in model.model_fields:
            number = _finite(raw.get(name))
            if number is not None:
                result[name] = number
        return result

    def _write_market(self, observed: int) -> None:
        symbol_priority = {symbol: index for index, symbol in enumerate(self.symbols)}
        rows = sorted(
            self._features.values(),
            key=lambda item: (
                0 if int(item.tf_sec) == 300 else 1,
                symbol_priority.get(item.symbol, len(symbol_priority)),
                int(item.tf_sec),
                item.symbol,
            ),
        )[:MAX_SYMBOLS]
        model = AgentMarketRuntimeSnapshotV0(
            produced_ts_ms=observed,
            publisher_version=self.publisher_version,
            publication_status="ready" if rows else "missing",
            symbols=rows,
        )
        self.store.write(MARKET_FILENAME, model)

    def _write_readiness(self, observed: int) -> None:
        parity_acknowledgements = (
            self.parity_history.observe_many(
                symbols=self.symbols,
                runtime=self.execution_position,
                public_exchange_info=self.public_exchange_info,
                observed_ts_ms=observed,
            )
            if self.parity_history is not None else []
        )
        snapshot = build_execution_readiness_snapshot(
            runtime=self.execution_position,
            symbols=self.symbols,
            produced_ts_ms=observed,
            trace_available=bool(getattr(self.execution_position, "correlation_store", None)),
            public_exchange_info=self.public_exchange_info,
            filter_parity_acknowledgements=parity_acknowledgements,
        )
        publication = AgentExecutionReadinessPublicationV0(
            produced_ts_ms=observed,
            publisher_version=self.publisher_version,
            source_owner="aurora_main_execution_position" if self.execution_position is not None else "publication_relay_no_runtime",
            snapshot=snapshot,
        )
        self.store.write(READINESS_FILENAME, publication)
        self._last_readiness_publish_ms = observed

    def _write_index(self, observed: int) -> None:
        status = "ready" if self._features and self.execution_position is not None else "degraded" if self._features else "missing"
        index = AgentBridgePublicationIndexV0(
            produced_ts_ms=observed,
            publisher_version=self.publisher_version,
            source_owner=(
                "direct_main_publication"
                if self.source_owner == "aurora_main_event_bus"
                else "publication_relay"
            ),
            publication_status=status,
            market_ref="aurora-publication://market/v0",
            execution_readiness_ref="aurora-publication://execution-readiness/v0",
            symbols_covered=sorted({item.symbol for item in self._features.values()}),
        )
        self.store.write(INDEX_FILENAME, index)


class RuntimePublicationReader:
    def __init__(self, directory: Path) -> None:
        self.store = AtomicPublicationStore(directory)

    def market(self) -> tuple[Optional[AgentMarketRuntimeSnapshotV0], list[str]]:
        return self.store.read(MARKET_FILENAME, AgentMarketRuntimeSnapshotV0)

    def readiness(self) -> tuple[Optional[AgentExecutionReadinessPublicationV0], list[str]]:
        return self.store.read(READINESS_FILENAME, AgentExecutionReadinessPublicationV0)

    def index(self) -> tuple[Optional[AgentBridgePublicationIndexV0], list[str]]:
        return self.store.read(INDEX_FILENAME, AgentBridgePublicationIndexV0)
