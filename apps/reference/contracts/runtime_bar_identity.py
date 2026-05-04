from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class RuntimeBarSourceMode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"
    WARMUP_IMPORT = "warmup_import"
    SYNTHETIC_REPAIR = "synthetic_repair"


@dataclass(frozen=True)
class CanonicalReplayIdentity:
    symbol: str
    timeframe_sec: int
    close_boundary_ts_ms: int
    source_mode: RuntimeBarSourceMode
    replay_generation: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe_sec": int(self.timeframe_sec),
            "close_boundary_ts_ms": int(self.close_boundary_ts_ms),
            "source_mode": self.source_mode.value,
            "replay_generation": int(self.replay_generation),
        }

    def to_ref(self) -> str:
        return (
            f"replay:{self.symbol}:{int(self.timeframe_sec)}:"
            f"{int(self.close_boundary_ts_ms)}:{self.source_mode.value}:"
            f"{int(self.replay_generation)}"
        )


@dataclass(frozen=True)
class CanonicalBarIdentity:
    symbol: str
    timeframe_sec: int
    bar_start_ts_ms: int
    bar_end_ts_ms: int
    close_boundary_ts_ms: int
    source_mode: RuntimeBarSourceMode

    def __post_init__(self) -> None:
        expected_close_boundary = int(self.bar_start_ts_ms) + int(self.timeframe_sec) * 1000
        expected_bar_end = expected_close_boundary - 1
        if int(self.close_boundary_ts_ms) != expected_close_boundary:
            raise ValueError(
                "close_boundary_ts_ms must equal bar_start_ts_ms + timeframe_sec * 1000"
            )
        if int(self.bar_end_ts_ms) != expected_bar_end:
            raise ValueError("bar_end_ts_ms must equal close_boundary_ts_ms - 1")

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe_sec": int(self.timeframe_sec),
            "bar_start_ts_ms": int(self.bar_start_ts_ms),
            "bar_end_ts_ms": int(self.bar_end_ts_ms),
            "close_boundary_ts_ms": int(self.close_boundary_ts_ms),
            "source_mode": self.source_mode.value,
        }

    def to_ref(self) -> str:
        return (
            f"bar:{self.symbol}:{int(self.timeframe_sec)}:"
            f"{int(self.close_boundary_ts_ms)}:{self.source_mode.value}"
        )

    def to_replay_identity(self, replay_generation: int = 0) -> CanonicalReplayIdentity:
        return CanonicalReplayIdentity(
            symbol=self.symbol,
            timeframe_sec=int(self.timeframe_sec),
            close_boundary_ts_ms=int(self.close_boundary_ts_ms),
            source_mode=self.source_mode,
            replay_generation=int(replay_generation),
        )


def normalize_source_mode(
    raw: Any,
    default: RuntimeBarSourceMode = RuntimeBarSourceMode.LIVE,
) -> RuntimeBarSourceMode:
    if isinstance(raw, RuntimeBarSourceMode):
        return raw
    candidate = str(raw or "").strip().lower()
    for mode in RuntimeBarSourceMode:
        if candidate == mode.value:
            return mode
    return default


def build_canonical_bar_identity(
    *,
    symbol: str,
    timeframe_sec: int,
    bar_start_ts_ms: int,
    close_boundary_ts_ms: int,
    source_mode: RuntimeBarSourceMode | str,
    bar_end_ts_ms: int | None = None,
) -> CanonicalBarIdentity:
    timeframe_sec = int(timeframe_sec)
    bar_start_ts_ms = int(bar_start_ts_ms)
    close_boundary_ts_ms = int(close_boundary_ts_ms)
    if timeframe_sec <= 0:
        raise ValueError("timeframe_sec must be positive")
    if bar_start_ts_ms < 0 or close_boundary_ts_ms <= 0:
        raise ValueError("bar timestamps must be positive")
    if bar_end_ts_ms is None:
        bar_end_ts_ms = close_boundary_ts_ms - 1
    return CanonicalBarIdentity(
        symbol=str(symbol),
        timeframe_sec=timeframe_sec,
        bar_start_ts_ms=bar_start_ts_ms,
        bar_end_ts_ms=int(bar_end_ts_ms),
        close_boundary_ts_ms=close_boundary_ts_ms,
        source_mode=normalize_source_mode(source_mode),
    )


