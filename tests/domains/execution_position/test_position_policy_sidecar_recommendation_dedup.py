"""Package 5.2 — Recommendation dedup / cadence hardening tests.

Proves:
1. First qualifying recommendation is emitted.
2. Repeated identical recommendation in same lifecycle is NOT re-emitted.
3. Recommendation IS re-emitted after meaningful state change.
4. Dedup does NOT block recommendations across distinct lifecycle/fill identities.
5. Shadow mode behavior remains intact.
6. Explainability / trace integrity remain intact (dedup_detail present).
"""

from pathlib import Path
from types import SimpleNamespace

from apps.reference.config_models import PositionPolicySidecarConfig
from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
    PositionPolicySidecar,
)


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, dict]] = []
        self.listeners: dict[str, list] = {}

    def listen(self, topic, handler):
        self.listeners.setdefault(topic, []).append(handler)

    def emit(self, topic, payload=None, **kwargs):
        payload = payload or {}
        self.events.append((topic, payload, kwargs))
        for handler in self.listeners.get(topic, []):
            handler(SimpleNamespace(pld=payload, verb=topic.split(
                ":")[-1], rid=payload.get("rid")))


class DummyManageFlow:
    def __init__(
        self,
        *,
        active: bool = True,
        closing: bool = False,
        side: str = "BUY",
        qty: str = "0.10",
        entry_price: str = "100.0",
    ) -> None:
        self.state = SimpleNamespace(value="TRACKING")
        self._active = active
        self._closing_position = closing
        self.position_side = side
        self.position_qty = qty
        self.position_entry_price = entry_price
        self.position_open_ts = 1_000.0
        self.symbol = "BTCUSDT"

    def has_active_lifecycle(self) -> bool:
        return self._active


def _sidecar_config(
    tmp_path: Path,
    *,
    mode: str = "shadow",
    recommend_soft_close_at: float = 0.30,
) -> PositionPolicySidecarConfig:
    return PositionPolicySidecarConfig.model_validate(
        {
            "mode": mode,
            "freshness": {
                "portfolio_max_age_ms": 15_000,
                "features_max_age_ms": 15_000,
                "regime_max_age_ms": 15_000,
                "order_state_max_age_ms": 15_000,
            },
            "startup_grace": {
                "startup_grace_ms": 0,
                "post_fill_grace_ms": 0,
                "min_portfolio_updates": 1,
                "min_feature_updates": 1,
                "min_regime_updates": 1,
            },
            "profitability_guard": {
                "enabled": False,
                "min_unrealized_pnl_pct": 0.25,
                "min_unrealized_pnl_usdt": 0.0,
            },
            "scoring": {
                "weights": {
                    "microstructure_adverse_pressure": 0.30,
                    "regime_exhaustion_hint": 0.30,
                    "conviction_decay": 0.15,
                    "unrealized_loss_pressure": 0.25,
                },
                "caps": {
                    "microstructure_adverse_pressure": 1.0,
                    "regime_exhaustion_hint": 1.0,
                    "conviction_decay": 1.0,
                    "unrealized_loss_pressure": 1.0,
                },
            },
            "thresholds": {
                "recommend_soft_close_at": recommend_soft_close_at,
                "loss_bps_full_pressure": 50.0,
                "adverse_price_distance_bps_full_pressure": 25.0,
                "book_imbalance_full_pressure": 0.35,
                "regime_confidence_floor": 0.55,
                "signal_score_floor": 0.0,
                "adverse_regimes_long": ["TREND_DOWN"],
                "adverse_regimes_short": ["TREND_UP"],
            },
            "logging": {
                "emit_internal_bus_events": True,
                "write_trade_lifecycle_jsonl": True,
                "trade_lifecycle_log_path": str(tmp_path / "trade_lifecycle.jsonl"),
                "include_score_payloads": True,
            },
            "allowed_actions": {
                "soft_close_symbol_current_net_only": True,
                "partial_reduce": False,
                "bracket_mutation": False,
                "exact_targeting": False,
            },
            "peak_giveback_close": {
                "enabled": False,
                "edge_arm_usd": 25.0,
                "giveback_trigger_pct": 50.0,
            },
        }
    )


def _event(**payload):
    return SimpleNamespace(pld=payload)


def _topics(bus: RecordingBus) -> list[str]:
    return [topic for topic, _, _ in bus.events]


def _payloads(bus: RecordingBus, topic: str) -> list[dict]:
    return [payload for recorded_topic, payload, _ in bus.events if recorded_topic == topic]


