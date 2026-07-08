import decimal
import time
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.core.facade import DecisionMaking
from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway
from apps.reference.domains.decision_making.gates.safety_gates import SafetyGateResult
from apps.reference.domains.agent_bridge.contracts_p26 import AgentTradeDecisionV0
from apps.reference.domains.agent_bridge.deepseek_to_fsm_adapter import AgentTradeDecisionToSignalMapper
from apps.reference.domains.decision_making.intent.builder_validators import ResolvedKellyMetadata
from vfoundation.core.fsm_emit_compat import Message

class _Bus:
    def __init__(self) -> None:
        self.emitted = []
        self.listeners = {}

    def listen(self, event_name: str, handler) -> None:
        self.listeners[event_name] = handler

    def emit(self, event_name: str, payload: dict | None = None, *_a, **_k) -> None:
        self.emitted.append((event_name, payload or {}))

    def publish(self, topic: str, msg) -> None:
        self.emitted.append((topic, msg))

    def handle(self, msg) -> None:
        return None

class FixedClock:
    def now_ms(self) -> int:
        return 1700000000000
    def now_sec(self) -> float:
        return 1700000000.0

@pytest.fixture
def get_valid_decision_data() -> dict:
    return {
        "schema_version": "agent-trade-decision/v0",
        "agent_id": "deepseek_agent_p26",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "packet_ref": "agent-feed://packet/afp_abc123",
        "symbol": "ETHUSDT",
        "horizon": "micro",
        "action": "TESTNET_OPEN_LONG",
        "side": "BUY",
        "confidence": 0.85,
        "thesis": "Integration thesis to prove sizing invocation.",
        "invalidation": "Test invalidation that is long enough to pass.",
        "expected_scenarios": ["S01_TEST"],
        "evidence_refs": ["close_price"],
        "acknowledged_warnings": [],
        "risk_note": "Risk note that is long enough to pass validation.",
        "testnet_only": True,
    }

@patch("apps.reference.domains.decision_making.intent.builder.resolve_kelly_metadata")
@patch("apps.reference.domains.decision_making.intent.builder.resolve_order_policy_impl")
@patch("apps.reference.domains.decision_making.gateway.strategy_gateway.resolve_strategy_mode")
@patch("apps.reference.domains.decision_making.gates.safety_gate.apply_safety_gates")
def test_deepseek_signal_reaches_sizing_and_intent_builder(
    mock_asg, mock_rsm, mock_rop, mock_rkm, get_valid_decision_data
) -> None:
    # 1. Load real config
    cfg = get_config()
    bus = _Bus()

    # Assign deepseek_agent_p26 strategy to ETHUSDT in the strategy assignments registry
    cfg.strategies_registry.assignments["ETHUSDT"] = ["deepseek_agent_p26"]

    # 2. Mock resolve_strategy_mode to return 'runtime' (active mode)
    mock_rsm.return_value = "runtime"

    # Mock order policy resolution
    mock_rop.return_value = ("LIMIT", "GTC", 60000)

    # Mock Kelly metadata resolution
    mock_rkm.return_value = ResolvedKellyMetadata(
        p="0.5",
        payoff_ratio_r="2.0",
        kelly_fraction="0.25",
        provenance={}
    )

    # 3. Instantiate facade
    dm = DecisionMaking(fsm=bus, config=cfg, clock=FixedClock())

    # 4. Mock decision-making domain stubs to let signal flow
    dm._check_strategy_arbitration = MagicMock(return_value={"allowed": True})
    dm._degraded_context_gate_should_defer = MagicMock(return_value=False)
    dm._warmup_gate_before_trade_intent = MagicMock(return_value=False)
    dm._qos_enabled_for_strategy = MagicMock(return_value=False)
    dm._precheck_exposure_cache = MagicMock(return_value=True)

    # Mock regime loss embargo so it does not block the test
    dm._regime_loss_embargo = MagicMock()
    dm._regime_loss_embargo.get_entry_block.return_value = {"blocked": False}

    # 5. Mutate symbol states in-place so all delegates see the updates
    dm.symbol_states.clear()
    dm.symbol_states.update({
        "ETHUSDT": {
            "risk": {
                "ts": 1700000000000,
                "risk_parameters": {
                    "is_trading_allowed": True,
                    "risk_score": 0.1
                }
            },
            "features": {
                "ts": 1700000000000,
                "features": {},
                "warmup": {
                    "full_ready": True
                }
            }
        }
    })

    # Set regime detector warmup to ready
    dm._per_symbol_regimes["ETHUSDT"] = {
        "warmup": {
            "full_ready": True
        }
    }

    # 6. Set real portfolio value (equity=10000) so that margin-first sizing has value
    dm.latest_portfolio = {
        "equity": decimal.Decimal("10000.0"),
        "available_usdt": decimal.Decimal("10000.0"),
        "positions": [],
        "positions_last_ts_ms": 1700000000000
    }

    # Mock safety gates return ALLOW
    mock_asg.return_value = SafetyGateResult(outcome="ALLOW")

    # 7. Map decision
    decision = AgentTradeDecisionV0.model_validate(get_valid_decision_data)
    price_ctx = {
        "close_price": "2000.0",
        "entry_price": "2000.0",
        "stop_price": "1900.0",
        "target_price": "2100.0"
    }
    signal_payload = AgentTradeDecisionToSignalMapper.map_decision(
        decision,
        decision_id="test-dec-9999",
        ts_ms=1700000000000,
        price_ctx=price_ctx
    )

    # 8. Create message and publish to FSM
    msg = Message(
        op="EVT", verb="STRATEGY_SIGNAL_PRODUCED",
        src="feature_engineering", dst="decision_making",
        name="EVT:STRATEGY_SIGNAL_PRODUCED",
        pld=signal_payload,
        rid="test-dec-9999"
    )

    # Spy on PositionQueries.calculate_position_size inside dm
    spy_calc_size = MagicMock(wraps=dm._pos.calculate_position_size)
    dm._pos.calculate_position_size = spy_calc_size

    # Trigger process_signal
    dm._on_strategy_signal_gateway(msg)

    # Print emitted events to help debug
    print("EMITTED EVENTS:", bus.emitted)
    for name, pld in bus.emitted:
        if name == "EVT:TRADE_INTENT_PROPOSED":
            print("TRADE INTENT PAYLOAD:", pld)

    # ── Assertions ──

    # A. Gateway process_signal was reached
    # B. PositionQueries.calculate_position_size was called with the mapped price reference
    spy_calc_size.assert_called_once()
    assert spy_calc_size.call_args.args[0] == "ETHUSDT"
    assert spy_calc_size.call_args.args[1] == decimal.Decimal("2000.0")

    # C. IntentBuilder.build_and_emit was reached and published EVT:TRADE_INTENT_PROPOSED to bus
    emitted_intents = [pld for name, pld in bus.emitted if name == "EVT:TRADE_INTENT_PROPOSED"]
    assert len(emitted_intents) == 1, "DecisionMaking did not emit EVT:TRADE_INTENT_PROPOSED"

    intent = emitted_intents[0]
    
    # D. Emitted intent has FSM-computed sizing
    # Sizing for ETHUSDT under 10000 equity (margin_pct=0.015, leverage=1) is qty=0.075 ETH
    assert "qty" in intent["order"]
    assert float(intent["order"]["qty"]) > 0.0

    # E. Emitted intent preserves complete attribution via strategy and rid
    assert intent["strategy"] == "deepseek_agent_p26"
    assert intent["rid"] == "test-dec-9999"
