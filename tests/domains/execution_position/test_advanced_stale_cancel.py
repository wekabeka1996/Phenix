"""
ADVANCED-STALE-CANCEL-01: Tests for 3-gate evidence-based regime cancel.

Gates tested:
  Gate 1 — Regime gate:  new_regime in per-order cancelable_regimes
                         (derived at placement: allowed_regimes ∩ may_cancel[side] − never_cancel)
                         Fallback if cancelable_regimes is None: may_cancel_regimes[side] − never_cancel
  Gate 2 — Age gate:     order age >= min_age_before_cancel_sec
  Gate 3 — Drift gate:   |current_price - limit_price| >= atr_mult * atr_14

fail-closed semantics: missing metadata or features cache → do NOT cancel.
"""
import time
import pytest
from decimal import Decimal
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.fsm import PendingEntryMeta
from apps.reference.domains.execution_position.watchdog import (
    OrderDeadline,
    OrderTimeoutType,
)


# ── Constants ────────────────────────────────────────────────────────────────
SYMBOL = "BTCUSDT"
ORDER_ID = "oid-1"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_deadline(symbol: str = SYMBOL, order_id: str = ORDER_ID) -> OrderDeadline:
    return OrderDeadline(
        order_id=order_id,
        client_order_id="cl-1",
        symbol=symbol,
        deadline_ms=99_999_999_999,
        timeout_type=OrderTimeoutType.FILL_TIMEOUT,
    )


def _make_adv_cfg(min_age_sec: int = 300, atr_mult: float = 0.5) -> MagicMock:
    """
    MagicMock shaped like AdvancedStaleCancelConfig.
    Uses self-consistent mock labels (BEAR_TREND/BULL_TREND) for unit-level gate tests.
    Canonical-label regression tests override may_cancel_regimes directly.
    """
    adv = MagicMock()
    adv.enabled = True
    adv.min_age_before_cancel_sec = min_age_sec
    adv.drift_away.atr_mult = atr_mult
    # Fallback Gate 1 path: may_cancel_regimes[side] − never_cancel
    adv.may_cancel_regimes = {
        "BUY": ["BEAR_TREND"],
        "SELL": ["BULL_TREND"],
    }
    adv.never_cancel_regimes = ["UNCERTAIN"]
    return adv


def _install_adv_cfg(fsm, adv_cfg) -> None:
    """Wire advanced_stale_cancel config into fsm.config (in-place)."""
    pe_ttl = MagicMock()
    pe_ttl.enabled = True
    pe_ttl.cancel_on_regime_change = True
    pe_ttl.advanced_stale_cancel = adv_cfg
    fsm.config.domains.execution_position.pending_entry_ttl = pe_ttl
    fsm.config.basis_tf_sec = 300


def _old_meta(
    side: str = "BUY",
    limit_price: str = "95000.0",
    cancelable_regimes=None,
) -> PendingEntryMeta:
    """Entry placed at epoch+1ms — age_ms >> any reasonable min_age."""
    return PendingEntryMeta(
        symbol=SYMBOL,
        side=side,
        limit_price=limit_price,
        placed_at_ms=1000,
        tf_sec=300,
        cancelable_regimes=cancelable_regimes,
    )


def _features_snap(price: str = "97000.0", atr_14: str = "1000.0") -> dict:
    return {
        "symbol": SYMBOL,
        "tf_sec": 300,
        "features": {
            "price": price,
            "atr_14": atr_14,
        },
    }


def _setup(fsm, adv_cfg, meta=None, features=None) -> MagicMock:
    """
    Common test setup:
      - Install config
      - Wire watchdog with one pending order
      - Optionally populate metadata + features cache
      - Replace _cancel_pending_entries_for_symbol with a MagicMock

    Returns the cancel MagicMock.
    """
    _install_adv_cfg(fsm, adv_cfg)
    fsm.watchdog.pending_orders = {ORDER_ID: _make_deadline()}
    fsm.watchdog.acked_orders = {}
    if meta is not None:
        fsm._pending_entry_meta[ORDER_ID] = meta
    if features is not None:
        fsm._last_features_cache[SYMBOL] = features
    cancel_mock = MagicMock()
    fsm._cancel_pending_entries_for_symbol = cancel_mock
    return cancel_mock


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1 — Regime gate (via fallback Path B: may_cancel_regimes[side])
# These tests use self-consistent mock labels (BEAR_TREND) to isolate gate logic.
# ─────────────────────────────────────────────────────────────────────────────

