"""
DM-EVT-ORDER-REJECTED-CONTRACT-HARDENING-PACK

Tests for canonical normalization of EVT:ORDER_REJECTED payloads
and fail-closed behavior on malformed / empty / unrecognized reasons.

Covers:
  1. payload with reject_reason only
  2. payload with reason only (production emitter)
  3. payload with reason_code + reason_text (fsm.py ADAPTER_ERROR path)
  4. payload with unrelated reason — no unsafe fallback
  5. malformed / empty / partial payload — fail-closed
  6. POST_ONLY → gtx_retries increments
  7. gtx_retry_max exceeded → fallback to MARKET bookkeeping
  8. unrecognized reason does NOT trigger false MARKET fallback
  9. MAKER_ONLY path covered separately
 10. table-driven spellings for post-only / maker-only reject
"""

import pytest
from unittest.mock import MagicMock
from vfoundation.core.protocol import Message
from apps.reference.domains.decision_making.md_amr_handler import MDAMRHandler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class DummyExecution:
    gtx_retry_max = 2
    gtx_fallback_to_market = True


class DummyMDAMRConfig:
    enabled = False
    timeframe_sec = 900
    defer_ttl_sec = 60
    execution = DummyExecution()
    assets = {}


class DummyStrategies:
    md_amr = DummyMDAMRConfig()


class DummyConfig:
    execution = DummyExecution()
    strategies = DummyStrategies()


def _make_handler() -> MDAMRHandler:
    config = DummyConfig()
    fsm_mock = MagicMock()
    h = MDAMRHandler(config=config, fsm=fsm_mock)
    h._enabled = True
    h._enabled_symbols = {"BTCUSDT"}
    return h


def _evt(pld: dict) -> Message:
    return Message(
        name="EVT:ORDER_REJECTED",
        op="EVT",
        verb="ORDER_REJECTED",
        src="execution_position",
        dst="decision_making",
        pld=pld,
    )


# ===========================================================================
# A. Unit tests for _normalize_order_reject_reason (static)
# ===========================================================================

class TestNormalizeOrderRejectReason:
    """Direct unit tests for the canonical normalization function."""

    norm = staticmethod(MDAMRHandler._normalize_order_reject_reason)

    # --- 1. reject_reason only ---
    def test_reject_reason_field_used(self):
        assert self.norm({"reject_reason": "POST_ONLY_REJECT"}
                         ) == "POST_ONLY_REJECT"

    def test_reject_reason_whitespace_trimmed(self):
        assert self.norm(
            {"reject_reason": "  post_only_reject  "}) == "POST_ONLY_REJECT"

    # --- 2. reason only (production emitter) ---
    def test_reason_field_used(self):
        assert self.norm({"reason": "MAKER_ONLY_REJECT"}
                         ) == "MAKER_ONLY_REJECT"

    def test_reason_field_lowercase_uppercased(self):
        assert self.norm({"reason": "maker_only_reject"}
                         ) == "MAKER_ONLY_REJECT"

    # --- 3. reason_code + reason_text ---
    def test_reason_code_only(self):
        assert self.norm({"reason_code": "ADAPTER_ERROR"}) == "ADAPTER_ERROR"

    def test_reason_code_with_reason_text(self):
        result = self.norm(
            {"reason_code": "ADAPTER_ERROR", "reason_text": "timeout"})
        assert result == "ADAPTER_ERROR: TIMEOUT"

    def test_reason_code_empty_text_ignored(self):
        result = self.norm({"reason_code": "ADAPTER_ERROR", "reason_text": ""})
        assert result == "ADAPTER_ERROR"

    # --- Priority: reject_reason wins over reason ---
    def test_reject_reason_takes_precedence_over_reason(self):
        result = self.norm(
            {"reject_reason": "POST_ONLY_REJECT", "reason": "MAKER_ONLY_REJECT"})
        assert result == "POST_ONLY_REJECT"

    def test_reason_takes_precedence_over_reason_code(self):
        result = self.norm({"reason": "MAKER_ONLY_REJECT",
                           "reason_code": "ADAPTER_ERROR"})
        assert result == "MAKER_ONLY_REJECT"

    # --- 5. malformed / empty / partial ---
    def test_empty_dict(self):
        assert self.norm({}) == ""

    def test_reject_reason_empty_string_falls_through(self):
        assert self.norm({"reject_reason": ""}) == ""

    def test_reject_reason_none_falls_through_to_reason(self):
        assert self.norm({"reject_reason": None, "reason": "X"}) == "X"

    def test_reject_reason_whitespace_only_falls_through(self):
        assert self.norm({"reject_reason": "   ", "reason": "Y"}) == "Y"

    def test_all_fields_empty(self):
        assert self.norm(
            {"reject_reason": "", "reason": "", "reason_code": ""}) == ""

    def test_reason_code_whitespace_only(self):
        assert self.norm({"reason_code": "  ", "reason_text": "  "}) == ""

    def test_non_string_reject_reason_coerced(self):
        assert self.norm({"reject_reason": 42}) == "42"

    def test_non_string_reason_coerced(self):
        assert self.norm({"reason": 123}) == "123"


# ===========================================================================
# B. Integration tests: _on_order_rejected wired through canonical normalizer
# ===========================================================================

