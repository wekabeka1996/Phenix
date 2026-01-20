import logging
import time
from types import SimpleNamespace
from apps.reference.core.time.clock import LiveClock


def test_decision_making_blocks_trade_intent_until_ready(monkeypatch):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    blocks: list[tuple[str, str]] = []

    def _fake_inc_warmup_block(*, domain: str, reason: str) -> None:
        blocks.append((domain, reason))

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.decision_making.inc_warmup_block",
        _fake_inc_warmup_block,
    )

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.logger = logging.getLogger("tests.task24.decision_making")
    dm._clock = LiveClock()  # T2B-08: Clock required for _features_ready()

    # FIX-MOCK-DM: _warmup_gate_before_trade_intent now reads config.domains.decision_making.warmup
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                warmup=SimpleNamespace(enforcement_mode="fail_fast")
            )
        )
    )

    dm.features_ttl_sec = 60
    dm.latest_portfolio = {"ok": True}
    dm.symbol_states = {}
    dm._per_symbol_regimes = {}
    dm._latest_warmup = {"full_ready": False, "ticks_seen": 1}
    dm._record_blocked_intent = lambda _symbol: None

    symbol = "BTCUSDT"
    now_ms = int(time.time() * 1000)
    dm.symbol_states[symbol] = {
        "features": {"ts": now_ms, "warmup": {"full_ready": True}},
        "risk": {},
    }
    # Per-symbol warmup is now required (fail-closed). Without it, warmup gate blocks with regime_warmup_missing
    # This tests that fail-closed policy works as expected

    blocked = dm._warmup_gate_before_trade_intent(
        symbol=symbol,
        rid="rid-1",
        reduce_only=False,
        context="test",
    )
    assert blocked is True
    # Since _per_symbol_regimes[symbol] is missing, reason is regime_warmup_missing (not regime_not_ready)
    assert any(domain == "decision_making" and reason == "regime_warmup_missing" for domain, reason in blocks)


def test_decision_making_reduce_only_bypasses_warmup_gate(monkeypatch):
    from apps.reference.domains.decision_making.decision_making import DecisionMaking

    called = {"n": 0}

    def _fake_inc_warmup_block(*, domain: str, reason: str) -> None:
        called["n"] += 1

    monkeypatch.setattr(
        "apps.reference.domains.decision_making.decision_making.inc_warmup_block",
        _fake_inc_warmup_block,
    )

    dm = DecisionMaking.__new__(DecisionMaking)
    dm.logger = logging.getLogger("tests.task24.decision_making")
    dm._clock = LiveClock()  # T2B-08: Clock required for warmup gate
    dm.latest_portfolio = None
    dm.symbol_states = {}
    dm._per_symbol_regimes = {}
    dm._latest_warmup = None
    dm._record_blocked_intent = lambda _symbol: None

    blocked = dm._warmup_gate_before_trade_intent(
        symbol="BTCUSDT",
        rid="rid-2",
        reduce_only=True,
        context="test",
    )
    assert blocked is False
    assert called["n"] == 0