def test_uncertain_never_cancels(fsm_harness):
    """
    Gate 1 blocks: UNCERTAIN is not in may_cancel_regimes["BUY"] = ["BEAR_TREND"],
    and it is also in never_cancel_regimes.
    Even if age and drift gates would both pass, no cancel should fire.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg()
    # Age: very old; drift: 2000 > threshold 500 — both would pass
    cancel_mock = _setup(fsm, adv_cfg, meta=_old_meta(),
                         features=_features_snap())

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="UNCERTAIN")

    cancel_mock.assert_not_called()


def test_regime_not_in_may_cancel_no_cancel(fsm_harness):
    """
    Gate 1 blocks: MEAN_REVERSION is NOT in may_cancel_regimes["BUY"] = ["BEAR_TREND"].
    Cancel must not fire.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg()
    cancel_mock = _setup(fsm, adv_cfg, meta=_old_meta(),
                         features=_features_snap())

    fsm._evaluate_advanced_stale_cancel(
        symbol=SYMBOL, new_regime="MEAN_REVERSION")

    cancel_mock.assert_not_called()


# ── Gate 2 — Age gate ────────────────────────────────────────────────────────

def test_age_gate_blocks_fresh_order(fsm_harness):
    """
    Gate 1 passes (BEAR_TREND is in may_cancel_regimes for BUY).
    Gate 2 blocks: order placed only 1 second ago — below min_age of 300 s.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg(min_age_sec=300)

    # Placed ≈1 second ago
    fresh_placed_ms = int(time.time() * 1000) - 1_000
    fresh_meta = PendingEntryMeta(
        symbol=SYMBOL,
        side="BUY",
        limit_price="95000.0",
        placed_at_ms=fresh_placed_ms,
        tf_sec=300,
    )
    cancel_mock = _setup(fsm, adv_cfg, meta=fresh_meta,
                         features=_features_snap())

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="BEAR_TREND")

    cancel_mock.assert_not_called()


# ── Gate 3 — Drift gate ───────────────────────────────────────────────────────

def test_no_features_cache_fail_closed(fsm_harness):
    """
    Gates 1+2 pass (matching regime, old order).
    Gate 3 is fail-closed: features cache is empty → do NOT cancel.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg()
    # features=None → _last_features_cache stays empty
    cancel_mock = _setup(fsm, adv_cfg, meta=_old_meta(), features=None)

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="BEAR_TREND")

    cancel_mock.assert_not_called()


