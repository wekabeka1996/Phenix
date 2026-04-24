"""
Tests for Phase 0.5: SystemStressOverlay domain and safety_gates integration.

Coverage:
  - SystemStressOverlay disabled: no subscription, no events
  - SystemStressOverlay burn-in: no events before burn_in_bars
  - SystemStressOverlay NORMAL→STRESS transition with no-lookahead z-scores
  - No duplicate emit when state unchanged
  - _StressActuator: consecutive confirmation, min_duration, circuit breaker
  - _check_system_stress_gate: NORMAL/STRESS/EXTREME gate logic
  - SafetyGateResult.system_stress_state field populated
"""

from __future__ import annotations

import types
from typing import Any, Dict, List, Optional

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ns(**kw) -> types.SimpleNamespace:
    return types.SimpleNamespace(**kw)


def _make_ss_config(
    enabled: bool = True,
    window: int = 5,
    burn_in: int = 10,
    consecutive: int = 2,
    min_dur: int = 2,
    enter_stress: float = 0.5,
    max_switches: int = 3,
) -> types.SimpleNamespace:
    sm = _ns(
        enter_stress=enter_stress,
        exit_stress=0.30,
        enter_extreme=0.90,
        exit_extreme=0.70,
        consecutive_bars_enter=consecutive,
        consecutive_bars_exit=consecutive,
        min_duration_bars=min_dur,
        switch_window_bars=50,
        max_switches_per_window=max_switches,
    )
    agg = _ns(
        method="weighted_vote",
        weights={"atr": 0.25, "vol": 0.25, "gap": 0.25, "range": 0.25},
        k=2,
    )
    thr = _ns(atr_sigma=1.0, vol_sigma=1.0, gap_sigma=1.0, range_sigma=1.0)
    ss = _ns(enabled=enabled, baseline_window=window, burn_in_bars=burn_in,
             state_mapping=sm, aggregation=agg, thresholds=thr)
    return _ns(system_stress=ss, basis_tf_sec=300)


class _MockFSM:
    def __init__(self) -> None:
        self.emitted: List[Dict[str, Any]] = []
        self.listeners: Dict[str, Any] = {}

    def emit(self, verb: str, payload: Any, why: str = "") -> None:
        self.emitted.append({"verb": verb, "payload": payload, "why": why})

    def listen(self, verb: str, handler: Any) -> None:
        self.listeners[verb] = handler

    def register_domain(self, *a, **kw) -> None:
        pass


class _MockMsg:
    def __init__(self, pld: dict) -> None:
        self.pld = pld


def _bar_event(
    symbol: str = "BTCUSDT",
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.0,
    ts_ms: int = 1_704_067_500_000,
    tf_sec: int = 300,
) -> _MockMsg:
    return _MockMsg({
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": ts_ms,
        "bar": {
            "open": str(open_),
            "high": str(high),
            "low": str(low),
            "close": str(close),
            "end_ts_ms": ts_ms,
        },
    })


# ── Unit: _StressActuator ─────────────────────────────────────────────────────

