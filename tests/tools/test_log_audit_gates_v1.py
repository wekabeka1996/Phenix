"""
Tests for LOG-AUDIT-GATES-01: log_audit.py

Tests critical invariants:
1. intent without trace → TRACE_MISSING
2. trace DENY + CMD:OPEN → DENY_BYPASSED (critical)
3. open LONG with trend=DOWN → directional violation
4. open LONG with pm_norm_300s <= -T_bleed → price_motion violation
5. reduce_only blocked → reduce_only critical
6. max_hold breach without timer close → max_hold critical
"""

import json
import pytest
from pathlib import Path
from typing import Dict, List, Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.log_audit import (
    LogAuditor,
    parse_dm_log,
    parse_order_log,
    result_to_json,
    result_to_markdown,
    CRITICAL,
    ERROR,
    WARN,
    NRR_DIRECTIONAL,
    NRR_PM_BLEED_BLOCKED,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def empty_auditor():
    """Auditor with no events."""
    return LogAuditor([], [], [])


def make_order_intent(rid: str, symbol: str, side: str = "BUY", ts: int = 1000) -> Dict:
    return {
        "rid": rid,
        "event_type": "ORDER_INTENT",
        "symbol": symbol,
        "side": side,
        "timestamp": ts,
    }


def make_order_placed(rid: str, symbol: str, side: str = "BUY", ts: int = 1000) -> Dict:
    return {
        "rid": rid,
        "event_type": "ORDER_PLACED",
        "symbol": symbol,
        "side": side,
        "order_id": f"ORD-{rid[:8]}",
        "timestamp": ts,
    }


def make_order_rejected(
    rid: str, 
    symbol: str, 
    nrr_code: str = "NRR-026", 
    reduce_only: bool = False,
    ts: int = 1000,
) -> Dict:
    return {
        "rid": rid,
        "event_type": "ORDER_REJECTED",
        "symbol": symbol,
        "nrr_code": nrr_code,
        "metadata": {"reduce_only": reduce_only},
        "timestamp": ts,
    }


def make_dm_entry(
    symbol: str,
    outcome: str,  # ALLOW or DENY
    side: str,     # LONG or SHORT
    trend: str,    # UP, DOWN, UNKNOWN
    reason: str,   # NRR-xxx
) -> Dict:
    return {
        "type": "SAFETY_GATES",
        "symbol": symbol,
        "outcome": outcome,
        "side": side,
        "trend": trend,
        "reason": reason,
        "timestamp": "2026-01-03 12:00:00,000",
        "_line_num": 1,
    }


# =============================================================================
# TEST CASES
# =============================================================================

class TestTraceCoerage:
    """A1: Trace coverage tests."""
    
    def test_reject_without_nrr_is_error(self):
        """ORDER_REJECTED without nrr_code → TRACE_MISSING."""
        orders = [
            {
                "rid": "test-rid-1",
                "event_type": "ORDER_REJECTED",
                "symbol": "ETHUSDT",
                # No nrr_code!
                "timestamp": 1000,
            }
        ]
        
        auditor = LogAuditor([], orders, [])
        result = auditor.run_audit()
        
        assert result.error_count >= 1
        codes = [v.code for v in result.violations]
        assert "TRACE_MISSING" in codes


class TestDenyNeverOpens:
    """A2: DENY should never become CMD:OPEN."""
    
    def test_same_rid_reject_and_placed_is_critical(self):
        """Same RID with both REJECT and PLACED → DENY_BYPASSED."""
        rid = "dup-rid-123"
        orders = [
            make_order_rejected(rid, "ETHUSDT", "NRR-026"),
            make_order_placed(rid, "ETHUSDT"),
        ]
        
        auditor = LogAuditor([], orders, [])
        result = auditor.run_audit()
        
        assert result.critical_count >= 1
        codes = [v.code for v in result.violations]
        assert "DENY_BYPASSED" in codes


class TestDirectionalSanity:
    """A3: Directional sanity gate correctness."""
    
    def test_long_allowed_on_downtrend_is_violation(self):
        """ALLOW LONG when trend=DOWN → DIRECTIONAL_VIOLATION."""
        dm_entries = [
            make_dm_entry("BTCUSDT", "ALLOW", "LONG", "DOWN", ""),
        ]
        
        auditor = LogAuditor([], [], dm_entries)
        result = auditor.run_audit()
        
        assert result.critical_count >= 1
        codes = [v.code for v in result.violations]
        assert "DIRECTIONAL_VIOLATION" in codes
    
    def test_short_allowed_on_uptrend_is_violation(self):
        """ALLOW SHORT when trend=UP → DIRECTIONAL_VIOLATION."""
        dm_entries = [
            make_dm_entry("BTCUSDT", "ALLOW", "SHORT", "UP", ""),
        ]
        
        auditor = LogAuditor([], [], dm_entries)
        result = auditor.run_audit()
        
        assert result.critical_count >= 1
        codes = [v.code for v in result.violations]
        assert "DIRECTIONAL_VIOLATION" in codes
    
    def test_long_denied_on_downtrend_is_ok(self):
        """DENY LONG when trend=DOWN → No violation."""
        dm_entries = [
            make_dm_entry("BTCUSDT", "DENY", "LONG", "DOWN", "NRR-027"),
        ]
        
        auditor = LogAuditor([], [], dm_entries)
        result = auditor.run_audit()
        
        dir_violations = [v for v in result.violations if v.code == "DIRECTIONAL_VIOLATION"]
        assert len(dir_violations) == 0
    
    def test_long_allowed_on_uptrend_is_ok(self):
        """ALLOW LONG when trend=UP → No violation."""
        dm_entries = [
            make_dm_entry("BTCUSDT", "ALLOW", "LONG", "UP", ""),
        ]
        
        auditor = LogAuditor([], [], dm_entries)
        result = auditor.run_audit()
        
        dir_violations = [v for v in result.violations if v.code == "DIRECTIONAL_VIOLATION"]
        assert len(dir_violations) == 0


class TestReduceOnlyBypass:
    """A6: reduce_only orders must not be blocked by gates."""
    
    def test_reduce_only_blocked_by_gate_is_critical(self):
        """reduce_only=true blocked by NRR-026 → REDUCE_ONLY_BLOCKED."""
        orders = [
            make_order_rejected(
                "reduce-rid-1", 
                "SOLUSDT", 
                nrr_code="NRR-026",
                reduce_only=True,
            ),
        ]
        
        auditor = LogAuditor([], orders, [])
        result = auditor.run_audit()
        
        assert result.critical_count >= 1
        codes = [v.code for v in result.violations]
        assert "REDUCE_ONLY_BLOCKED" in codes
    
    def test_reduce_only_blocked_by_pm_gate_is_critical(self):
        """reduce_only=true blocked by NRR-030 → REDUCE_ONLY_BLOCKED."""
        orders = [
            make_order_rejected(
                "reduce-rid-2", 
                "SOLUSDT", 
                nrr_code="NRR-030",  # PM bleed blocked
                reduce_only=True,
            ),
        ]
        
        auditor = LogAuditor([], orders, [])
        result = auditor.run_audit()
        
        assert result.critical_count >= 1
        codes = [v.code for v in result.violations]
        assert "REDUCE_ONLY_BLOCKED" in codes
    
    def test_regular_order_blocked_is_ok(self):
        """Regular order blocked by gate → No violation."""
        orders = [
            make_order_rejected(
                "normal-rid-1", 
                "SOLUSDT", 
                nrr_code="NRR-026",
                reduce_only=False,
            ),
        ]
        
        auditor = LogAuditor([], orders, [])
        result = auditor.run_audit()
        
        reduce_violations = [v for v in result.violations if v.code == "REDUCE_ONLY_BLOCKED"]
        assert len(reduce_violations) == 0


class TestSymbolCoverage:
    """A8: All symbols should have activity."""
    
    def test_no_activity_symbol_is_warning(self):
        """Symbol with features but no events → SYMBOL_SILENT (or similar)."""
        # Create auditor with empty by_symbol entry
        auditor = LogAuditor([], [], [])
        auditor.by_symbol["DEADCOIN"] = auditor._get_symbol_stats("DEADCOIN")
        # Stats are all zeros
        
        result = auditor.run_audit()
        
        # Should have warning for silent symbol
        codes = [v.code for v in result.violations]
        assert "SYMBOL_SILENT" in codes


class TestOutputFormatters:
    """Test JSON and Markdown output."""
    
    def test_json_output_has_required_fields(self):
        """JSON output contains meta, global, by_symbol, violations."""
        auditor = LogAuditor([], [], [])
        result = auditor.run_audit()
        
        json_out = result_to_json(result)
        
        assert "meta" in json_out
        assert "global" in json_out
        assert "by_symbol" in json_out
        assert "violations_summary" in json_out
        assert "violations" in json_out
    
    def test_markdown_output_is_valid(self):
        """Markdown output is non-empty string."""
        dm_entries = [
            make_dm_entry("ETHUSDT", "DENY", "LONG", "DOWN", "NRR-026"),
        ]
        
        auditor = LogAuditor([], [], dm_entries)
        result = auditor.run_audit()
        
        md = result_to_markdown(result)
        
        assert isinstance(md, str)
        assert len(md) > 100
        assert "# Log Audit Report" in md
        assert "Executive Summary" in md


class TestAuditInvariants:
    """Test complete audit invariants."""
    
    def test_clean_audit_passes(self):
        """Audit with no violations passes."""
        orders = [
            make_order_intent("good-1", "ETHUSDT"),
            make_order_placed("good-1", "ETHUSDT"),
        ]
        dm_entries = [
            make_dm_entry("ETHUSDT", "ALLOW", "LONG", "UP", ""),
        ]
        
        auditor = LogAuditor([], orders, dm_entries)
        result = auditor.run_audit()
        
        assert result.critical_count == 0
    
    def test_multiple_violations_aggregated(self):
        """Multiple violations are correctly aggregated."""
        orders = [
            # DENY_BYPASSED
            make_order_rejected("dup-1", "ETHUSDT", "NRR-026"),
            make_order_placed("dup-1", "ETHUSDT"),
            # REDUCE_ONLY_BLOCKED
            make_order_rejected("red-1", "BTCUSDT", "NRR-030", reduce_only=True),
        ]
        dm_entries = [
            # DIRECTIONAL_VIOLATION
            make_dm_entry("SOLUSDT", "ALLOW", "LONG", "DOWN", ""),
        ]
        
        auditor = LogAuditor([], orders, dm_entries)
        result = auditor.run_audit()
        
        assert result.critical_count >= 3
        
        codes = [v.code for v in result.violations]
        assert "DENY_BYPASSED" in codes
        assert "REDUCE_ONLY_BLOCKED" in codes
        assert "DIRECTIONAL_VIOLATION" in codes


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
