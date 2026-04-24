"""Tests for gate_protocol.py and gate_chain.py — Slice 4.0 foundation.

Validates:
  • GateResult construction & factory
  • GateContext field budget (≤ 15)
  • GateChain short-circuit on first non-PASS
  • GateChain context_update accumulation across gates
  • GateChain trace recording
  • GateChain with empty gate list
  • GateChain with all-PASS list
"""
import pytest
from apps.reference.domains.decision_making.gateway.protocol import (
    GateContext,
    GateOutcome,
    GateResult,
)
from apps.reference.domains.decision_making.gateway.chain import (
    GateChain,
    GateChainResult,
    GateTraceEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(**overrides) -> GateContext:
    """Build a minimal GateContext for testing."""
    defaults = dict(
        symbol="BTCUSDT",
        strategy_id="aurora",
        side="BUY",
        rid="test-rid-001",
        pld={"ts_ms": 1000000},
        config=None,
        clock=None,
        dm=None,
        symbol_states={},
    )
    defaults.update(overrides)
    return GateContext(**defaults)


def _gate_pass(name: str = "pass_gate", **ctx_update):
    """Return a gate function that always PASSes."""
    def gate(ctx: GateContext) -> GateResult:
        return GateResult.passed(name, **ctx_update)
    return gate


def _gate_reject(name: str = "reject_gate", reason_code: str = "TEST_REJECT"):
    """Return a gate function that always REJECTs."""
    def gate(ctx: GateContext) -> GateResult:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=name,
            reason_code=reason_code,
            reason="DECISION",
            context=f"test:{name}",
        )
    return gate


def _gate_defer(name: str = "defer_gate", reason_code: str = "TEST_DEFER"):
    """Return a gate function that always DEFERs."""
    def gate(ctx: GateContext) -> GateResult:
        return GateResult(
            outcome=GateOutcome.DEFER,
            gate_name=name,
            reason_code=reason_code,
            reason="test_defer",
        )
    return gate


def _gate_block(name: str = "block_gate"):
    """Return a gate function that always BLOCKs."""
    def gate(ctx: GateContext) -> GateResult:
        return GateResult(
            outcome=GateOutcome.BLOCK,
            gate_name=name,
        )
    return gate


def _gate_spy(name: str = "spy", calls: list | None = None):
    """Return a gate that records its invocation and PASSes."""
    if calls is None:
        calls = []

    def gate(ctx: GateContext) -> GateResult:
        calls.append(name)
        return GateResult.passed(name)
    return gate


# ---------------------------------------------------------------------------
# GateResult tests
# ---------------------------------------------------------------------------

class TestGateResult:
    def test_passed_factory(self):
        r = GateResult.passed("my_gate", foo="bar")
        assert r.outcome == GateOutcome.PASS
        assert r.gate_name == "my_gate"
        assert r.context_update == {"foo": "bar"}
        assert r.reason_code == ""

    def test_reject_construction(self):
        r = GateResult(
            outcome=GateOutcome.REJECT,
            gate_name="risk",
            reason_code="RISK_TOO_HIGH",
            reason="RISK",
            context="test:risk",
            details={"score": 0.95},
            why_extra=["risk_score:0.95"],
        )
        assert r.outcome == GateOutcome.REJECT
        assert r.reason_code == "RISK_TOO_HIGH"
        assert r.details == {"score": 0.95}

    def test_result_is_frozen(self):
        r = GateResult.passed("g")
        with pytest.raises(AttributeError):
            r.outcome = GateOutcome.REJECT  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GateContext tests
# ---------------------------------------------------------------------------

class TestGateContext:
    def test_field_count_within_budget(self):
        """GateContext must not exceed ~15 fields (§9 discipline)."""
        import dataclasses
        fields = dataclasses.fields(GateContext)
        assert len(fields) <= 15, (
            f"GateContext has {len(fields)} fields — exceeds 15-field budget. "
            f"Fields: {[f.name for f in fields]}"
        )

    def test_basic_construction(self):
        ctx = _make_ctx()
        assert ctx.symbol == "BTCUSDT"
        assert ctx.strategy_id == "aurora"
        assert ctx.accumulated == {}

    def test_accumulated_is_mutable(self):
        ctx = _make_ctx()
        ctx.accumulated["qty"] = 42
        assert ctx.accumulated["qty"] == 42


