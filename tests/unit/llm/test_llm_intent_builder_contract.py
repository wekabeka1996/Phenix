"""
test_llm_intent_builder_contract.py

Tests IntentBuilder._resolve_order_policy() for llm_microstructure.

AUDIT FINDINGS verified:
  - LIMIT + GTC resolved from profile (not from external request)
  - tf_sec=300 maps to valid_for_ms=1200000ms (ttl_by_tf_sec[300]=1200)
  - tf_sec=60 would REJECT if not in ttl_by_tf_sec (fail-closed)
  - ORDER_TYPE_MISSING rejects if entry_order_type absent from profile
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons


def _make_config_for_builder(
    order_type: str = "LIMIT",
    tif: str = "GTC",
    supported_types=None,
    supported_tifs=None,
    pe_ttl_enabled: bool = True,
    ttl_by_tf_sec: dict | None = None,
    reject_unknown_tf: bool = True,
) -> MagicMock:
    if supported_types is None:
        supported_types = ["LIMIT", "MARKET"]
    if supported_tifs is None:
        supported_tifs = ["GTC", "GTX", "IOC", "FOK"]
    if ttl_by_tf_sec is None:
        ttl_by_tf_sec = {180: 600, 300: 1200, 900: 1800}

    cfg = MagicMock()

    # llm_microstructure execution profile
    exec_cfg = MagicMock()
    exec_cfg.entry_order_type = order_type
    exec_cfg.entry_tif = tif
    strat_cfg = MagicMock()
    strat_cfg.execution = exec_cfg
    strat_cfg.decision.kelly.fraction = "0.1"
    strat_cfg.decision.retry_ttl_ms = 30000
    cfg.strategies.llm_microstructure = strat_cfg
    cfg.strategies.aurora = strat_cfg  # fallback

    # Order capabilities
    caps = MagicMock()
    caps.supported_order_types = supported_types
    caps.supported_tif = supported_tifs
    cfg.domains.execution_position.order_capabilities = caps

    # Pending entry TTL
    pe_ttl = MagicMock()
    pe_ttl.enabled = pe_ttl_enabled
    pe_ttl.ttl_by_tf_sec = ttl_by_tf_sec
    pe_ttl.reject_unknown_tf = reject_unknown_tf
    cfg.domains.execution_position.pending_entry_ttl = pe_ttl

    return cfg


def _make_builder(config) -> tuple:
    """Create IntentBuilder with minimal mock dependencies + capture reject calls."""
    from apps.reference.domains.decision_making.intent.builder import IntentBuilder
    from apps.reference.core.time.clock import LiveClock

    rejected = []

    def fake_emit_rejected(**kw):
        rejected.append(kw)

    builder = IntentBuilder(
        fsm=MagicMock(),
        clock=MagicMock(),
        config=config,
        tca_prefs={"max_slippage_bps": 5,
                   "max_latency_ms": 100, "maker_preference": "maker"},
        risk_budgets={"trade_cvar95_max_bps": "50",
                      "session_cvar95_max_bps": "200"},
        safe_decimal_fn=lambda v, default=None: None,
        check_strategy_arbitration_fn=lambda *a, **kw: {
            "allowed": True, "reason": ""},
        warmup_gate_fn=lambda **kw: False,  # never blocks
        emit_rejected_fn=fake_emit_rejected,
        record_blocked_fn=lambda sym: None,
        record_accepted_fn=lambda sym: None,
        emit_deferred_fn=lambda **kw: None,
        get_side_bias_params_fn=lambda sym: (0.5, 60, 0.5, 5),
        side_intent_window={},
        logger=MagicMock(),
    )
    return builder, rejected


class TestIntentBuilderOrderPolicyForLLM:
    """
    H3 AUDIT: IntentBuilder._resolve_order_policy() for 'llm_microstructure'.
    """

    def test_resolves_limit_gtc_from_profile(self):
        """
        Profile declares entry_order_type=LIMIT, entry_tif=GTC.
        IntentBuilder must resolve this from config.strategies.llm_microstructure,
        ignoring any external request order policy.
        """
        config = _make_config_for_builder(order_type="LIMIT", tif="GTC")
        builder, rejected = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="1000PEPEUSDT",
            strategy_id="llm_microstructure",
            side="BUY",
            rid="test-rid",
            tf_sec=300,  # mapper emits 300
            reduce_only=False,
            why_chain=[],
        )

        assert order_type == "LIMIT", f"Expected LIMIT, got {order_type!r}"
        assert tif == "GTC", f"Expected GTC, got {tif!r}"
        assert len(rejected) == 0, f"Unexpected rejection: {rejected}"

    def test_tf_sec_300_resolves_valid_for_ms_1200000(self):
        """
        AUDIT FACT-2: ttl_by_tf_sec has 300:1200 → valid_for_ms=1200000ms.
        tf_sec=300 from mapper does NOT cause a rejection at built intent.
        """
        config = _make_config_for_builder(
            ttl_by_tf_sec={180: 600, 300: 1200, 900: 1800},
            reject_unknown_tf=True,
        )
        builder, rejected = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="1000PEPEUSDT",
            strategy_id="llm_microstructure",
            side="BUY",
            rid="test-rid",
            tf_sec=300,
            reduce_only=False,
            why_chain=[],
        )

        assert valid_for_ms == 1_200_000, (
            f"Expected valid_for_ms=1200000 for tf_sec=300, got {valid_for_ms!r}. "
            "H3 DISPROVEN: tf_sec=300 is NOT a runtime blocker."
        )
        assert len(rejected) == 0

    def test_tf_sec_60_rejects_if_not_in_ttl_map(self):
        """
        AUDIT: If mapper were fixed to tf_sec=60, but ttl_by_tf_sec has no entry for 60,
        the builder would reject with MISSING_TF_SEC (fail-closed).
        This shows that fixing the tf_sec drift REQUIRES also updating ttl_by_tf_sec.
        """
        config = _make_config_for_builder(
            ttl_by_tf_sec={180: 600, 300: 1200, 900: 1800},  # 60 is absent
            reject_unknown_tf=True,
        )
        builder, rejected = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="1000PEPEUSDT",
            strategy_id="llm_microstructure",
            side="BUY",
            rid="test-rid",
            tf_sec=60,  # fixed mapper value
            reduce_only=False,
            why_chain=[],
        )

        assert order_type is None, (
            "Expected rejection (order_type=None) when tf_sec=60 not in ttl_by_tf_sec. "
            "Fix: add '60: 300' to ttl_by_tf_sec alongside mapper tf_sec fix."
        )
        assert len(rejected) == 1
        assert str(rejected[0].get("reason_code", "")
                   ) == NormalizedRejectReasons.MISSING_TF_SEC

    def test_tf_sec_60_passes_if_added_to_ttl_map(self):
        """
        AUDIT: If both mapper (tf_sec=60) and ttl_by_tf_sec ({60: 300}) are fixed,
        the builder passes and valid_for_ms=300000ms (5 minutes).
        """
        config = _make_config_for_builder(
            ttl_by_tf_sec={60: 300, 180: 600,
                           300: 1200, 900: 1800},  # 60 added
            reject_unknown_tf=True,
        )
        builder, rejected = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="1000PEPEUSDT",
            strategy_id="llm_microstructure",
            side="BUY",
            rid="test-rid",
            tf_sec=60,
            reduce_only=False,
            why_chain=[],
        )

        assert order_type == "LIMIT"
        assert tif == "GTC"
        assert valid_for_ms == 300_000, (
            f"Expected valid_for_ms=300000 for tf_sec=60 with ttl=300s, got {valid_for_ms!r}"
        )
        assert len(rejected) == 0

    def test_missing_order_type_in_profile_rejects(self):
        """
        Fail-closed: if llm_microstructure profile lacks entry_order_type, builder rejects.
        """
        config = _make_config_for_builder(
            order_type=None)  # type: ignore[arg-type]
        builder, rejected = _make_builder(config)

        order_type, tif, valid_for_ms = builder._resolve_order_policy(
            symbol="1000PEPEUSDT",
            strategy_id="llm_microstructure",
            side="BUY",
            rid="test-rid",
            tf_sec=300,
            reduce_only=False,
            why_chain=[],
        )

        assert order_type is None
        assert len(rejected) == 1
        rcode = str(rejected[0].get("reason_code", ""))
        assert rcode == NormalizedRejectReasons.ORDER_TYPE_MISSING