class TestOnOrderRejectedIntegration:
    """Verify full handler path uses normalized reason for GTX retry logic."""

    @pytest.fixture
    def handler(self):
        return _make_handler()

    # --- 6. POST_ONLY via `reason` field (production emitter) → retries grow ---
    def test_reason_field_post_only_increments_retries(self, handler):
        evt = _evt({"symbol": "BTCUSDT", "reason": "POST_ONLY_REJECT"})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT") == 1
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT") == 2

    # --- 9. MAKER_ONLY via `reason` field → retries grow ---
    def test_reason_field_maker_only_increments_retries(self, handler):
        evt = _evt({"symbol": "BTCUSDT", "reason": "MAKER_ONLY_REJECT"})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT") == 1

    # --- 7. gtx_retry_max exceeded → fallback resets counter ---
    def test_reason_field_gtx_fallback_resets_retries(self, handler):
        evt = _evt({"symbol": "BTCUSDT", "reason": "MAKER_ONLY_REJECT"})
        handler._on_order_rejected(evt)  # retry=1
        handler._on_order_rejected(evt)  # retry=2
        handler._on_order_rejected(evt)  # exceeds max → fallback
        assert handler._gtx_retries.get("BTCUSDT") == 0

    # --- 4 + 8. unrelated reason does NOT trigger retry or MARKET fallback ---
    def test_unrelated_reason_no_retry(self, handler):
        evt = _evt({"symbol": "BTCUSDT", "reason": "INSUFFICIENT_FUNDS"})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT", 0) == 0

    def test_adapter_error_reason_code_no_retry(self, handler):
        evt = _evt(
            {"symbol": "BTCUSDT", "reason_code": "ADAPTER_ERROR", "reason_text": "timeout"})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT", 0) == 0

    # --- 5. malformed payload → fail-closed, no retry ---
    def test_empty_payload_fail_closed(self, handler):
        evt = _evt({"symbol": "BTCUSDT"})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT", 0) == 0

    def test_none_reason_fail_closed(self, handler):
        evt = _evt({"symbol": "BTCUSDT", "reason": None})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT", 0) == 0

    def test_empty_string_reasons_fail_closed(self, handler):
        evt = _evt({"symbol": "BTCUSDT", "reject_reason": "", "reason": ""})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT", 0) == 0

    # --- reject_reason field still works (backward compat) ---
    def test_legacy_reject_reason_field_still_works(self, handler):
        evt = _evt({"symbol": "BTCUSDT", "reject_reason": "POST_ONLY_REJECT"})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT") == 1

    # --- no_fallback path ---
    def test_no_fallback_config_resets_retries(self, handler):
        handler._cfg.execution.gtx_fallback_to_market = False
        evt = _evt({"symbol": "BTCUSDT", "reason": "POST_ONLY_REJECT"})
        handler._gtx_retries["BTCUSDT"] = 2
        handler._on_order_rejected(evt)  # exceeds max, no fallback
        assert handler._gtx_retries.get("BTCUSDT") == 0


# ===========================================================================
# C. Table-driven: spellings of POST_ONLY / MAKER_ONLY across exchanges
# ===========================================================================

_POST_ONLY_MAKER_ONLY_SPELLINGS = [
    "MAKER_ONLY_REJECT",
    "POST_ONLY_REJECT",
    "MAKER_ONLY",
    "POST_ONLY",
    "post_only_reject",
    "maker_only_reject",
    "MAKER_ONLY_ENFORCEMENT_FAIL",
]
# NOTE: Raw Binance error text like "Post Only order will be rejected" is NOT
# a valid reason string at this layer. execution_position maps Binance error
# codes (-5022) to canonical MAKER_ONLY_REJECT before emitting ORDER_REJECTED.
# Matching on free-form exchange text would be an unsafe heuristic.


class TestPostOnlyMakerOnlySpellings:
    """Table-driven: all known spellings must trigger GTX retry path."""

    @pytest.fixture
    def handler(self):
        return _make_handler()

    @pytest.mark.parametrize("spelling", _POST_ONLY_MAKER_ONLY_SPELLINGS)
    def test_spelling_triggers_retry(self, handler, spelling):
        evt = _evt({"symbol": "BTCUSDT", "reason": spelling})
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT") == 1, (
            f"Spelling {spelling!r} did not trigger GTX retry"
        )


# ===========================================================================
# D. Table-driven: reasons that must NOT trigger POST_ONLY/MAKER_ONLY path
# ===========================================================================

_SAFE_NON_GTX_REASONS = [
    "INSUFFICIENT_FUNDS",
    "RATE_LIMIT_EXCEEDED",
    "ADAPTER_ERROR",
    "UNKNOWN",
    "INTERNAL_ERROR",
    "",   # empty
    "42",  # numeric coerced
]


class TestSafeNonGtxReasons:
    """These reasons must NOT trigger GTX retry / MARKET fallback."""

    @pytest.fixture
    def handler(self):
        return _make_handler()

    @pytest.mark.parametrize("reason_str", _SAFE_NON_GTX_REASONS)
    def test_reason_does_not_trigger_retry(self, handler, reason_str):
        pld = {"symbol": "BTCUSDT"}
        if reason_str:
            pld["reason"] = reason_str
        evt = _evt(pld)
        handler._on_order_rejected(evt)
        assert handler._gtx_retries.get("BTCUSDT", 0) == 0, (
            f"Reason {reason_str!r} incorrectly triggered GTX retry"
        )