def test_drift_too_small_no_cancel(fsm_harness):
    """
    Gates 1+2 pass.
    Gate 3 blocks: drift = 10 < threshold = atr_14 * atr_mult = 1000 * 0.5 = 500.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg(atr_mult=0.5)
    # limit = 95000, current = 95010 → drift_BUY = 10 < threshold 500
    cancel_mock = _setup(
        fsm,
        adv_cfg,
        meta=_old_meta("BUY", "95000.0"),
        features=_features_snap(price="95010.0", atr_14="1000.0"),
    )

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="BEAR_TREND")

    cancel_mock.assert_not_called()


# ── All gates pass ────────────────────────────────────────────────────────────

def test_all_gates_pass_cancel_fires(fsm_harness):
    """
    All 3 gates pass (fallback Path B — cancelable_regimes is None):
      Gate 1: BEAR_TREND in may_cancel_regimes["BUY"]
      Gate 2: order placed at epoch+1ms → age >> 300 s
      Gate 3: drift = 2 000 > threshold = 1000 * 0.5 = 500

    Expected: _cancel_pending_entries_for_symbol called with
      reason="CANCEL_STALE_REGIME_ADVANCED" and filter_order_ids containing ORDER_ID.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg(atr_mult=0.5)
    # limit = 95000, current = 97000 → drift_BUY = 2000 > threshold 500
    cancel_mock = _setup(
        fsm,
        adv_cfg,
        meta=_old_meta("BUY", "95000.0"),
        features=_features_snap(price="97000.0", atr_14="1000.0"),
    )

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="BEAR_TREND")

    cancel_mock.assert_called_once()
    kwargs = cancel_mock.call_args.kwargs
    assert kwargs.get("reason") == "CANCEL_STALE_REGIME_ADVANCED", (
        f"Expected reason='CANCEL_STALE_REGIME_ADVANCED', got {kwargs.get('reason')!r}"
    )
    filter_ids = kwargs.get("filter_order_ids")
    assert filter_ids is not None, "filter_order_ids must be passed"
    assert ORDER_ID in filter_ids, (
        f"Expected {ORDER_ID!r} in filter_order_ids, got {filter_ids!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Regression: canonical regime label matching (Path B — fallback)
# ─────────────────────────────────────────────────────────────────────────────
# These tests use the REAL canonical labels (TREND_DOWN / TREND_UP) from
# RegimeLabel enum.  If someone introduces a label namespace mismatch again,
# these tests will catch it.

def test_canonical_trend_down_invalidates_buy_fallback(fsm_harness):
    """
    Regression (fallback path): TREND_DOWN must pass Gate 1 for a BUY order
    when cancelable_regimes is None (no allowed_regimes in payload).
    Protects against BEAR_TREND vs TREND_DOWN label drift.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg()
    adv_cfg.may_cancel_regimes = {"BUY": ["TREND_DOWN"], "SELL": ["TREND_UP"]}
    adv_cfg.never_cancel_regimes = ["UNCERTAIN"]
    # cancelable_regimes=None → fallback to may_cancel_regimes
    cancel_mock = _setup(
        fsm,
        adv_cfg,
        meta=_old_meta("BUY", "95000.0", cancelable_regimes=None),
        features=_features_snap(price="97000.0", atr_14="1000.0"),
    )

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="TREND_DOWN")

    cancel_mock.assert_called_once()
    assert cancel_mock.call_args.kwargs.get("reason") == "CANCEL_STALE_REGIME_ADVANCED"
    assert ORDER_ID in cancel_mock.call_args.kwargs.get("filter_order_ids", set())


def test_canonical_trend_up_invalidates_sell_fallback(fsm_harness):
    """
    Regression (fallback path): TREND_UP must pass Gate 1 for a SELL order.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg()
    adv_cfg.may_cancel_regimes = {"BUY": ["TREND_DOWN"], "SELL": ["TREND_UP"]}
    adv_cfg.never_cancel_regimes = ["UNCERTAIN"]
    # SELL order: drift = limit - current (price fell away from sell limit)
    cancel_mock = _setup(
        fsm,
        adv_cfg,
        meta=_old_meta("SELL", "97000.0", cancelable_regimes=None),
        features=_features_snap(price="94000.0", atr_14="1000.0"),
    )

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="TREND_UP")

    cancel_mock.assert_called_once()
    assert cancel_mock.call_args.kwargs.get("reason") == "CANCEL_STALE_REGIME_ADVANCED"
    assert ORDER_ID in cancel_mock.call_args.kwargs.get("filter_order_ids", set())


# ─────────────────────────────────────────────────────────────────────────────
# Per-order cancelable_regimes (Path A — derived from allowed_regimes)
# ─────────────────────────────────────────────────────────────────────────────

def test_per_order_path_a_cancel_fires(fsm_harness):
    """
    Path A: cancelable_regimes is pre-computed and stored in meta.
    TREND_DOWN in cancelable_regimes → all gates pass → cancel fires.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg(atr_mult=0.5)
    # cancelable_regimes explicitly set (as if derived from allowed_regimes at placement)
    cancel_mock = _setup(
        fsm,
        adv_cfg,
        meta=_old_meta("BUY", "95000.0", cancelable_regimes=["TREND_DOWN"]),
        features=_features_snap(price="97000.0", atr_14="1000.0"),
    )

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="TREND_DOWN")

    cancel_mock.assert_called_once()
    assert cancel_mock.call_args.kwargs.get("reason") == "CANCEL_STALE_REGIME_ADVANCED"
    assert ORDER_ID in cancel_mock.call_args.kwargs.get("filter_order_ids", set())


def test_per_order_path_a_empty_cancelable_never_cancels(fsm_harness):
    """
    Path A: cancelable_regimes is an empty list (e.g. mean-reversion-only symbol
    whose allowed_regimes ∩ may_cancel = {}).
    TREND_DOWN event does NOT cancel even if may_cancel_regimes would allow it —
    because the per-order result is empty.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg(atr_mult=0.5)
    # Empty cancelable_regimes = intersection was empty at placement time
    cancel_mock = _setup(
        fsm,
        adv_cfg,
        meta=_old_meta("BUY", "95000.0", cancelable_regimes=[]),
        features=_features_snap(price="97000.0", atr_14="1000.0"),
    )

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="TREND_DOWN")

    cancel_mock.assert_not_called()