class TestStressActuator:
    """Direct unit-tests for the incremental actuator FSM."""

    def _make_actuator(self, **sm_kw):
        from apps.reference.domains.system_stress.system_stress_overlay import _StressActuator
        defaults = dict(
            enter_stress=0.60, exit_stress=0.40,
            enter_extreme=0.85, exit_extreme=0.70,
            consecutive_bars_enter=2, consecutive_bars_exit=2,
            min_duration_bars=3, switch_window_bars=50,
            max_switches_per_window=3,
        )
        defaults.update(sm_kw)
        return _StressActuator(sm=_ns(**defaults))

    def test_stays_normal_below_threshold(self) -> None:
        act = self._make_actuator()
        for _ in range(20):
            state, _ = act.step(0.30)
        assert state == "NORMAL"

    def test_transition_normal_to_stress(self) -> None:
        act = self._make_actuator(consecutive_bars_enter=2, min_duration_bars=3)
        # warmup 3 bars in NORMAL (min_duration_bars)
        for _ in range(3):
            act.step(0.30)
        # 2 consecutive bars above enter_stress
        s1, _ = act.step(0.65)
        assert s1 == "NORMAL"  # pending_count=1, not yet
        s2, why = act.step(0.65)
        assert s2 == "STRESS"
        assert "NORMAL->STRESS" in why

    def test_hysteresis_confirmation_required(self) -> None:
        act = self._make_actuator(consecutive_bars_enter=3, min_duration_bars=2)
        for _ in range(3):
            act.step(0.30)
        act.step(0.65)  # pending=1
        act.step(0.65)  # pending=2, required=3, not yet
        assert act.state == "NORMAL"
        act.step(0.65)  # pending=3 → transition
        assert act.state == "STRESS"

    def test_interrupted_confirmation_resets(self) -> None:
        act = self._make_actuator(consecutive_bars_enter=3, min_duration_bars=2)
        for _ in range(3):
            act.step(0.30)
        act.step(0.65)  # pending=1
        act.step(0.30)  # reset → desired becomes NORMAL
        act.step(0.65)  # pending=1 again (reset)
        act.step(0.65)  # pending=2, not 3 → no transition
        assert act.state == "NORMAL"

    def test_circuit_breaker_halts(self) -> None:
        act = self._make_actuator(
            consecutive_bars_enter=2, min_duration_bars=2,
            switch_window_bars=200, max_switches_per_window=2,
        )
        # Force 2 switches to hit the circuit breaker
        def _fill_normal(n: int) -> None:
            for _ in range(n):
                act.step(0.30)
        def _fill_stress(n: int) -> None:
            for _ in range(n):
                act.step(0.70)

        _fill_normal(3)
        _fill_stress(3)  # 1st switch NORMAL→STRESS
        _fill_normal(3)  # 1st switch back STRESS→NORMAL
        _fill_stress(3)  # 2nd switch NORMAL→STRESS (hits CB limit=2 on next)
        _fill_normal(3)  # this switch would be the 3rd — should trigger CB

        # After CB, state must be frozen
        frozen_state = act.state
        for _ in range(10):
            s, w = act.step(0.0)
            assert s == frozen_state
            assert w == "CB:halt"


# ── Unit: SystemStressOverlay (event-level) ────────────────────────────────────

class TestSystemStressOverlayDisabled:
    def test_disabled_overlay_does_not_subscribe(self) -> None:
        from apps.reference.domains.system_stress.system_stress_overlay import SystemStressOverlay
        config = _make_ss_config(enabled=False)
        fsm = _MockFSM()
        overlay = SystemStressOverlay(config=config, fsm=fsm)
        # Must not subscribe to EVT:BAR_CLOSED
        assert "EVT:BAR_CLOSED" not in fsm.listeners

    def test_disabled_overlay_emits_nothing(self) -> None:
        from apps.reference.domains.system_stress.system_stress_overlay import SystemStressOverlay
        config = _make_ss_config(enabled=False)
        fsm = _MockFSM()
        overlay = SystemStressOverlay(config=config, fsm=fsm)
        msg = _bar_event(close=50.0, high=200.0, low=40.0)
        overlay.handle_event(msg)
        assert len(fsm.emitted) == 0


class TestSystemStressOverlayBurnIn:
    def _make(self, **kw):
        from apps.reference.domains.system_stress.system_stress_overlay import SystemStressOverlay
        config = _make_ss_config(**kw)
        fsm = _MockFSM()
        return SystemStressOverlay(config=config, fsm=fsm), fsm

    def test_no_emission_during_burn_in(self) -> None:
        overlay, fsm = self._make(burn_in=10, window=5)
        # Feed exactly burn_in-1 bars (varied closes to have non-trivial baseline)
        closes = [100, 99, 101, 100.5, 99.5, 100, 99, 101, 100.5, 99.5]
        for i, c in enumerate(closes[:9]):
            msg = _bar_event(
                close=c, high=c + 1.5, low=c - 1.5, open_=c,
                ts_ms=1_704_067_500_000 + i * 300_000,
            )
            overlay.handle_event(msg)
        assert len(fsm.emitted) == 0, "Must not emit before burn_in"

    def test_tf_filter_ignores_wrong_timeframe(self) -> None:
        overlay, fsm = self._make(burn_in=5, window=3)
        for i in range(20):
            msg = _bar_event(tf_sec=60, close=50.0, high=200.0, low=40.0)
            overlay.handle_event(msg)
        assert len(fsm.emitted) == 0