def extract_canonical_bar_identity(
    payload: Mapping[str, Any] | None,
    *,
    default_symbol: str | None = None,
    default_timeframe_sec: int | None = None,
    default_source_mode: RuntimeBarSourceMode = RuntimeBarSourceMode.LIVE,
) -> CanonicalBarIdentity | None:
    if not isinstance(payload, Mapping):
        return None

    bar_identity_raw = payload.get("bar_identity")
    if isinstance(bar_identity_raw, Mapping):
        try:
            return build_canonical_bar_identity(
                symbol=str(bar_identity_raw["symbol"]),
                timeframe_sec=int(bar_identity_raw["timeframe_sec"]),
                bar_start_ts_ms=int(bar_identity_raw["bar_start_ts_ms"]),
                bar_end_ts_ms=int(bar_identity_raw["bar_end_ts_ms"]),
                close_boundary_ts_ms=int(bar_identity_raw["close_boundary_ts_ms"]),
                source_mode=normalize_source_mode(
                    bar_identity_raw.get("source_mode"), default=default_source_mode
                ),
            )
        except Exception:
            pass

    bar_raw = payload.get("bar")
    bar = bar_raw if isinstance(bar_raw, Mapping) else {}

    nested_bar_identity = bar.get("bar_identity")
    if isinstance(nested_bar_identity, Mapping):
        try:
            return build_canonical_bar_identity(
                symbol=str(nested_bar_identity["symbol"]),
                timeframe_sec=int(nested_bar_identity["timeframe_sec"]),
                bar_start_ts_ms=int(nested_bar_identity["bar_start_ts_ms"]),
                bar_end_ts_ms=int(nested_bar_identity["bar_end_ts_ms"]),
                close_boundary_ts_ms=int(nested_bar_identity["close_boundary_ts_ms"]),
                source_mode=normalize_source_mode(
                    nested_bar_identity.get("source_mode"), default=default_source_mode
                ),
            )
        except Exception:
            pass

    symbol = (
        payload.get("symbol")
        or bar.get("symbol")
        or default_symbol
    )
    tf_sec = (
        payload.get("tf_sec")
        or payload.get("timeframe_sec")
        or bar.get("timeframe_sec")
        or bar.get("tf_sec")
        or default_timeframe_sec
    )
    if symbol is None or tf_sec is None:
        return None

    try:
        tf_sec = int(tf_sec)
    except Exception:
        return None

    source_mode = normalize_source_mode(
        payload.get("source_mode") or bar.get("source_mode"),
        default=default_source_mode,
    )

    start_ts_ms = first_int(
        bar.get("start_ts_ms"),
        bar.get("open_ts"),
        payload.get("bar_start_ts_ms"),
    )
    close_boundary_ts_ms = first_int(
        bar.get("close_boundary_ts_ms"),
        payload.get("close_boundary_ts_ms"),
    )
    bar_end_ts_ms = first_int(
        bar.get("end_ts_ms"),
        payload.get("bar_close_ts"),
        payload.get("bar_end_ts_ms"),
        bar.get("close_ts"),
        bar.get("kline_close_time"),
    )

    if start_ts_ms is None and close_boundary_ts_ms is not None:
        start_ts_ms = int(close_boundary_ts_ms) - int(tf_sec) * 1000
    if start_ts_ms is None and bar_end_ts_ms is not None:
        start_ts_ms = int(bar_end_ts_ms) + 1 - int(tf_sec) * 1000
    if close_boundary_ts_ms is None and start_ts_ms is not None:
        close_boundary_ts_ms = int(start_ts_ms) + int(tf_sec) * 1000
    if bar_end_ts_ms is None and close_boundary_ts_ms is not None:
        bar_end_ts_ms = int(close_boundary_ts_ms) - 1

    if start_ts_ms is None or close_boundary_ts_ms is None or bar_end_ts_ms is None:
        return None

    try:
        return build_canonical_bar_identity(
            symbol=str(symbol),
            timeframe_sec=int(tf_sec),
            bar_start_ts_ms=int(start_ts_ms),
            bar_end_ts_ms=int(bar_end_ts_ms),
            close_boundary_ts_ms=int(close_boundary_ts_ms),
            source_mode=source_mode,
        )
    except Exception:
        return None


def extract_canonical_replay_identity(
    payload: Mapping[str, Any] | None,
    *,
    default_symbol: str | None = None,
    default_timeframe_sec: int | None = None,
    default_source_mode: RuntimeBarSourceMode = RuntimeBarSourceMode.LIVE,
    default_replay_generation: int = 0,
) -> CanonicalReplayIdentity | None:
    if not isinstance(payload, Mapping):
        return None

    replay_identity_raw = payload.get("replay_identity")
    if isinstance(replay_identity_raw, Mapping):
        try:
            return CanonicalReplayIdentity(
                symbol=str(replay_identity_raw["symbol"]),
                timeframe_sec=int(replay_identity_raw["timeframe_sec"]),
                close_boundary_ts_ms=int(replay_identity_raw["close_boundary_ts_ms"]),
                source_mode=normalize_source_mode(
                    replay_identity_raw.get("source_mode"), default=default_source_mode
                ),
                replay_generation=int(
                    replay_identity_raw.get("replay_generation", default_replay_generation)
                ),
            )
        except Exception:
            pass

    identity = extract_canonical_bar_identity(
        payload,
        default_symbol=default_symbol,
        default_timeframe_sec=default_timeframe_sec,
        default_source_mode=default_source_mode,
    )
    if identity is None:
        return None

    replay_generation = first_int(
        payload.get("replay_generation"),
        payload.get("bar", {}).get("replay_generation") if isinstance(payload.get("bar"), Mapping) else None,
    )
    return identity.to_replay_identity(replay_generation=replay_generation or default_replay_generation)


def attach_canonical_bar_payload(
    payload: dict[str, Any],
    *,
    identity: CanonicalBarIdentity,
    replay_generation: int = 0,
    attach_nested_bar: bool = True,
) -> dict[str, Any]:
    replay_identity = identity.to_replay_identity(replay_generation=replay_generation)
    payload["source_mode"] = identity.source_mode.value
    payload["bar_identity"] = identity.to_payload()
    payload["replay_identity"] = replay_identity.to_payload()
    payload["close_boundary_ts_ms"] = int(identity.close_boundary_ts_ms)
    payload.setdefault("bar_close_ts", int(identity.bar_end_ts_ms))
    payload.setdefault("replay_generation", int(replay_generation))

    if attach_nested_bar:
        bar = payload.get("bar")
        if isinstance(bar, dict):
            bar["source_mode"] = identity.source_mode.value
            bar["close_boundary_ts_ms"] = int(identity.close_boundary_ts_ms)
            bar["bar_identity"] = identity.to_payload()
            bar["replay_identity"] = replay_identity.to_payload()
            bar.setdefault("end_ts_ms", int(identity.bar_end_ts_ms))
            bar.setdefault("start_ts_ms", int(identity.bar_start_ts_ms))
            bar.setdefault("replay_generation", int(replay_generation))

    return payload


def first_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except Exception:
            continue
    return None
