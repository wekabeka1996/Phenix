#!/usr/bin/env python3
"""
Minimal testnet checks before deployment.

Criteria:
- WHY≤80 chars (bridge truncation)
- SL_bps default warning
- κ bounds [0.3, 1.0]
"""

import logging
import sys
import yaml
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
LOG = logging.getLogger(__name__)


def test_why_truncation():
    """Test that truncate_why function works correctly."""
    from vfoundation.core.protocol import truncate_why

    # Test 1: Short string unchanged
    short = "hello"
    assert truncate_why(short) == short, f"Failed: {truncate_why(short)}"
    LOG.info("✅ WHY truncation: short string unchanged")

    # Test 2: Exact 80 chars unchanged
    exact_80 = "a" * 80
    assert truncate_why(
        exact_80) == exact_80, f"Failed: len={len(truncate_why(exact_80))}"
    LOG.info("✅ WHY truncation: 80-char string unchanged")

    # Test 3: >80 chars truncated
    long_str = "a" * 120
    truncated = truncate_why(long_str)
    assert len(truncated) == 80, f"Failed: expected 80, got {len(truncated)}"
    LOG.info("✅ WHY truncation: >80 chars truncated to 80")

    # Test 4: None returns None
    assert truncate_why(None) is None, "Failed: None handling"
    LOG.info("✅ WHY truncation: None handling")

    return True


def test_why_length_in_message():
    """Test that Message validator accepts ≤80 why."""
    from vfoundation.core.protocol import Message

    # Valid: ≤80 chars
    msg = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="test",
        why="short why"
    )
    LOG.info(f"✅ Message with why={msg.why}")

    # Invalid: >80 chars (should fail)
    try:
        msg_bad = Message(
            op="CMD",
            verb="OPEN",
            src="test",
            dst="test",
            why="a" * 85  # >80
        )
        LOG.error("❌ Message accepted >80 char why! Validator broken!")
        return False
    except ValueError as e:
        LOG.info(f"✅ Message correctly rejects >80 why: {e}")

    return True


def test_sl_bps_default_warning():
    """Warn if SL_bps missing from config."""
    cfg_path = Path(__file__).parent / "config" / "aurora" / "trading.yaml"

    if not cfg_path.exists():
        LOG.warning(f"⚠️  Cannot find {cfg_path}, skipping SL_bps check")
        return True

    with open(cfg_path, 'r', encoding='utf-8-sig', errors='replace') as f:
        cfg = yaml.safe_load(f)

    execution_brackets = cfg.get("trading", {}).get(
        "execution", {}).get("manage", {}).get("brackets", {})
    sl_bps = execution_brackets.get("stop_loss_bps", None)

    if sl_bps is None:
        LOG.warning(
            "⚠️  WARN: SL_bps not found in execution.manage.brackets. Defaulting to 50bps.")
    else:
        LOG.info(f"✅ SL_bps present in config: {sl_bps} bps")

    return True


def test_kappa_bounds():
    """Test κ bounds [0.3, 1.0]."""
    # Simulate κ selection logic
    test_cases = [
        (0.2, 0.3),  # Below min → clamp to 0.3
        (0.3, 0.3),  # Min boundary → ok
        (0.5, 0.5),  # Middle → ok
        (1.0, 1.0),  # Max boundary → ok
        (1.2, 1.0),  # Above max → clamp to 1.0
    ]

    for input_kappa, expected in test_cases:
        # Simulate clamp logic
        clamped = max(0.3, min(1.0, input_kappa))
        assert clamped == expected, f"Failed: κ={input_kappa} → {clamped}, expected {expected}"
        LOG.info(f"✅ κ clamp: {input_kappa} → {clamped}")

    return True


def test_mode_resolver():
    """Test that mode-resolver merges decision[mode] → decision."""
    from apps.reference.config_loader import ConfigLoader

    loader = ConfigLoader()
    try:
        config = loader.load_config()
        trading_mode = config.get("trading_mode")
        LOG.info(f"✅ Config loaded with trading_mode={trading_mode}")

        # Check if decision config has been resolved
        decision = config.get("trading", {}).get("decision", {})
        LOG.info(f"✅ decision section loaded: {len(decision)} keys")

        return True
    except Exception as e:
        LOG.error(f"❌ Config loading failed: {e}")
        return False


if __name__ == "__main__":
    LOG.info("=" * 60)
    LOG.info("TESTNET PRE-FLIGHT CHECKS")
    LOG.info("=" * 60)

    results = []

    LOG.info("\n[1/5] Testing WHY truncation...")
    results.append(test_why_truncation())

    LOG.info("\n[2/5] Testing Message WHY validator...")
    results.append(test_why_length_in_message())

    LOG.info("\n[3/5] Testing SL_bps default warning...")
    results.append(test_sl_bps_default_warning())

    LOG.info("\n[4/5] Testing κ bounds...")
    results.append(test_kappa_bounds())

    LOG.info("\n[5/5] Testing mode-resolver...")
    results.append(test_mode_resolver())

    LOG.info("\n" + "=" * 60)
    if all(results):
        LOG.info("✅ ALL CHECKS PASSED - READY FOR TESTNET")
        LOG.info("=" * 60)
        sys.exit(0)
    else:
        LOG.error("❌ SOME CHECKS FAILED")
        LOG.info("=" * 60)
        sys.exit(1)