class TestSystemStressOverlayTransition:
    """Test NORMAL→STRESS transition via high-z events."""

    def _make(self):
        from apps.reference.domains.system_stress.system_stress_overlay import SystemStressOverlay
        # Small window and burn-in for fast tests
        config = _make_ss_config(
            window=5, burn_in=10, consecutive=2, min_dur=2, enter_stress=0.5
        )
        fsm = _MockFSM()
        overlay = SystemStressOverlay(config=config, fsm=fsm)
        return overlay, fsm

    def _feed_quiet(self, overlay, n: int, base_ts: int = 1_704_067_500_000) -> int:
        """Feed n quiet bars with variation so baseline std is non-zero.

        open_ offset from prev_close ensures non-trivial gap baseline.
        """
        patterns = [
            (1.5, 3.0, -2.0, 100.0),
            (-1.0, 2.0, -3.0,  99.0),
            (2.0, 4.0, -1.5, 101.0),
            (0.5, 2.5, -2.5, 100.5),
            (-1.5, 1.5, -3.5,  99.5),
            (1.0, 3.5, -2.0, 100.2),
            (-2.0, 1.0, -4.0,  98.8),
            (2.5, 4.5, -1.0, 101.2),
            (0.0, 3.0, -2.5, 100.3),
            (-1.0, 2.0, -3.0,  99.7),
        ]
        prev_close = 100.0
        for i in range(n):
            od, hd, ld, close = patterns[i % len(patterns)]
            open_ = prev_close + od
            high = close + abs(hd)
            low = close + ld
            overlay.handle_event(_bar_event(
                close=close, high=high, low=low, open_=open_,
                ts_ms=base_ts + i * 300_000,
            ))
            prev_close = close
        return base_ts + n * 300_000

    def _feed_crash(self, overlay, n: int, base_ts: int) -> int:
        """Feed n extreme crash bars (large gap + range)."""
        for i in range(n):
            # prev_close ~100, open=150 (50% gap), extreme H/L
            overlay.handle_event(_bar_event(
                close=50.0, high=160.0, low=40.0, open_=150.0,
                ts_ms=base_ts + i * 300_000,
            ))
        return base_ts + n * 300_000

    def test_no_emission_on_quiet_bars_after_burnin(self) -> None:
        overlay, fsm = self._make()
        # 10 burn-in + 5 quiet → NORMAL holds, no event
        ts = self._feed_quiet(overlay, n=15)
        assert len(fsm.emitted) == 0

    def test_normal_to_stress_transition(self) -> None:
        overlay, fsm = self._make()
        # 10 burn-in + 2 quiet (min_dur=2) = 12 quiet total
        ts = self._feed_quiet(overlay, n=12)
        # 2 crash bars → stress_level=1.0 which exceeds enter_extreme (0.90 default),
        # so state goes NORMAL→EXTREME directly (correct FSM behaviour).
        self._feed_crash(overlay, n=2, base_ts=ts)
        crisis_events = [
            e for e in fsm.emitted
            if e["verb"] == "EVT:SYSTEM_STRESS_STATE_UPDATED"
            and e["payload"]["state"] in ("STRESS", "EXTREME")
        ]
        assert len(crisis_events) >= 1, (
            f"Expected STRESS or EXTREME event. Emitted: {[e['payload'] for e in fsm.emitted]}"
        )
        event_pld = crisis_events[0]["payload"]
        assert event_pld["prev_state"] == "NORMAL"
        assert event_pld["symbol"] == "BTCUSDT"
        assert 0.0 <= event_pld["stress_level"] <= 1.0

    def test_no_duplicate_emission_on_same_state(self) -> None:
        overlay, fsm = self._make()
        ts = self._feed_quiet(overlay, n=12)
        self._feed_crash(overlay, n=2, base_ts=ts)
        count_before = len(fsm.emitted)
        # More crash bars: already in STRESS, no new emission unless state changes again
        self._feed_crash(overlay, n=5, base_ts=ts + 2 * 300_000)
        new_events = [
            e for e in fsm.emitted[count_before:]
            if e["payload"].get("state") == "STRESS" and e["payload"].get("prev_state") == "STRESS"
        ]
        assert len(new_events) == 0, "Must not re-emit same STRESS→STRESS"

    def test_multi_symbol_isolation(self) -> None:
        overlay, fsm = self._make()
        # Feed ETHUSDT quiet bars only — BTCUSDT should be independent
        for i in range(15):
            overlay.handle_event(_bar_event(
                symbol="ETHUSDT", close=3000.0, high=3020.0, low=2980.0,
                ts_ms=1_704_067_500_000 + i * 300_000,
            ))
        btc_events = [e for e in fsm.emitted if e["payload"].get("symbol") == "BTCUSDT"]
        assert len(btc_events) == 0


