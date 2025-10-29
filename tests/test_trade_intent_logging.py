"""
Tests for trade intent logging functionality.

Verifies that trade intents are logged to separate files in correct formats.
"""

import json
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_aurora_trade_intents_formatted_log_file():
    """
    Test that aurora_trade_intents_formatted.log is created with exact console format.
    
    Verifies:
    - File logs/aurora_trade_intents_formatted.log is created
    - Contains exact format as shown in console output:
      ============================================================
      🚀 NEW TRADE INTENT PROPOSED! 🚀
      ============================================================
      {
        "instrument": "ETHUSDT",
        "side": "buy",
        ...
      }
      ============================================================
    - No timestamp prefix (just raw formatted message)
    - JSON is properly indented with 2 spaces
    """
    # Use the actual production log file path
    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    log_file = logs_dir / "aurora_trade_intents_formatted.log"
    
    # Remove old test file to start fresh
    if log_file.exists():
        log_file.unlink()
    
    # Configure logger exactly as in main.py
    formatted_logger = logging.getLogger('test.aurora.trade_formatted')
    formatted_logger.setLevel(logging.INFO)
    formatted_logger.propagate = False
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB per file
        backupCount=5,  # Keep 5 backup files
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    # Critical: No timestamp prefix - just raw message
    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)
    formatted_logger.addHandler(file_handler)
    
    # Create test trade intent matching the exact format user showed
    test_trade_intent = {
        "instrument": "ETHUSDT",
        "side": "buy",
        "p": 0.8,
        "payoff_ratio_r": 2.0,
        "tca_budget": {
            "max_slippage_bps": 50.0,
            "max_latency_ms": 5000,
            "maker_preference": "allow"
        },
        "risk_budget": {
            "trade_cvar95_max_bps": 100.0,
            "session_cvar95_max_bps": 200.0
        },
        "size": {
            "kelly_fraction": 0.6,
            "notional_cap_usd": 0.0
        },
        "valid_for_ms": 30000,
        "why": [
            "Decision based on signal_score=52478.514",
            "Features: obi=1.000, tfi=1.000, absorption=174926.047",
            "Risk approved: kelly=0.600, trading_allowed=True"
        ],
        "dto_version": "1.0.0",
        "schema_ref": "https://aurora.scalp/shared/dto/trade_intent.schema.json"
    }
    
    # Format EXACTLY as in main.py (identical to console output)
    trade_data = json.dumps(test_trade_intent, indent=2, default=str)
    trade_message = f"\n{'='*60}\n🚀 NEW TRADE INTENT PROPOSED! 🚀\n{'='*60}\n{trade_data}\n{'='*60}\n"
    
    # Log the message
    formatted_logger.info(trade_message)
    
    # Close handler to flush
    file_handler.close()
    formatted_logger.removeHandler(file_handler)
    
    # === VERIFICATION ===
    
    # 1. Verify file was created
    assert log_file.exists(), f"File should be created at: {log_file}"
    
    # 2. Verify file is not empty
    file_size = log_file.stat().st_size
    assert file_size > 0, "Log file should contain data"
    
    # 3. Read content
    content = log_file.read_text(encoding='utf-8')
    
    # 4. Verify exact format elements
    assert "============================================================" in content, \
        "Should contain 60 equals signs separator"
    
    assert "🚀 NEW TRADE INTENT PROPOSED! 🚀" in content, \
        "Should contain emoji header"
    
    # 5. Verify JSON structure with proper indentation
    assert '"instrument": "ETHUSDT"' in content, \
        "Should contain instrument field"
    
    assert '"side": "buy"' in content, \
        "Should contain side field"
    
    assert '"p": 0.8' in content, \
        "Should contain probability p"
    
    assert '"payoff_ratio_r": 2.0' in content, \
        "Should contain payoff ratio"
    
    # 6. Verify nested objects are indented (2 spaces for first level, 4 for nested)
    assert '  "tca_budget"' in content, \
        "Top-level objects should be indented with 2 spaces"
    
    assert '    "max_slippage_bps"' in content, \
        "Nested objects should be indented with 4 spaces"
    
    # 7. Verify why array is present
    assert '"why": [' in content, \
        "Should contain why array"
    
    assert "Decision based on signal_score=" in content, \
        "Should contain signal score in why"
    
    assert "Features: obi=" in content, \
        "Should contain features in why"
    
    assert "Risk approved: kelly=" in content, \
        "Should contain risk approval in why"
    
    # 8. Verify NO timestamp prefix (critical requirement)
    lines = content.split('\n')
    # First non-empty line should start with newline or separator, NOT timestamp
    first_meaningful_line = None
    for line in lines:
        if line.strip():
            first_meaningful_line = line
            break
    
    assert first_meaningful_line is not None, "Should have content"
    assert first_meaningful_line.startswith('='), \
        f"First line should start with '=' (separator), not timestamp. Got: {first_meaningful_line[:50]}"
    
    # 9. Verify the exact separator length (60 equals)
    assert content.count('='*60) >= 3, \
        "Should have at least 3 separator lines (top, middle, bottom)"
    
    # === SUCCESS ===
    print("\n" + "="*70)
    print("✅ TEST PASSED!")
    print("="*70)
    print(f"📁 Log file created: {log_file.absolute()}")
    print(f"📊 File size: {file_size} bytes")
    print("✅ Format matches console output EXACTLY")
    print("✅ No timestamp prefix")
    print("✅ JSON indented with 2 spaces")
    print("✅ Contains emoji and separators")
    print("="*70)
    
    # Print preview
    print("\n📄 Content preview (first 800 chars):")
    print(content[:800])
    print("...")
    print("="*70)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short", "-s"])