def test_per_order_path_a_regime_not_in_cancelable(fsm_harness):
    """
    Path A: cancelable_regimes = ["TREND_DOWN"] (single regime).
    TREND_UP event must NOT cancel the BUY order.
    """
    fsm, _bus, _cfg = fsm_harness
    adv_cfg = _make_adv_cfg(atr_mult=0.5)
    cancel_mock = _setup(
        fsm,
        adv_cfg,
        meta=_old_meta("BUY", "95000.0", cancelable_regimes=["TREND_DOWN"]),
        features=_features_snap(price="97000.0", atr_14="1000.0"),
    )

    fsm._evaluate_advanced_stale_cancel(symbol=SYMBOL, new_regime="TREND_UP")

    cancel_mock.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Regression: Pydantic rejects phantom regime labels at config load time
# ─────────────────────────────────────────────────────────────────────────────

def test_pydantic_rejects_phantom_regime_label():
    """
    Regression: AdvancedStaleCancelConfig must reject labels absent from
    RegimeLabel enum (e.g. BEAR_TREND, BULL_TREND) at Pydantic construction time.
    This catches config drift before it silently disables the cancel policy.
    """
    from pydantic import ValidationError
    from apps.reference.config_models import AdvancedStaleCancelConfig

    with pytest.raises(ValidationError, match="Unknown regime label"):
        AdvancedStaleCancelConfig(
            enabled=True,
            min_age_before_cancel_sec=300,
            may_cancel_regimes={"BUY": ["BEAR_TREND"]},  # phantom label
        )


def test_pydantic_rejects_uncertain_in_may_cancel():
    """
    Regression: UNCERTAIN must not be allowed in may_cancel_regimes.
    """
    from pydantic import ValidationError
    from apps.reference.config_models import AdvancedStaleCancelConfig

    with pytest.raises(ValidationError, match="UNCERTAIN"):
        AdvancedStaleCancelConfig(
            enabled=True,
            min_age_before_cancel_sec=300,
            may_cancel_regimes={"BUY": ["UNCERTAIN"]},
        )


def test_pydantic_rejects_overlap_may_cancel_never_cancel():
    """
    Regression: overlapping labels in may_cancel_regimes and never_cancel_regimes
    must raise a validation error.
    """
    from pydantic import ValidationError
    from apps.reference.config_models import AdvancedStaleCancelConfig

    with pytest.raises(ValidationError, match="cannot be in both sets"):
        AdvancedStaleCancelConfig(
            enabled=True,
            min_age_before_cancel_sec=300,
            may_cancel_regimes={"BUY": ["TREND_DOWN"]},
            never_cancel_regimes=["UNCERTAIN", "TREND_DOWN"],  # overlap!
        )


def test_pydantic_accepts_canonical_labels():
    """
    Smoke test: AdvancedStaleCancelConfig must accept canonical labels without raising.
    """
    from apps.reference.config_models import AdvancedStaleCancelConfig

    cfg = AdvancedStaleCancelConfig(
        enabled=True,
        min_age_before_cancel_sec=300,
        may_cancel_regimes={"BUY": ["TREND_DOWN"], "SELL": ["TREND_UP"]},
        never_cancel_regimes=["UNCERTAIN", "MEAN_REVERSION", "LOW_VOLATILITY"],
    )
    assert cfg.may_cancel_regimes["BUY"] == ["TREND_DOWN"]
    assert cfg.may_cancel_regimes["SELL"] == ["TREND_UP"]
    assert "UNCERTAIN" in cfg.never_cancel_regimes
