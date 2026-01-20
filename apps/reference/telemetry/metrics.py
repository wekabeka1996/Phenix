# vfoundation/apps/reference/telemetry/metrics.py
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any

try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
except Exception:  # fail-closed: заглушки якщо либ немає

    class _D:
        def __init__(self, *_, **__):
            # Accept any args to mirror prometheus_client constructor signature
            pass

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

    # type: ignore[misc]
    def generate_latest(registry: Any = None, escaping: str = "underscores") -> bytes:
        """Fallback implementation of generate_latest when prometheus_client is unavailable."""
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

# Warmup/readiness gating (TASK24)
c_warmup_block_total = Counter(
    "warmup_block_total",
    "Warmup/readiness blocks (fail-closed, no trading until READY)",
    ["domain", "reason"],
)

# Data quality (TASK24)
c_data_quality_drop_total = Counter(
    "data_quality_drop_total",
    "Data-quality drops/ignores (explicit, no silent degrade)",
    ["domain", "reason"],
)
c_data_quality_bad_dt_total = Counter(
    "data_quality_bad_dt_total",
    "Bad dt observations (dt<=0) for time-normalized features",
    ["domain"],
)

# Macro sync out-of-order observability (FE-WARMUP-UNBLOCK-01)
c_macro_sync_ooo_dropped_total = Counter(
    "macro_sync_ooo_dropped_total",
    "Macro sync: out-of-order bins dropped (too late to reorder)",
    ["key"],
)
c_macro_sync_ooo_reordered_total = Counter(
    "macro_sync_ooo_reordered_total",
    "Macro sync: out-of-order bins reordered/inserted (within tolerance)",
    ["key"],
)
g_macro_sync_last_bin_ts_ms = Gauge(
    "macro_sync_last_bin_ts_ms",
    "Macro sync: latest observed bin_ts (ms) per series",
    ["key"],
)

# RetryScheduler loop contract (TASK24)
c_retry_scheduler_no_loop_total = Counter(
    "retry_scheduler_no_loop_total",
    "RetryScheduler schedule attempts without a running event loop (fail-fast contract)",
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

def inc_warmup_block(domain: str, reason: str) -> None:
    c_warmup_block_total.labels(domain=domain, reason=reason).inc()

def inc_data_quality_drop(domain: str, reason: str) -> None:
    c_data_quality_drop_total.labels(domain=domain, reason=reason).inc()

def inc_data_quality_bad_dt(domain: str) -> None:
    c_data_quality_bad_dt_total.labels(domain=domain).inc()


def inc_macro_sync_ooo_dropped(key: str) -> None:
    c_macro_sync_ooo_dropped_total.labels(key=str(key)).inc()


def inc_macro_sync_ooo_reordered(key: str) -> None:
    c_macro_sync_ooo_reordered_total.labels(key=str(key)).inc()


def set_macro_sync_last_bin_ts_ms(key: str, last_bin_ts_ms: int) -> None:
    g_macro_sync_last_bin_ts_ms.labels(key=str(key)).set(float(last_bin_ts_ms))

def inc_retry_scheduler_no_loop() -> None:
    c_retry_scheduler_no_loop_total.inc()


def inc_order_state(status: str) -> None:
    c_order_state_total.labels(status=status).inc()


def observe_order_lifecycle(duration_seconds: float) -> None:
    h_order_lifecycle_seconds.observe(duration_seconds)


# Task 17: Config Contract Violation Metric
c_config_contract_violation_total = Counter(
    "config_contract_violation_total", 
    "Total configuration contract violations (blocking)", 
    ["path", "symbol"]
)

def inc_config_contract_violation(path: str, symbol: str = "unknown") -> None:
    """Increment the config contract violation counter."""
    c_config_contract_violation_total.labels(path=path, symbol=symbol).inc()

# Task CFG-REJECT-INTEGRATE-01: Decision Blocked Metric
c_decision_blocked_total = Counter(
    "decision_blocked_total",
    "Decision blocked triggers (pipeline halted)",
    ["stage", "reason_code"]
)

def inc_decision_blocked(stage: str, reason_code: str) -> None:
    c_decision_blocked_total.labels(stage=stage, reason_code=reason_code).inc()


# Validated Alpha Search Metrics (TASK-ALPHA-FREEZE-02)
c_alpha_model_errors_total = Counter(
    "alpha_model_errors_total",
    "Total exceptions raised during alpha model calculation",
    ["model"]
)

def inc_alpha_model_error(model: str) -> None:
    c_alpha_model_errors_total.labels(model=model).inc()
