# vfoundation/apps/reference/telemetry/metrics.py
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
except Exception:  # fail-closed: заглушки якщо либ немає

    class _D:
        def __getattr__(self, _):
            return self

        def labels(self, *_, **__):
            return self

        def set(self, *_):
            pass

        def inc(self, *_):
            pass

        def observe(self, *_):
            pass

    Gauge = Counter = Histogram = _D  # type: ignore

    def generate_latest():
        return b""

    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"


def _d(x: Any) -> float:
    try:
        from decimal import Decimal as D

        return float(D(str(x)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


# Gauges (поточні значення)
g_exposure_equity_usd = Gauge(
    "exposure_equity_usd", "Free equity (USDT-M) used for sizing")
g_exposure_positions_usd = Gauge(
    "exposure_positions_usd", "Open positions notional in USD")
g_exposure_positions_margin_usd = Gauge(
    "exposure_positions_margin_usd", "Open positions margin in USD")  # EXP-LEVERAGE-001
g_exposure_pending_usd = Gauge(
    "exposure_pending_usd", "Pending (reserved) notional in USD")
g_exposure_pending_margin_usd = Gauge(
    "exposure_pending_margin_usd", "Pending (reserved) margin in USD")  # EXP-LEVERAGE-001
g_exposure_limit_usd = Gauge(
    "exposure_limit_usd", "Exposure limit in USD (equity * fraction)")
g_exposure_margin_limit_usd = Gauge(
    "exposure_margin_limit_usd", "Margin exposure limit in USD (equity * utilization_pct)")  # EXP-LEVERAGE-001

# Gauges with labels
g_reservation_margin_usd = Gauge(
    "reservation_margin_usd", "Margin reserved for pending orders", ["symbol"])  # EXP-LEVERAGE-001

# Counters (події)
c_guard_rejects_total = Counter(
    "fsm_guard_rejects_total", "FSM guard rejects", ["guard"])
c_pending_expired_total = Counter(
    "pending_exposure_expired_total", "Expired pending reservations by TTL"
)
c_manage_skipped_total = Counter(
    "manage_skipped_total", "Auto-manage skipped due to bracket mode")
c_orders_placed_total = Counter(
    "orders_placed_total", "Orders placed (entry & brackets)")
c_orders_filled_total = Counter("orders_filled_total", "Orders filled")
c_decision_rate_limited = Counter(
    "decision_rate_limited_total", "Decision intents rate-limited", ["symbol"]
)
c_decision_deferred_total = Counter(
    "decision_deferred_total", "Decision deferrals", ["reason", "symbol"]
)
c_bridge_deferred_total = Counter(
    "bridge_deferred_total", "Bridge deferrals", ["reason", "symbol"]
)
c_bridge_retry_total = Counter(
    "bridge_retry_total", "Bridge defer retries", ["symbol"]
)

# Order lifecycle metrics (AUR-004)
c_order_state_total = Counter(
    "order_state_total", "Order state changes", ["status"])
h_order_lifecycle_seconds = Histogram(
    "order_lifecycle_seconds",
    "Order lifecycle duration from NEW to terminal",
    buckets=(1, 5, 10, 30, 60, 300, 600),
)


# Metrics for hybrid coherence
AURORA_HYBRID_COHERENT = Gauge(
    'aurora_hybrid_coherent',
    'Indicates if the hybrid mode is coherent (1) or incoherent (0).',
    ['mode']
)
AURORA_HYBRID_INCOHERENT_REASONS_TOTAL = Counter(
    'aurora_hybrid_incoherent_reasons_total',
    'Counts the total number of times a specific reason for hybrid incoherence occurred.',
    ['reason']
)


def update_hybrid_coherence_metrics(state: dict):
    is_coherent = state['last_result']['ok']
    reasons = state['last_result']['reasons']
    # Assuming this is the 'mode' label
    execution_mode = state['execution_mode']

    mode_label = f"hybrid_{execution_mode}" if execution_mode else "hybrid_unknown"

    if is_coherent:
        AURORA_HYBRID_COHERENT.labels(mode=mode_label).set(1)
    else:
        AURORA_HYBRID_COHERENT.labels(mode=mode_label).set(0)
        for reason in reasons:
            # Slugify reason for metric label
            reason_slug = reason.lower().replace(' ', '_').replace('.', '').replace("'", '')
            AURORA_HYBRID_INCOHERENT_REASONS_TOTAL.labels(
                reason=reason_slug).inc()


def update_exposure(equity_usd: Any, positions_usd: Any, pending_usd: Any, fraction: float) -> None:
    eq = _d(equity_usd)
    pos = _d(positions_usd)
    pen = _d(pending_usd)
    lim = eq * float(fraction)
    g_exposure_equity_usd.set(eq)
    g_exposure_positions_usd.set(pos)
    g_exposure_pending_usd.set(pen)
    g_exposure_limit_usd.set(lim)


def update_exposure_margin(equity_usd: Any, positions_margin_usd: Any, pending_margin_usd: Any, utilization_pct: float) -> None:
    """EXP-LEVERAGE-001: Update margin-based exposure metrics."""
    eq = _d(equity_usd)
    pos_margin = _d(positions_margin_usd)
    pen_margin = _d(pending_margin_usd)
    margin_lim = eq * float(utilization_pct)
    g_exposure_positions_margin_usd.set(pos_margin)
    g_exposure_pending_margin_usd.set(pen_margin)
    g_exposure_margin_limit_usd.set(margin_lim)


def update_reservation_margin(symbol: str, margin_usd: Any) -> None:
    """EXP-LEVERAGE-001: Update reservation margin for a symbol."""
    g_reservation_margin_usd.labels(symbol=symbol).set(_d(margin_usd))


def inc_exposure_guard_block() -> None:
    c_guard_rejects_total.labels(guard="exposure").inc()


def inc_pending_expired(n: int) -> None:
    if n > 0:
        c_pending_expired_total.inc(n)


def inc_manage_skipped() -> None:
    c_manage_skipped_total.inc()


def inc_order_placed() -> None:
    c_orders_placed_total.inc()


def inc_order_filled() -> None:
    c_orders_filled_total.inc()


def inc_decision_rl(symbol: str) -> None:
    c_decision_rate_limited.labels(symbol=symbol).inc()


def inc_decision_deferred(reason: str, symbol: str) -> None:
    c_decision_deferred_total.labels(reason=reason, symbol=symbol).inc()


def inc_bridge_deferred(reason: str, symbol: str) -> None:
    c_bridge_deferred_total.labels(reason=reason, symbol=symbol).inc()


def inc_bridge_retry(symbol: str) -> None:
    c_bridge_retry_total.labels(symbol=symbol).inc()


def inc_order_state(status: str) -> None:
    c_order_state_total.labels(status=status).inc()


def observe_order_lifecycle(duration_seconds: float) -> None:
    h_order_lifecycle_seconds.observe(duration_seconds)
