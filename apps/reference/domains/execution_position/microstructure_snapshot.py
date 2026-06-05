"""Canonical FeatureEngineering -> execution_position microstructure snapshot helpers."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator


MICROSTRUCTURE_SNAPSHOT_CONTRACT = "microstructure_snapshot_v1"
MICROSTRUCTURE_PRESSURE_CONTRACT = "microstructure_pressure_v1"
RETAINABLE_SNAPSHOT_FIELDS = (
    "atr_14",
    "atr_pct",
    "atr_ready",
    "obi_close",
)
CORE_MICROSTRUCTURE_FIELDS = (
    "price",
    "atr_14",
    "orderbook_imbalance",
    "spread_bps",
    "liquidity_kappa",
)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dict(dumped)
        except Exception:
            return {}
    return {}


def _coerce_float(value: Any) -> Optional[float]:
    if value in (None, "", "None", "null"):
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None", "null"):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _extract_ts_ms(payload: Mapping[str, Any]) -> int:
    for key in (
        "ts_ms",
        "timestamp_ms",
        "ts",
        "timestamp",
        "bar_close_ts",
        "close_boundary_ts_ms",
    ):
        value = _coerce_float(payload.get(key))
        if value is not None and value >= 0:
            return int(value)
    return 0


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _read_path(payload: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _select_numeric(
    payload: Mapping[str, Any],
    *,
    canonical_paths: Iterable[Sequence[str]],
    legacy_paths: Iterable[Sequence[str]] = (),
) -> Tuple[Optional[float], Optional[str], bool]:
    for path in canonical_paths:
        value = _coerce_float(_read_path(payload, path))
        if value is not None:
            return value, ".".join(path), False
    for path in legacy_paths:
        value = _coerce_float(_read_path(payload, path))
        if value is not None:
            return value, ".".join(path), True
    return None, None, False


def _select_bool(
    payload: Mapping[str, Any],
    *,
    canonical_paths: Iterable[Sequence[str]],
    legacy_paths: Iterable[Sequence[str]] = (),
) -> Tuple[Optional[bool], Optional[str], bool]:
    for path in canonical_paths:
        value = _coerce_bool(_read_path(payload, path))
        if value is not None:
            return value, ".".join(path), False
    for path in legacy_paths:
        value = _coerce_bool(_read_path(payload, path))
        if value is not None:
            return value, ".".join(path), True
    return None, None, False


class MicrostructureSnapshotV1(BaseModel):
    """Canonical execution-side view of the latest FeatureEngineering semantics."""

    model_config = ConfigDict(extra="forbid")

    contract: str = Field(default=MICROSTRUCTURE_SNAPSHOT_CONTRACT)
    symbol: str = Field(..., min_length=1)
    ts_ms: int = Field(default=0, ge=0)
    tf_sec: int = Field(default=0, ge=0)
    price: Optional[float] = None
    atr_14: Optional[float] = None
    atr_pct: Optional[float] = None
    atr_ready: Optional[bool] = None
    orderbook_imbalance: Optional[float] = None
    obi: Optional[float] = None
    obi_close: Optional[float] = None
    spread_bps: Optional[float] = None
    liquidity_kappa: Optional[float] = None
    pm_norm_10s: Optional[float] = None
    pm_norm_60s: Optional[float] = None
    pm_norm_300s: Optional[float] = None
    warmup_full_ready: Optional[bool] = None
    source_paths: Dict[str, str] = Field(default_factory=dict)
    legacy_fallback_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    retained_fields: list[str] = Field(default_factory=list)

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalize_symbol(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).strip().upper()


class MicrostructurePressureV1(BaseModel):
    """Bounded microstructure pressure verdict used by post-entry soft-close logic."""

    model_config = ConfigDict(extra="forbid")

    contract: str = Field(default=MICROSTRUCTURE_PRESSURE_CONTRACT)
    enabled: bool = False
    authority_state: str = Field(default="observe_only", min_length=1)
    authority_reason: str = Field(default="observe_only", min_length=1)
    warmup_full_ready: Optional[bool] = None
    orderbook_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    price_motion_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    spread_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    liquidity_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    microstructure_adverse_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_fields: list[str] = Field(default_factory=list)
    retained_fields: list[str] = Field(default_factory=list)
    source_paths: Dict[str, str] = Field(default_factory=dict)


def extract_microstructure_snapshot(
    payload: Mapping[str, Any],
) -> Optional[MicrostructureSnapshotV1]:
    raw_payload = _as_dict(payload)
    symbol = str(raw_payload.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    source_paths: Dict[str, str] = {}
    legacy_fallback_fields: set[str] = set()

    price, price_path, _ = _select_numeric(
        raw_payload,
        canonical_paths=(("features", "price"), ("price",)),
    )
    if price_path is not None:
        source_paths["price"] = price_path

    atr_14, atr_path, atr_legacy = _select_numeric(
        raw_payload,
        canonical_paths=(
            ("features", "volatility", "atr_14"),
            ("volatility", "atr_14"),
        ),
        legacy_paths=(("features", "atr_14"), ("atr_14",)),
    )
    if atr_path is not None:
        source_paths["atr_14"] = atr_path
    if atr_legacy:
        legacy_fallback_fields.add("atr_14")

    atr_pct, atr_pct_path, atr_pct_legacy = _select_numeric(
        raw_payload,
        canonical_paths=(
            ("features", "volatility", "atr_pct"),
            ("volatility", "atr_pct"),
        ),
        legacy_paths=(("features", "atr_pct"), ("atr_pct",)),
    )
    if atr_pct_path is not None:
        source_paths["atr_pct"] = atr_pct_path
    if atr_pct_legacy:
        legacy_fallback_fields.add("atr_pct")

    atr_ready, atr_ready_path, atr_ready_legacy = _select_bool(
        raw_payload,
        canonical_paths=(
            ("features", "volatility", "atr_ready"),
            ("volatility", "atr_ready"),
        ),
        legacy_paths=(("features", "atr_ready"), ("atr_ready",)),
    )
    if atr_ready_path is not None:
        source_paths["atr_ready"] = atr_ready_path
    if atr_ready_legacy:
        legacy_fallback_fields.add("atr_ready")

    obi, obi_path, _ = _select_numeric(
        raw_payload,
        canonical_paths=(("features", "obi"), ("obi",)),
    )
    if obi_path is not None:
        source_paths["obi"] = obi_path

    obi_close, obi_close_path, obi_close_legacy = _select_numeric(
        raw_payload,
        canonical_paths=(
            ("features", "liquidity", "obi_close"),
            ("liquidity", "obi_close"),
        ),
        legacy_paths=(("features", "obi_close"), ("obi_close",)),
    )
    if obi_close_path is not None:
        source_paths["obi_close"] = obi_close_path
    if obi_close_legacy:
        legacy_fallback_fields.add("obi_close")

    orderbook_imbalance = obi
    if orderbook_imbalance is not None:
        source_paths["orderbook_imbalance"] = source_paths.get("obi", "features.obi")
    elif obi_close is not None:
        orderbook_imbalance = obi_close
        source_paths["orderbook_imbalance"] = source_paths.get(
            "obi_close", "features.liquidity.obi_close"
        )
    else:
        orderbook_imbalance, orderbook_path, orderbook_legacy = _select_numeric(
            raw_payload,
            canonical_paths=(),
            legacy_paths=(
                ("features", "orderbook_imbalance"),
                ("orderbook_imbalance",),
                ("features", "book_imbalance"),
                ("book_imbalance",),
                ("features", "microstructure_imbalance"),
                ("microstructure_imbalance",),
            ),
        )
        if orderbook_path is not None:
            source_paths["orderbook_imbalance"] = orderbook_path
        if orderbook_legacy:
            legacy_fallback_fields.add("orderbook_imbalance")

    spread_bps, spread_path, _ = _select_numeric(
        raw_payload,
        canonical_paths=(("features", "spread_bps"), ("spread_bps",)),
    )
    if spread_path is not None:
        source_paths["spread_bps"] = spread_path

    liquidity_kappa, liquidity_kappa_path, _ = _select_numeric(
        raw_payload,
        canonical_paths=(("features", "liquidity_kappa"), ("liquidity_kappa",)),
    )
    if liquidity_kappa_path is not None:
        source_paths["liquidity_kappa"] = liquidity_kappa_path

    pm_norm_10s, pm10_path, _ = _select_numeric(
        raw_payload,
        canonical_paths=(("price_motion", "pm_norm_10s"),),
    )
    if pm10_path is not None:
        source_paths["pm_norm_10s"] = pm10_path

    pm_norm_60s, pm60_path, _ = _select_numeric(
        raw_payload,
        canonical_paths=(("price_motion", "pm_norm_60s"),),
    )
    if pm60_path is not None:
        source_paths["pm_norm_60s"] = pm60_path

    pm_norm_300s, pm300_path, _ = _select_numeric(
        raw_payload,
        canonical_paths=(("price_motion", "pm_norm_300s"),),
    )
    if pm300_path is not None:
        source_paths["pm_norm_300s"] = pm300_path

    warmup_full_ready, warmup_path, _ = _select_bool(
        raw_payload,
        canonical_paths=(("warmup", "full_ready"),),
    )
    if warmup_path is not None:
        source_paths["warmup_full_ready"] = warmup_path

    snapshot_data = {
        "symbol": symbol,
        "ts_ms": _extract_ts_ms(raw_payload),
        "tf_sec": int(_coerce_float(raw_payload.get("tf_sec")) or 0),
        "price": price,
        "atr_14": atr_14,
        "atr_pct": atr_pct,
        "atr_ready": atr_ready,
        "orderbook_imbalance": orderbook_imbalance,
        "obi": obi,
        "obi_close": obi_close,
        "spread_bps": spread_bps,
        "liquidity_kappa": liquidity_kappa,
        "pm_norm_10s": pm_norm_10s,
        "pm_norm_60s": pm_norm_60s,
        "pm_norm_300s": pm_norm_300s,
        "warmup_full_ready": warmup_full_ready,
        "source_paths": source_paths,
        "legacy_fallback_fields": sorted(legacy_fallback_fields),
    }
    snapshot = MicrostructureSnapshotV1.model_validate(snapshot_data)

    missing_fields = [
        field_name
        for field_name in CORE_MICROSTRUCTURE_FIELDS
        if getattr(snapshot, field_name) is None
    ]
    return snapshot.model_copy(update={"missing_fields": missing_fields})


def merge_microstructure_snapshots(
    previous: MicrostructureSnapshotV1,
    incoming: MicrostructureSnapshotV1,
) -> MicrostructureSnapshotV1:
    merged = incoming.model_dump()
    retained_fields = set(incoming.retained_fields)
    source_paths = dict(incoming.source_paths)

    for field_name in RETAINABLE_SNAPSHOT_FIELDS:
        if merged.get(field_name) is None and getattr(previous, field_name) is not None:
            merged[field_name] = getattr(previous, field_name)
            retained_fields.add(field_name)
            previous_path = previous.source_paths.get(field_name)
            if previous_path and field_name not in source_paths:
                source_paths[field_name] = previous_path

    if merged.get("orderbook_imbalance") is None and previous.orderbook_imbalance is not None:
        merged["orderbook_imbalance"] = previous.orderbook_imbalance
        retained_fields.add("orderbook_imbalance")
        previous_path = previous.source_paths.get("orderbook_imbalance")
        if previous_path and "orderbook_imbalance" not in source_paths:
            source_paths["orderbook_imbalance"] = previous_path

    merged["source_paths"] = source_paths
    merged["retained_fields"] = sorted(retained_fields)
    merged["legacy_fallback_fields"] = sorted(
        set(previous.legacy_fallback_fields) | set(incoming.legacy_fallback_fields)
    )

    merged_snapshot = MicrostructureSnapshotV1.model_validate(merged)
    missing_fields = [
        field_name
        for field_name in CORE_MICROSTRUCTURE_FIELDS
        if getattr(merged_snapshot, field_name) is None
    ]
    return merged_snapshot.model_copy(update={"missing_fields": missing_fields})


def get_microstructure_snapshot(
    payload: Mapping[str, Any],
) -> Optional[MicrostructureSnapshotV1]:
    raw_payload = _as_dict(payload)
    embedded = raw_payload.get(MICROSTRUCTURE_SNAPSHOT_CONTRACT)
    if isinstance(embedded, Mapping):
        try:
            return MicrostructureSnapshotV1.model_validate(dict(embedded))
        except Exception:
            pass
    return extract_microstructure_snapshot(raw_payload)


def attach_microstructure_snapshot(
    payload: Mapping[str, Any],
    *,
    previous_snapshot: Optional[MicrostructureSnapshotV1] = None,
) -> Dict[str, Any]:
    enriched = _as_dict(payload)
    current_snapshot = extract_microstructure_snapshot(enriched)
    if current_snapshot is None:
        return enriched
    if previous_snapshot is not None:
        current_snapshot = merge_microstructure_snapshots(
            previous_snapshot,
            current_snapshot,
        )
    enriched[MICROSTRUCTURE_SNAPSHOT_CONTRACT] = current_snapshot.model_dump()
    return enriched


def build_microstructure_pressure(
    snapshot: Optional[MicrostructureSnapshotV1],
    *,
    side: str,
    enabled: bool,
    authority_state: str,
    authority_reason: str,
    adverse_obi_full_pressure: float,
    adverse_pm_norm_full_pressure: float,
    spread_bps_full_pressure: float,
    liquidity_kappa_floor: float,
) -> MicrostructurePressureV1:
    if snapshot is None:
        return MicrostructurePressureV1(
            enabled=bool(enabled),
            authority_state=authority_state,
            authority_reason=authority_reason,
            missing_fields=[*CORE_MICROSTRUCTURE_FIELDS, "pm_norm"],
        )

    side_sign = 1.0 if str(side or "").upper() == "BUY" else -1.0

    orderbook_pressure = 0.0
    if snapshot.orderbook_imbalance is not None and adverse_obi_full_pressure > 0:
        raw_adverse = max(0.0, -side_sign * snapshot.orderbook_imbalance)
        orderbook_pressure = _clamp(raw_adverse / adverse_obi_full_pressure)

    pm_values = [
        value
        for value in (
            snapshot.pm_norm_10s,
            snapshot.pm_norm_60s,
            snapshot.pm_norm_300s,
        )
        if value is not None
    ]
    price_motion_pressure = 0.0
    if pm_values and adverse_pm_norm_full_pressure > 0:
        adverse_pm = max(max(0.0, -side_sign * value) for value in pm_values)
        price_motion_pressure = _clamp(adverse_pm / adverse_pm_norm_full_pressure)

    spread_pressure = 0.0
    if snapshot.spread_bps is not None and spread_bps_full_pressure > 0:
        spread_pressure = _clamp(snapshot.spread_bps / spread_bps_full_pressure)

    liquidity_pressure = 0.0
    if (
        snapshot.liquidity_kappa is not None
        and liquidity_kappa_floor > 0
        and snapshot.liquidity_kappa < liquidity_kappa_floor
    ):
        liquidity_pressure = _clamp(
            (liquidity_kappa_floor - snapshot.liquidity_kappa) / liquidity_kappa_floor
        )

    missing_fields = set(snapshot.missing_fields)
    if not pm_values:
        missing_fields.add("pm_norm")

    pressure_value = 0.0
    if enabled:
        pressure_value = max(
            orderbook_pressure,
            price_motion_pressure,
            spread_pressure,
            liquidity_pressure,
        )

    return MicrostructurePressureV1(
        enabled=bool(enabled),
        authority_state=authority_state,
        authority_reason=authority_reason,
        warmup_full_ready=snapshot.warmup_full_ready,
        orderbook_pressure=orderbook_pressure,
        price_motion_pressure=price_motion_pressure,
        spread_pressure=spread_pressure,
        liquidity_pressure=liquidity_pressure,
        microstructure_adverse_pressure=pressure_value,
        missing_fields=sorted(missing_fields),
        retained_fields=list(snapshot.retained_fields),
        source_paths=dict(snapshot.source_paths),
    )


__all__ = [
    "MICROSTRUCTURE_PRESSURE_CONTRACT",
    "MICROSTRUCTURE_SNAPSHOT_CONTRACT",
    "MicrostructurePressureV1",
    "MicrostructureSnapshotV1",
    "attach_microstructure_snapshot",
    "build_microstructure_pressure",
    "extract_microstructure_snapshot",
    "get_microstructure_snapshot",
    "merge_microstructure_snapshots",
]