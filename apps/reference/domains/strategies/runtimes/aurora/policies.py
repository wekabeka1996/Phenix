"""Pure Aurora runtime policies.

These helpers return decisions from snapshots. AuroraHandler remains the owner
of per-symbol state mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable


@dataclass(frozen=True)
class HoldingPeriodDecision:
    suppress: bool
    reason_code: str | None = None
    time_in_position_sec: float | None = None
    min_duration_sec: float | None = None
    emergency_exit: bool = False


@dataclass(frozen=True)
class HoldingPeriodSnapshot:
    enabled: bool
    apply_to_flips: bool
    is_flip: bool
    entry_timestamp: float | None
    now_monotonic: float
    min_duration_sec: float
    score: Decimal
    emergency_threshold: float


class HoldingPeriodPolicy:
    def evaluate(self, snapshot: HoldingPeriodSnapshot) -> HoldingPeriodDecision:
        if not snapshot.enabled:
            return HoldingPeriodDecision(suppress=False)
        if snapshot.is_flip and not snapshot.apply_to_flips:
            return HoldingPeriodDecision(suppress=False)
        if snapshot.entry_timestamp is None:
            return HoldingPeriodDecision(suppress=False)

        elapsed = float(snapshot.now_monotonic) - float(snapshot.entry_timestamp)
        if elapsed >= float(snapshot.min_duration_sec):
            return HoldingPeriodDecision(
                suppress=False,
                time_in_position_sec=elapsed,
                min_duration_sec=float(snapshot.min_duration_sec),
            )
        emergency_exit = abs(float(snapshot.score)) >= float(snapshot.emergency_threshold)
        if emergency_exit:
            return HoldingPeriodDecision(
                suppress=False,
                time_in_position_sec=elapsed,
                min_duration_sec=float(snapshot.min_duration_sec),
                emergency_exit=True,
            )
        return HoldingPeriodDecision(
            suppress=True,
            reason_code="HOLDING_PERIOD_ACTIVE",
            time_in_position_sec=elapsed,
            min_duration_sec=float(snapshot.min_duration_sec),
        )


@dataclass(frozen=True)
class RegimeInertiaSnapshot:
    raw_previous: str | None
    effective_previous: str | None
    raw_candidate: str | None
    raw_change_ts: float | None
    now_monotonic: float
    anti_churn_enabled: bool
    confirm_window_sec: float
    same_severity_confirm_window_sec: float
    immediate_risk_off: bool


@dataclass(frozen=True)
class RegimeInertiaResult:
    raw: str | None
    effective: str | None
    raw_change_ts: float | None


class RegimeInertiaPolicy:
    def __init__(self, severity_fn: Callable[[str | None], int]) -> None:
        self._severity_fn = severity_fn

    def apply(self, snapshot: RegimeInertiaSnapshot) -> RegimeInertiaResult:
        raw = snapshot.raw_previous
        effective = snapshot.effective_previous
        raw_change_ts = snapshot.raw_change_ts
        now = float(snapshot.now_monotonic)

        if raw is None and effective is None:
            return RegimeInertiaResult(
                raw=snapshot.raw_candidate,
                effective=snapshot.raw_candidate,
                raw_change_ts=now,
            )

        if snapshot.raw_candidate != raw:
            raw = snapshot.raw_candidate
            raw_change_ts = now

        if not snapshot.anti_churn_enabled or snapshot.confirm_window_sec <= 0.0:
            return RegimeInertiaResult(raw=raw, effective=raw, raw_change_ts=raw_change_ts)

        if raw == effective:
            return RegimeInertiaResult(raw=raw, effective=effective, raw_change_ts=raw_change_ts)

        eff_sev = self._severity_fn(effective)
        raw_sev = self._severity_fn(raw)
        if snapshot.immediate_risk_off and raw_sev > eff_sev:
            return RegimeInertiaResult(raw=raw, effective=raw, raw_change_ts=raw_change_ts)

        if raw_sev == eff_sev and snapshot.same_severity_confirm_window_sec > 0.0:
            if raw_change_ts is None or (now - raw_change_ts) >= snapshot.same_severity_confirm_window_sec:
                effective = raw
            return RegimeInertiaResult(raw=raw, effective=effective, raw_change_ts=raw_change_ts)

        if raw_change_ts is None or (now - raw_change_ts) >= snapshot.confirm_window_sec:
            effective = raw
        return RegimeInertiaResult(raw=raw, effective=effective, raw_change_ts=raw_change_ts)


@dataclass(frozen=True)
class RegimeTpslSelection:
    regime_used: str
    reason: str


class RegimeTpslCalculator:
    def select_regime(
        self,
        *,
        raw_regime: str | None,
        effective_regime: str | None,
        anti_churn_enabled: bool,
    ) -> RegimeTpslSelection:
        if anti_churn_enabled and effective_regime:
            return RegimeTpslSelection(regime_used=effective_regime, reason="effective_regime")
        return RegimeTpslSelection(regime_used=raw_regime or "DEFAULT", reason="raw_or_default")


__all__ = [
    "HoldingPeriodDecision",
    "HoldingPeriodPolicy",
    "HoldingPeriodSnapshot",
    "RegimeInertiaPolicy",
    "RegimeInertiaResult",
    "RegimeInertiaSnapshot",
    "RegimeTpslCalculator",
    "RegimeTpslSelection",
]
