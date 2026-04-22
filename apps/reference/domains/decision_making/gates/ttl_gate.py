"""TTL gate — GATE 5 in the strategy gateway pipeline.

Checks signal freshness against bar-TTL or features-TTL.
Extracted from strategy_gateway.py lines 803–819.
"""
from __future__ import annotations

from ..gate_protocol import GateContext, GateOutcome, GateResult

GATE_NAME = "ttl"


def check(ctx: GateContext) -> GateResult:
    dm = ctx.dm
    pld = ctx.pld

    signal_ts_ms = ctx.ts_ms
    current_ms = ctx.clock.now_ms()

    tf_sec_val = int(pld.get("tf_sec") or 0)
    if tf_sec_val > 0:
        bar_ttl = tf_sec_val * 1000 * 2
        sys_md = getattr(ctx.config.system, "market_data", None)
        if sys_md:
            bar_ttl = float(getattr(sys_md, "bar_ttl_ms", bar_ttl) or bar_ttl)
        ttl_ms = bar_ttl
    else:
        ttl_ms = dm.features_ttl_sec * 1000

    if current_ms - int(signal_ts_ms) > ttl_ms:
        return GateResult(
            outcome=GateOutcome.REJECT,
            gate_name=GATE_NAME,
            reason_code="SIGNAL_STALE",
            reason="DECISION",
            context=f"strategy_signal_gateway:signal_is_stale_ttl_{ttl_ms}ms",
        )

    return GateResult.passed(GATE_NAME)