def _seed_sidecar(sidecar, now_ms):
    """Feed portfolio + features + regime so that the sidecar is primed for evaluation.

    Regime = TREND_DOWN + confidence 0.10 gives regime_exhaustion_hint = 1.0,
    producing soft_close_pressure = 0.30 (exactly at threshold).
    """
    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.10",
                    "entryPrice": "100.0",
                    "markPrice": "100.0",
                    "unrealizedProfit": "0.0",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms + 1,
            orderbook_imbalance=0.0,
            signal_score=0.0,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )


# ── Test 1: First qualifying recommendation is emitted ──────────────────────

def test_first_recommendation_is_emitted(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")
    assert len(recommended) == 1
    assert recommended[0]["score_snapshot"]["soft_close_pressure"] == 0.3


# ── Test 2: Repeated identical recommendation is suppressed ──────────────────

def test_repeated_identical_recommendation_is_suppressed(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)

    # First recommendation emitted
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    # Send identical regime event again — same scores, same state
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 3,
               regime="TREND_DOWN", confidence=0.10)
    )

    # Still only 1 recommendation — second was suppressed
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    # Verify suppression was emitted with correct reason
    suppressed_all = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")
    dedup_suppressed = [
        s for s in suppressed_all
        if s.get("suppression_reason") == "recommendation_duplicate_same_state"
    ]
    assert len(dedup_suppressed) == 1
    assert dedup_suppressed[0]["dedup_detail"]["suppressed_count"] == 1


# ── Test 3: Consecutive repeated recommendations accumulate suppression count ─

def test_consecutive_duplicates_accumulate_suppression_count(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)

    # Fire 3 more identical evaluations
    for i in range(3):
        sidecar.on_regime_detected(
            _event(symbol="BTCUSDT", ts_ms=now_ms + 10 + i,
                   regime="TREND_DOWN", confidence=0.10)
        )

    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    dedup_suppressed = [
        s for s in _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")
        if s.get("suppression_reason") == "recommendation_duplicate_same_state"
    ]
    assert len(dedup_suppressed) == 3
    assert dedup_suppressed[0]["dedup_detail"]["suppressed_count"] == 1
    assert dedup_suppressed[1]["dedup_detail"]["suppressed_count"] == 2
    assert dedup_suppressed[2]["dedup_detail"]["suppressed_count"] == 3


# ── Test 4: Re-emission after meaningful state change ────────────────────────

def test_recommendation_reemitted_after_state_change(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    # Change portfolio_position_amt — material state change
    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms + 10,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.20",
                    "entryPrice": "100.0",
                    "markPrice": "100.0",
                    "unrealizedProfit": "0.0",
                }
            ],
        )
    )

    # New recommendation emitted because position_qty signature field unchanged
    # but portfolio_position_amt changed
    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")
    assert len(recommended) == 2


# ── Test 5: Re-emission after score changes ──────────────────────────────────

def test_recommendation_reemitted_after_score_change(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    # Feed features that change the score: strong adverse imbalance + loss
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms + 10,
            orderbook_imbalance=-1.0,
            price_vs_vwap_bps=-80.0,
            signal_score=-0.5,
        )
    )

    # Regime again to trigger evaluation with new features
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 11,
               regime="TREND_DOWN", confidence=0.10)
    )

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")
    assert len(recommended) >= 2
    # Verify the new score is different
    assert recommended[-1]["score_snapshot"]["soft_close_pressure"] > 0.3


# ── Test 6: Dedup does NOT block across distinct fill identities ─────────────

def test_dedup_does_not_block_across_distinct_lifecycle(tmp_path: Path) -> None:
    """After a non-reduce-only fill resets dedup state, the same score/state
    that was previously deduplicated is emitted again as a fresh recommendation."""
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    # Confirm duplicate is suppressed
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 3,
               regime="TREND_DOWN", confidence=0.10)
    )
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    # Non-reduce-only fill resets dedup state.
    # Use a past timestamp so the fill grace check doesn't suppress.
    sidecar.on_trade_executed(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms - 1000,
            rid="rid-new-fill",
            orderId="order-new",
            clientOrderId="ENTRY-NEW",
            fill_source="trade_executed",
            canonical_fill_trace_id="exec-fill:BTCUSDT:trade_executed:rid-new-fill:2",
            reduceOnly=False,
            manage_flow_created=False,
            manage_state_before="TRACKING",
            manage_state_after="TRACKING",
        )
    )

    # Now re-seed fresh features and regime so the sidecar can evaluate again
    fresh_ms = get_clock().now_ms()
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=fresh_ms,
            orderbook_imbalance=0.0,
            signal_score=0.0,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=fresh_ms + 1,
               regime="TREND_DOWN", confidence=0.10)
    )

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")
    assert len(recommended) >= 2, (
        f"Expected ≥2 recommendations after fill reset, got {len(recommended)}. "
        f"Fill should have reset dedup state."
    )