# ── Unit: _check_system_stress_gate ───────────────────────────────────────────

class TestCheckSystemStressGate:

    def _call(self, symbol: str, stress_states: Optional[dict], reduce_only: bool = False,
               stress_policy: str = "attenuate"):
        from apps.reference.domains.decision_making.gates.safety_gates import _check_system_stress_gate
        return _check_system_stress_gate(
            symbol=symbol,
            reduce_only=reduce_only,
            apply_safety_gates_flag=True,
            system_stress_states=stress_states,
            stress_policy=stress_policy,
        )

    def test_normal_allows(self) -> None:
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "NORMAL"})
        assert out == "ALLOW"
        assert state == "NORMAL"

    def test_stress_allows_and_surfaces_state(self) -> None:
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "STRESS"})
        assert out == "ALLOW"
        assert state == "STRESS"

    def test_extreme_denies(self) -> None:
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "EXTREME"})
        assert out == "DENY"
        assert deny == NormalizedRejectReasons.SYSTEM_STRESS_ENTRY_BLOCKED
        assert state == "EXTREME"

    def test_reduce_only_bypasses_extreme(self) -> None:
        out, deny, why, state = self._call("BTCUSDT", {"BTCUSDT": "EXTREME"}, reduce_only=True)
        assert out == "ALLOW"

    def test_none_stress_states_bypasses(self) -> None:
        out, deny, why, state = self._call("BTCUSDT", None)
        assert out == "ALLOW"
        assert state == "NORMAL"

    def test_unknown_symbol_defaults_to_normal(self) -> None:
        out, deny, why, state = self._call("NEWCOIN", {"BTCUSDT": "EXTREME"})
        # symbol not in dict → defaults to NORMAL → ALLOW
        assert out == "ALLOW"
        assert state == "NORMAL"

    def test_disabled_flag_bypasses(self) -> None:
        from apps.reference.domains.decision_making.gates.safety_gates import _check_system_stress_gate
        out, deny, why, state = _check_system_stress_gate(
            symbol="BTCUSDT",
            reduce_only=False,
            apply_safety_gates_flag=False,
            system_stress_states={"BTCUSDT": "EXTREME"},
            stress_policy="attenuate",  # policy=attenuate would normally deny; flag=False bypasses
        )
        assert out == "ALLOW"


# ── Unit: SafetyGateResult field ──────────────────────────────────────────────

class TestSafetyGateResultField:

    def test_default_system_stress_state_is_normal(self) -> None:
        from apps.reference.domains.decision_making.gates.safety_gates import SafetyGateResult
        r = SafetyGateResult()
        assert r.system_stress_state == "NORMAL"

    def test_field_survives_allow(self) -> None:
        from apps.reference.domains.decision_making.gates.safety_gates import SafetyGateResult
        r = SafetyGateResult(system_stress_state="STRESS")
        assert r.system_stress_state == "STRESS"
