"""
Smoke test for logs_errors_summary.py

Tests basic functionality with sample log data.
"""

import pytest
import tempfile
import json
from pathlib import Path
import sys

# Add tools to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))

from logs_errors_summary import LogParser


def test_parse_plain_log_format():
    """Test parsing standard Python logging format."""
    parser = LogParser()
    
    sample_line = "2025-11-23 10:10:10,123 - apps.reference.domains.execution - ERROR - Failed to process order orderId=12345"
    
    parser.parse_plain_log_line(sample_line)
    
    assert len(parser.signatures) == 1
    sig = list(parser.signatures.values())[0]
    assert sig.level == "ERROR"
    assert sig.logger == "apps.reference.domains.execution"
    assert "orderId=<ID>" in sig.signature or "<ID>" in sig.signature
    assert sig.count == 1


def test_parse_jsonl_format():
    """Test parsing JSONL format."""
    parser = LogParser()
    
    sample_jsonl = '{"level": "ERROR", "logger": "execpos.runtime", "message": "Bracket creation failed for BTCUSDT"}'
    
    parser.parse_jsonl_line(sample_jsonl)
    
    assert len(parser.signatures) == 1
    sig = list(parser.signatures.values())[0]
    assert sig.level == "ERROR"
    assert sig.logger == "execpos.runtime"
    assert "Bracket creation failed" in sig.signature


def test_message_normalization():
    """Test that variable parts are normalized correctly."""
    parser = LogParser()
    
    # Test order ID normalization
    assert "<ID>" in parser.normalize_message("order_id=12345 failed")
    assert "<ID>" in parser.normalize_message("Order 67890 completed")
    
    # Test symbol normalization
    assert "<SYMBOL>" in parser.normalize_message("symbol=BTCUSDT price=50000")
    assert "<SYMBOL>" in parser.normalize_message("Trading ETHUSDT")
    
    # Test numeric normalization
    assert "<NUM>" in parser.normalize_message("price=12345.67 qty=0.001")
    

def test_duplicate_grouping():
    """Test that similar messages are grouped together."""
    parser = LogParser()
    
    line1 = "2025-11-23 10:10:10,123 - test.logger - ERROR - Order 111 failed"
    line2 = "2025-11-23 10:10:11,456 - test.logger - ERROR - Order 222 failed"
    line3 = "2025-11-23 10:10:12,789 - test.logger - ERROR - Order 333 failed"
    
    parser.parse_plain_log_line(line1)
    parser.parse_plain_log_line(line2)
    parser.parse_plain_log_line(line3)
    
    # Should be grouped into single signature
    assert len(parser.signatures) == 1
    sig = list(parser.signatures.values())[0]
    assert sig.count == 3


def test_error_vs_warning_separation():
    """Test that ERRORs and WARNINGs are counted separately."""
    parser = LogParser()
    
    error_line = "2025-11-23 10:10:10,123 - test - ERROR - Test error"
    warning_line = "2025-11-23 10:10:10,123 - test - WARNING - Test warning"
    
    parser.parse_plain_log_line(error_line)
    parser.parse_plain_log_line(warning_line)
    
    assert parser.error_count == 1
    assert parser.warning_count == 1
    assert len(parser.signatures) == 2


def test_get_results_structure():
    """Test that results are properly structured."""
    parser = LogParser()
    
    parser.parse_plain_log_line("2025-11-23 10:10:10,123 - test - ERROR - Test")
    parser.parse_plain_log_line("2025-11-23 10:10:10,123 - test - WARNING - Test")
    
    results = parser.get_results()
    
    assert "errors" in results
    assert "warnings" in results
    assert "summary" in results
    assert results["summary"]["total_errors"] == 1
    assert results["summary"]["total_warnings"] == 1
    assert results["summary"]["unique_error_signatures"] == 1
    assert results["summary"]["unique_warning_signatures"] == 1


def test_parse_file_integration():
    """Integration test with temporary log file."""
    parser = LogParser()
    
    # Create temp log file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write("2025-11-23 10:10:10,123 - test - ERROR - Error 1\n")
        f.write("2025-11-23 10:10:11,456 - test - ERROR - Error 1\n")
        f.write("2025-11-23 10:10:12,789 - test - WARNING - Warning 1\n")
        temp_path = Path(f.name)
    
    try:
        parser.parse_file(temp_path)
        
        assert parser.error_count == 2
        assert parser.warning_count == 1
        
        results = parser.get_results()
        assert len(results["errors"]) == 1
        assert len(results["warnings"]) == 1
        assert results["errors"][0]["count"] == 2
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
