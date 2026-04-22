"""GateChain — ordered gate runner with per-gate tracing.

Package 4, Slice 4.0.  Runs an ordered list of GateFunc against a shared
GateContext, short-circuiting on the first non-PASS outcome.

The chain is synchronous (all current gates are synchronous).  It records a
per-gate trace list that Slice 4.4 will expose via EVT:GATE_CHAIN_TRACE.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from .gate_protocol import GateContext, GateFunc, GateOutcome, GateResult

logger = logging.getLogger("domain_decision_making")


# ---------------------------------------------------------------------------
# Per-gate trace record
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GateTraceEntry:
    """One row in the chain execution trace."""
    gate_name: str
    outcome: str          # GateOutcome.value
    reason_code: str
    elapsed_ms: float


# ---------------------------------------------------------------------------
# Chain result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GateChainResult:
    """Overall result of running the full gate chain."""

    final_outcome: GateOutcome
    # The result from the gate that caused the short-circuit (or last gate).
    terminal_result: GateResult
    trace: list[GateTraceEntry] = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.final_outcome == GateOutcome.PASS


# ---------------------------------------------------------------------------
# GateChain
# ---------------------------------------------------------------------------

class GateChain:
    """Run an ordered sequence of gates, short-circuit on first non-PASS."""

    __slots__ = ("_gates",)

    def __init__(self, gates: Sequence[GateFunc]) -> None:
        self._gates: tuple[GateFunc, ...] = tuple(gates)

    def run(self, ctx: GateContext) -> GateChainResult:
        """Execute gates in order.  Returns as soon as one gate is non-PASS.

        On each PASS, any ``context_update`` from the gate is merged into
        ``ctx.accumulated`` so later gates can read carry-forward data.
        """
        trace: list[GateTraceEntry] = []
        chain_t0 = time.perf_counter()
        last_result: GateResult | None = None

        for gate_fn in self._gates:
            t0 = time.perf_counter()
            gate_name = getattr(gate_fn, "__module__", "").rsplit(".", 1)[-1] or "unknown"
            try:
                result = gate_fn(ctx)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                logger.error(
                    "[%s] GateChain: gate %s raised %s — treating as REJECT (fail-closed)",
                    ctx.symbol, gate_name, exc)
                trace.append(GateTraceEntry(
                    gate_name=gate_name,
                    outcome="ERROR",
                    reason_code=f"exception:{type(exc).__name__}",
                    elapsed_ms=round(elapsed_ms, 3),
                ))
                total = (time.perf_counter() - chain_t0) * 1000.0
                return GateChainResult(
                    final_outcome=GateOutcome.REJECT,
                    terminal_result=GateResult(
                        outcome=GateOutcome.REJECT,
                        gate_name=gate_name,
                        reason_code="GATE_CHAIN_EXCEPTION",
                        reason="ERROR",
                        context=f"gate_chain:exception:{type(exc).__name__}",
                    ),
                    trace=trace,
                    total_elapsed_ms=round(total, 3),
                )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            trace.append(GateTraceEntry(
                gate_name=result.gate_name,
                outcome=result.outcome.value,
                reason_code=result.reason_code,
                elapsed_ms=round(elapsed_ms, 3),
            ))

            last_result = result

            if result.outcome != GateOutcome.PASS:
                # Short-circuit — stop running further gates.
                total = (time.perf_counter() - chain_t0) * 1000.0
                return GateChainResult(
                    final_outcome=result.outcome,
                    terminal_result=result,
                    trace=trace,
                    total_elapsed_ms=round(total, 3),
                )

            # Merge carry-forward data for subsequent gates.
            if result.context_update:
                ctx.accumulated.update(result.context_update)

        # All gates passed.
        total = (time.perf_counter() - chain_t0) * 1000.0
        if last_result is None:
            # Empty gate list — vacuously pass.
            last_result = GateResult.passed("empty_chain")
        return GateChainResult(
            final_outcome=GateOutcome.PASS,
            terminal_result=last_result,
            trace=trace,
            total_elapsed_ms=round(total, 3),
        )
