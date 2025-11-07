from apps.reference.domains.decision_making.decision_making import DecisionMaking
from vfoundation.core.protocol import Message
import time


class MockFSM:
    def __init__(self):
        self.events = []

    def emit(self, event_type, payload=None, why=None, data_ref=None):
        print(f'EMIT: {event_type}')
        self.events.append(
            {'type': event_type, 'payload': payload, 'why': why, 'data_ref': data_ref})

    def listen(self, event_type, handler):
        pass


config = {
    'decision': {'position_sizing': {'min_position_size_usd': 10, 'liquidity_based_cap_usd': 10000}},
    'tca_prefs': {'max_slippage_bps': 10},
    'risk_budgets': {'trade_cvar95_max_bps': 100},
    'instruments': {'BTCUSDT': {'step_size': '0.001'}}
}

mock_fsm = MockFSM()
dm = DecisionMaking(mock_fsm, config)
print(f'alpha_registry: {dm.alpha_registry}')

features_payload = {
    'symbol': 'BTCUSDT',
    'features': {
        'price': 50000,
        'price_momentum_5m': 0.01,
        'price_momentum_1h': 0.005,
        'price_momentum_1d': 0.002,
        'volume_momentum_5m': 0.02,
        'rsi_14': 55,
        'macd_signal': 0.001,
        'bb_position': 0.6,
        'bb_width': 0.05,
        'price_sma_20_deviation': 0.01,
        'volume_sma_ratio': 1.2,
        'stoch_k': 60,
        'stoch_d': 58,
        'atr_14': 1000,
        'atr_ratio': 1.2,
        'realized_volatility_1h': 0.03,
        'realized_volatility_1d': 0.025,
        'volume_volatility_ratio': 1.1,
        'price_range_ratio': 1.1,
        'bb_width_change': 0.01
    },
    'ts': int(time.time() * 1000)
}

mock_message = Message(
    op="EVT",
    verb="FEATURES_CALCULATED",
    src="test",
    dst="decision_making",
    pld=features_payload,
    rid="test-rid"
)

print("Calling on_features...")
dm.on_features(mock_message)

print(f"Events: {len(mock_fsm.events)}")
for evt in mock_fsm.events:
    print(f"  - {evt['type']}")

alpha_events = [e for e in mock_fsm.events if e['type']
                == 'EVT:ALPHA_SCORE_CALCULATED']
print(f"Alpha events: {len(alpha_events)}")