# ── Test 7: Shadow mode preserves dedup behavior ─────────────────────────────

def test_shadow_mode_dedup_behavior(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)

    # First recommendation emitted
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1
    # No ACTION_SKIPPED in shadow mode
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED")) == 0

    # Repeat — suppressed
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 5,
               regime="TREND_DOWN", confidence=0.10)
    )
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1


# ── Test 8: Dedup detail / explainability trace integrity ────────────────────

def test_dedup_detail_trace_integrity(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)

    # Trigger duplicate
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 5,
               regime="TREND_DOWN", confidence=0.10)
    )

    dedup_suppressed = [
        s for s in _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")
        if s.get("suppression_reason") == "recommendation_duplicate_same_state"
    ]
    assert len(dedup_suppressed) == 1

    detail = dedup_suppressed[0]["dedup_detail"]
    assert detail["suppressed_count"] == 1
    assert detail["last_recommendation_ts_ms"] > 0
    assert isinstance(detail["signature_fields"], list)
    assert len(detail["signature_fields"]) == 6

    # Verify the suppressed event still carries full context
    assert dedup_suppressed[0]["symbol"] == "BTCUSDT"
    assert dedup_suppressed[0]["score_snapshot"]["soft_close_pressure"] == 0.3
    assert "trace_id" in dedup_suppressed[0]
    assert "position_snapshot" in dedup_suppressed[0]
    assert "fill_correlation" in dedup_suppressed[0]


# ── Test 9: Multi-symbol dedup is independent ────────────────────────────────

def test_multi_symbol_dedup_is_independent(tmp_path: Path) -> None:
    bus = RecordingBus()
    btc_flow = DummyManageFlow(side="BUY", qty="0.10")
    btc_flow.symbol = "BTCUSDT"
    eth_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="2000.0")
    eth_flow.symbol = "ETHUSDT"

    flows = {"BTCUSDT": btc_flow, "ETHUSDT": eth_flow}
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: flows.get(symbol),
        known_symbols_getter=lambda: {"BTCUSDT", "ETHUSDT"},
    )

    # Seed both symbols
    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.10",
                    "entryPrice": "100.0",
                    "markPrice": "100.0",
                    "unrealizedProfit": "0.0",
                },
                {
                    "symbol": "ETHUSDT",
                    "positionAmt": "1.0",
                    "entryPrice": "2000.0",
                    "markPrice": "2000.0",
                    "unrealizedProfit": "0.0",
                },
            ],
        )
    )
    for sym in ("BTCUSDT", "ETHUSDT"):
        sidecar.on_features_calculated(
            _event(symbol=sym, ts_ms=now_ms + 1,
                   orderbook_imbalance=0.0, signal_score=0.0)
        )
        sidecar.on_regime_detected(
            _event(symbol=sym, ts_ms=now_ms + 2,
                   regime="TREND_DOWN", confidence=0.10)
        )

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")
    btc_recs = [r for r in recommended if r["symbol"] == "BTCUSDT"]
    eth_recs = [r for r in recommended if r["symbol"] == "ETHUSDT"]
    assert len(btc_recs) == 1
    assert len(eth_recs) == 1

    # Repeat for BTC only — should be suppressed; ETH unaffected
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 10,
               regime="TREND_DOWN", confidence=0.10)
    )

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")
    btc_recs = [r for r in recommended if r["symbol"] == "BTCUSDT"]
    eth_recs = [r for r in recommended if r["symbol"] == "ETHUSDT"]
    assert len(btc_recs) == 1  # still 1 — duplicate suppressed
    assert len(eth_recs) == 1  # unchanged


# ── Test 10: Manage state change triggers re-emission ────────────────────────

def test_manage_state_change_triggers_reemission(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    _seed_sidecar(sidecar, now_ms)
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 1

    # Change manage_state (simulates state transition in ManageFlowFSM)
    manage_flow.state = SimpleNamespace(value="BRACKETS_ACTIVE")

    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 10,
               regime="TREND_DOWN", confidence=0.10)
    )

    # New recommendation because manage_state changed
    assert len(_payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")) == 2
