from __future__ import annotations

import json
import logging
import threading
import uuid
from hashlib import sha256
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple


def _iso_utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()


def _truncate_why(text: Optional[str], limit: int = 80) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit]


def _stable_payload_hash(value: Dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _inputs_digest(frame: Dict[str, Any], payload: Dict[str, Any]) -> str:
    explicit = (
        payload.get("inputs_digest")
        or payload.get("inputsDigest")
        or frame.get("inputs_digest")
        or frame.get("inputsDigest")
    )
    if isinstance(explicit, str) and len(explicit.strip()) >= 8:
        return explicit.strip()

    basis = {
        "event_name": frame.get("event_name"),
        "symbol": payload.get("symbol"),
        "tf_sec": payload.get("tf_sec"),
        "ts": payload.get("ts"),
        "warmup": payload.get("warmup"),
        "bar": payload.get("bar"),
        "features": payload.get("features"),
        "price_motion": payload.get("price_motion"),
        "source_mode": payload.get("source_mode"),
        "diagnostics": payload.get("diagnostics"),
        "why": frame.get("why"),
    }
    return _stable_payload_hash(basis)


BAR_FEATURE_EVENT = "EVT:FEATURES_CALCULATED"
TICK_FEATURE_EVENT = "EVT:TICK_FEATURES_CALCULATED"


class SnapshotStore:
    """In-memory + JSONL snapshot store for Shadow Telemetry."""

    def __init__(
        self,
        output_dir: str,
        *,
        trigger_event: str,
        bar_snapshots_enabled: bool,
        tick_snapshots_mode: str,
        tick_sample_every_n: int,
        min_tf_sec_for_full: int,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.bar_snapshots_enabled = bool(bar_snapshots_enabled)
        self.tick_snapshots_mode = str(tick_snapshots_mode)
        self.tick_sample_every_n = max(1, int(tick_sample_every_n))
        self.min_tf_sec_for_full = max(0, int(min_tf_sec_for_full))
        trig = str(trigger_event or BAR_FEATURE_EVENT)
        self.trigger_event = trig if trig.startswith("EVT:") else f"EVT:{trig}"
        self.tick_trigger_event = TICK_FEATURE_EVENT
        self._feature_events = {self.trigger_event, self.tick_trigger_event}

        self.logger = logger or logging.getLogger(__name__)

        self._lock = threading.Lock()
        self._recent: Deque[Dict[str, Any]] = deque(maxlen=50000)
        self._latest: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._tick_counter: Dict[str, int] = {}

        self._regime: Dict[str, Dict[str, Any]] = {}
        self._risk: Dict[str, Dict[str, Any]] = {}
        self._signal: Dict[str, Dict[str, Any]] = {}
        self._intent: Dict[str, Dict[str, Any]] = {}
        self._execution: Dict[str, Dict[str, Any]] = {}
        self._external_intent: Dict[str, Dict[str, Any]] = {}

    def record_external_intent(self, payload: Dict[str, Any]) -> None:
        symbol = str(payload.get("symbol") or "").upper()
        if not symbol:
            return
        with self._lock:
            self._external_intent[symbol] = dict(payload)

    def ingest_event(self, frame: Dict[str, Any]) -> None:
        event_name = str(frame.get("event_name") or "")
        payload = frame.get("payload")
        if not event_name or not isinstance(payload, dict):
            return

        symbol = self._extract_symbol(event_name, payload)
        if symbol:
            self._update_context(event_name, symbol, payload)

        if event_name in self._feature_events:
            self._build_snapshot(frame, payload, event_name=event_name)

    def latest(self, symbol: Optional[str], tf_sec: Optional[int]) -> Optional[Dict[str, Any]]:
        with self._lock:
            if symbol is not None and tf_sec is not None:
                return self._latest.get((symbol.upper(), int(tf_sec)))

            if symbol is not None:
                candidates = [
                    v for (sym, _tf), v in self._latest.items() if sym == symbol.upper()
                ]
                if not candidates:
                    return None
                return max(candidates, key=lambda x: int(x.get("ts_ms", 0)))

            if not self._recent:
                return None
            return self._recent[-1]

    def tail(self, symbol: Optional[str], limit: int) -> List[Dict[str, Any]]:
        lim = max(1, min(200, int(limit)))
        with self._lock:
            if symbol is None:
                return list(self._recent)[-lim:]
            sym = symbol.upper()
            rows = [r for r in self._recent if str(r.get("symbol", "")).upper() == sym]
            return rows[-lim:]

    def _extract_symbol(self, event_name: str, payload: Dict[str, Any]) -> Optional[str]:
        if "symbol" in payload and payload.get("symbol"):
            return str(payload.get("symbol")).upper()
        if event_name == "EVT:TRADE_INTENT_PROPOSED" and payload.get("instrument"):
            return str(payload.get("instrument")).upper()
        return None

    def _update_context(self, event_name: str, symbol: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            if event_name == "EVT:REGIME_DETECTED":
                self._regime[symbol] = dict(payload)
            elif event_name == "EVT:RISK_ASSESSMENT_COMPLETED":
                self._risk[symbol] = dict(payload)
            elif event_name == "EVT:STRATEGY_SIGNAL_PRODUCED":
                self._signal[symbol] = dict(payload)
            elif event_name in ("EVT:TRADE_INTENT_PROPOSED", "EVT:TRADE_INTENT_REJECTED", "EVT:INTENT_DEFERRED"):
                self._intent[symbol] = dict(payload)
            elif event_name in (
                "EVT:ORDER_PLACED",
                "EVT:ORDER_REJECTED",
                "EVT:ORDER_STATE_CHANGED",
                "EVT:TRADE_EXECUTED",
                "EVT:POSITION_CLOSED",
            ):
                self._execution[symbol] = dict(payload)
            elif event_name == "EVT:LLM_INTENT_RECEIVED_V1":
                self._external_intent[symbol] = dict(payload)

    def _build_snapshot(self, frame: Dict[str, Any], payload: Dict[str, Any], *, event_name: str) -> None:
        symbol = str(payload.get("symbol") or "").upper()
        if not symbol:
            return

        tf_sec_raw = payload.get("tf_sec")
        try:
            tf_sec = int(tf_sec_raw) if tf_sec_raw is not None else 0
        except Exception:
            tf_sec = 0

        is_tick_event = event_name == self.tick_trigger_event
        is_bar_event = event_name == self.trigger_event

        if is_tick_event:
            if self.tick_snapshots_mode == "off":
                return
            if self.tick_snapshots_mode == "sampled":
                c = int(self._tick_counter.get(symbol, 0)) + 1
                self._tick_counter[symbol] = c
                if c % self.tick_sample_every_n != 0:
                    return
            if tf_sec != 0:
                return
        elif is_bar_event:
            if tf_sec < self.min_tf_sec_for_full:
                return
            if not self.bar_snapshots_enabled:
                return
        else:
            return

        ts_ms_raw = payload.get("ts") or frame.get("captured_ts_ms")
        try:
            ts_ms = int(ts_ms_raw)
        except Exception:
            ts_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)

        with self._lock:
            snapshot = {
                "snapshot_id": str(uuid.uuid4()),
                "inputs_digest": _inputs_digest(frame, payload),
                "ts_ms": ts_ms,
                "ts_human": _iso_utc(ts_ms),
                "symbol": symbol,
                "tf_sec": tf_sec,
                "warmup": payload.get("warmup"),
                "bar": payload.get("bar"),
                "features": payload.get("features"),
                "price_motion": payload.get("price_motion"),
                "regime": self._regime.get(symbol),
                "risk": self._risk.get(symbol),
                "signal": self._signal.get(symbol),
                "intent": self._intent.get(symbol),
                "execution": self._execution.get(symbol),
                "external_intent": self._external_intent.get(symbol),
                "why_short": _truncate_why(frame.get("why"), 80),
            }

            self._latest[(symbol, tf_sec)] = snapshot
            self._recent.append(snapshot)

        self._append_jsonl(snapshot)

    def _append_jsonl(self, snapshot: Dict[str, Any]) -> None:
        try:
            ts_ms = int(snapshot.get("ts_ms", 0))
            dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            symbol = str(snapshot.get("symbol", "UNKNOWN")).upper()
            day = dt.strftime("%Y-%m-%d")
            hour = dt.strftime("%H")
            out_path = self.output_dir / symbol / day
            out_path.mkdir(parents=True, exist_ok=True)
            file_path = out_path / f"{hour}.jsonl"
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception as e:
            self.logger.warning("Failed to append snapshot JSONL: %s", e)