# ---------------------------------------------------------------------------
# GateChain tests
# ---------------------------------------------------------------------------

class TestGateChain:
    def test_empty_chain_passes(self):
        chain = GateChain([])
        result = chain.run(_make_ctx())
        assert result.passed
        assert result.final_outcome == GateOutcome.PASS
        assert result.trace == []

    def test_all_pass(self):
        chain = GateChain([
            _gate_pass("g1"),
            _gate_pass("g2"),
            _gate_pass("g3"),
        ])
        result = chain.run(_make_ctx())
        assert result.passed
        assert len(result.trace) == 3
        assert all(t.outcome == "PASS" for t in result.trace)

    def test_short_circuit_on_reject(self):
        calls: list[str] = []
        chain = GateChain([
            _gate_spy("g1", calls),
            _gate_reject("g2"),
            _gate_spy("g3", calls),  # should NOT run
        ])
        result = chain.run(_make_ctx())
        assert not result.passed
        assert result.final_outcome == GateOutcome.REJECT
        assert result.terminal_result.gate_name == "g2"
        assert "g1" in calls
        assert "g3" not in calls  # short-circuited
        assert len(result.trace) == 2

    def test_short_circuit_on_defer(self):
        chain = GateChain([
            _gate_pass("g1"),
            _gate_defer("g2"),
            _gate_pass("g3"),
        ])
        result = chain.run(_make_ctx())
        assert result.final_outcome == GateOutcome.DEFER
        assert result.terminal_result.reason_code == "TEST_DEFER"
        assert len(result.trace) == 2

    def test_short_circuit_on_block(self):
        chain = GateChain([
            _gate_block("g1"),
            _gate_pass("g2"),
        ])
        result = chain.run(_make_ctx())
        assert result.final_outcome == GateOutcome.BLOCK
        assert len(result.trace) == 1

    def test_context_update_accumulation(self):
        """PASS gates merge context_update into ctx.accumulated."""
        chain = GateChain([
            _gate_pass("g1", qty=10),
            _gate_pass("g2", price=42000),
        ])
        ctx = _make_ctx()
        result = chain.run(ctx)
        assert result.passed
        assert ctx.accumulated == {"qty": 10, "price": 42000}

    def test_context_update_visible_to_later_gates(self):
        """A later gate can read what an earlier gate put into accumulated."""
        seen_value = []

        def gate_reader(ctx: GateContext) -> GateResult:
            seen_value.append(ctx.accumulated.get("magic"))
            return GateResult.passed("reader")

        chain = GateChain([
            _gate_pass("writer", magic=42),
            gate_reader,
        ])
        chain.run(_make_ctx())
        assert seen_value == [42]

    def test_trace_records_timing(self):
        chain = GateChain([_gate_pass("g1")])
        result = chain.run(_make_ctx())
        assert len(result.trace) == 1
        assert result.trace[0].gate_name == "g1"
        assert result.trace[0].elapsed_ms >= 0.0
        assert result.total_elapsed_ms >= 0.0

    def test_trace_entry_fields(self):
        chain = GateChain([_gate_reject("rj", "NRR-001")])
        result = chain.run(_make_ctx())
        entry = result.trace[0]
        assert isinstance(entry, GateTraceEntry)
        assert entry.gate_name == "rj"
        assert entry.outcome == "REJECT"
        assert entry.reason_code == "NRR-001"

    def test_reject_at_first_gate(self):
        chain = GateChain([
            _gate_reject("g1"),
            _gate_pass("g2"),
        ])
        result = chain.run(_make_ctx())
        assert result.final_outcome == GateOutcome.REJECT
        assert len(result.trace) == 1

    def test_reject_preserves_details(self):
        def gate_with_details(ctx: GateContext) -> GateResult:
            return GateResult(
                outcome=GateOutcome.REJECT,
                gate_name="detailed",
                reason_code="FOO",
                details={"key": "val"},
                why_extra=["extra1"],
            )

        chain = GateChain([gate_with_details])
        result = chain.run(_make_ctx())
        assert result.terminal_result.details == {"key": "val"}
        assert result.terminal_result.why_extra == ["extra1"]

    def test_many_gates_all_pass(self):
        chain = GateChain([_gate_pass(f"g{i}") for i in range(20)])
        result = chain.run(_make_ctx())
        assert result.passed
        assert len(result.trace) == 20
