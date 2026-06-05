"""Gate protocol — shared types for the composable gate pipeline.

Package 4, Slice 4.0.  Every gate is a callable that receives a GateContext
and returns a GateResult.  The GateChain runner (gate_chain.py) iterates
through an ordered sequence of gates and short-circuits on the first non-PASS
outcome.

Design rules (from PACKAGE_4_GLOBAL_IMPLEMENTATION_PLAN §9):
  • GateContext must contain ONLY fields that 2+ gates need.
  • Gate-specific inputs are resolved inside the gate from config/state refs.
  • GateContext must not exceed ~15 fields.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# GateOutcome
# ---------------------------------------------------------------------------

class GateOutcome(str, enum.Enum):
    """Possible outcomes a single gate can produce."""
    PASS = "PASS"
    REJECT = "REJECT"
    DEFER = "DEFER"
    BLOCK = "BLOCK"


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class GateResult:
    """Immutable result returned by every gate function."""

    outcome: GateOutcome
    gate_name: str
    reason_code: str = ""
    reason: str = ""
    context: str = ""
    details: dict[str, Any] | None = None
    why_extra: list[str] = field(default_factory=list)
    # Opaque bag that later gates or the dispatcher can read.
    context_update: dict[str, Any] = field(default_factory=dict)

    # Convenience factory --------------------------------------------------

    @classmethod
    def passed(cls, gate_name: str, **ctx_update: Any) -> GateResult:
        return cls(outcome=GateOutcome.PASS, gate_name=gate_name,
                   context_update=dict(ctx_update) if ctx_update else {})


# ---------------------------------------------------------------------------
# GateContext — shared, *mutable* bag carried across the pipeline
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GateContext:
    """Shared context threaded through every gate in the chain.

    Field budget: ≤ 15 top-level fields (§9 discipline rule).
    Gate-specific data must NOT be pre-loaded here — resolve inside the gate.
    """

    # --- identity (4) ---
    symbol: str
    strategy_id: str
    side: str
    rid: str

    # --- event payload (1) ---
    pld: dict[str, Any]

    # --- shared state refs (4) — gates read, never replace the ref ---
    config: Any                           # AuroraConfig root
    clock: Any                            # Clock / IClock
    # DecisionMaking back-ref (for delegate calls)
    dm: Any
    symbol_states: dict[str, dict[str, Any]]

    # --- carry-forward accumulator (2) ---
    why_chain: list[str] = field(default_factory=list)
    accumulated: dict[str, Any] = field(default_factory=dict)

    # --- pre-computed by gateway (up to 3 more max) ---
    is_reduce_path: bool = False
    ts_ms: int = 0
    tf_sec: int | None = None

    # total: 14 fields — under the 15-field budget


# ---------------------------------------------------------------------------
# GateFunc — the callable signature every gate must satisfy
# ---------------------------------------------------------------------------

class GateFunc(Protocol):
    """Structural protocol for a gate callable."""

    def __call__(self, ctx: GateContext) -> GateResult: ...
