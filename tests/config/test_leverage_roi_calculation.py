"""
Test: Leverage loading and ROI-based SL/TP calculation verification.

This test verifies the complete chain:
1. Leverage is correctly loaded from config/instruments.yaml
2. resolve_effective_leverage() finds the leverage value
3. compute_sl_tp_from_roi() calculates sl_pct and tp_rr correctly
4. Final SL/TP prices match expected ROI-based values

Config paths verified:
- config.instruments.<symbol>.limits.max_leverage (primary path - system_config.yaml format)
- config_v2.domains.instruments.instruments.<symbol>.limits.max_leverage (legacy path)
"""

import pytest
from decimal import Decimal
from pathlib import Path
import yaml

# Import the functions under test
from apps.reference.config.execution_position import (
    resolve_effective_leverage,
    compute_sl_tp_from_roi,
    resolve_execution_position_config,
)
from apps.reference.domains.execution_position.aggregator_oco.core_math import (
    compute_desired_levels,
    DesiredLevels,
)


# ============================================================================
# Test fixtures
# ============================================================================

REPO_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture
def real_instruments_config():
    """Load actual instruments.yaml config."""
    instruments_path = REPO_ROOT / "config" / "instruments.yaml"
    with open(instruments_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def real_execution_config():
    """Load actual execution.yaml config."""
    execution_path = REPO_ROOT / "config" / "domains" / "execution.yaml"
    with open(execution_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def combined_config(real_instruments_config, real_execution_config):
    """Combine instruments and execution configs as runtime would see them."""
    return {
        "instruments": real_instruments_config.get("instruments", {}),
        "execution_position": {
            "manage": {
                "brackets": {
                    "aggregated_oco": real_execution_config.get("brackets", {}).get(
                        "aggregated_oco", {}
                    )
                }
            }
        },
    }


# ============================================================================
# Test: Leverage loading from real config
# ============================================================================


class TestLeverageLoading:
    """Tests for leverage loading from configuration."""

    def test_leverage_exists_in_instruments_yaml(self, real_instruments_config):
        """Verify max_leverage is defined in instruments.yaml for all symbols."""
        instruments = real_instruments_config.get("instruments", {})

        expected_symbols = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "BNBUSDT"]

        for symbol in expected_symbols:
            assert symbol in instruments, f"Symbol {symbol} not found in instruments.yaml"
            limits = instruments[symbol].get("limits", {})
            max_leverage = limits.get("max_leverage")
            assert max_leverage is not None, f"max_leverage not defined for {symbol}"
            assert max_leverage > 0, f"max_leverage must be positive for {symbol}"
            print(f"✓ {symbol}: max_leverage = {max_leverage}")

    def test_resolve_effective_leverage_with_primary_path(self):
        """Test resolve_effective_leverage finds leverage via instruments.<symbol>.limits.max_leverage."""
        config = {
            "instruments": {
                "SOLUSDT": {"limits": {"max_leverage": 20}},
                "BTCUSDT": {"limits": {"max_leverage": 125}},
            }
        }

        sol_lev = resolve_effective_leverage("SOLUSDT", config)
        btc_lev = resolve_effective_leverage("BTCUSDT", config)

        assert sol_lev == 20.0, f"Expected 20.0, got {sol_lev}"
        assert btc_lev == 125.0, f"Expected 125.0, got {btc_lev}"
        print(f"✓ SOLUSDT leverage = {sol_lev}")
        print(f"✓ BTCUSDT leverage = {btc_lev}")

    def test_resolve_effective_leverage_with_real_config(self, combined_config):
        """Test resolve_effective_leverage with actual config structure."""
        symbols = ["SOLUSDT", "ETHUSDT", "BTCUSDT", "BNBUSDT"]

        for symbol in symbols:
            lev = resolve_effective_leverage(symbol, combined_config)
            expected_lev = combined_config["instruments"][symbol]["limits"]["max_leverage"]
            assert lev == float(expected_lev), (
                f"{symbol}: Expected {expected_lev}, got {lev}"
            )
            print(f"✓ {symbol}: leverage = {lev}")

    def test_resolve_effective_leverage_fallback_default(self):
        """Test that missing leverage falls back to default (10.0)."""
        config = {"instruments": {}}  # No symbols

        lev = resolve_effective_leverage("UNKNOWN_SYMBOL", config)
        assert lev == 10.0, f"Expected default 10.0, got {lev}"
        print(f"✓ Unknown symbol fallback = {lev}")

    def test_resolve_effective_leverage_legacy_path(self):
        """Test legacy config_v2 path still works."""
        config = {
            "config_v2": {
                "domains": {
                    "instruments": {
                        "instruments": {
                            "SOLUSDT": {"limits": {"max_leverage": 50}}
                        }
                    }
                }
            }
        }

        lev = resolve_effective_leverage("SOLUSDT", config)
        assert lev == 50.0, f"Expected 50.0, got {lev}"
        print(f"✓ Legacy path SOLUSDT leverage = {lev}")


# ============================================================================
# Test: ROI-based SL/TP calculation
# ============================================================================


class TestROICalculation:
    """Tests for ROI-based SL/TP calculation."""

    def test_compute_sl_tp_from_roi_formula(self):
        """Verify the ROI → sl_pct/tp_rr formula is correct."""
        # Given ROI configuration
        sl_roi_pct = 35.0  # 35% loss on margin
        tp_roi_pct = 50.0  # 50% profit on margin
        leverage = 20.0

        # Expected calculation:
        # sl_pct_price = (sl_roi_pct / 100) / leverage = 35/100/20 = 0.0175 (1.75%)
        # tp_pct_price = (tp_roi_pct / 100) / leverage = 50/100/20 = 0.025 (2.5%)
        # tp_rr = tp_pct_price / sl_pct_price = 0.025 / 0.0175 = 1.4286

        expected_sl_pct = 0.0175
        expected_tp_rr = 50.0 / 35.0  # 1.4286

        # Build config
        config = {
            "execution_position": {
                "manage": {
                    "brackets": {
                        "aggregated_oco": {
                            "enabled": True,
                            "sl_pct": 0.02,  # fallback
                            "tp_rr": 2.0,    # fallback
                            "sl_roi_pct": sl_roi_pct,
                            "tp_roi_pct": tp_roi_pct,
                        }
                    }
                }
            }
        }

        ep_cfg = resolve_execution_position_config(config)
        sl_pct, tp_rr = compute_sl_tp_from_roi(ep_cfg, "SOLUSDT", leverage)

        assert abs(sl_pct - expected_sl_pct) < 0.0001, (
            f"sl_pct: Expected {expected_sl_pct}, got {sl_pct}"
        )
        assert abs(tp_rr - expected_tp_rr) < 0.001, (
            f"tp_rr: Expected {expected_tp_rr:.4f}, got {tp_rr:.4f}"
        )
        print(f"✓ sl_pct = {sl_pct:.4f} ({sl_pct*100:.2f}%)")
        print(f"✓ tp_rr = {tp_rr:.4f}")

    def test_compute_sl_tp_from_roi_with_different_leverages(self):
        """Test ROI calculation with different leverage values."""
        sl_roi_pct = 35.0
        tp_roi_pct = 50.0

        test_cases = [
            (10, 0.035, 1.4286),   # 10x → 3.5% sl_pct
            (20, 0.0175, 1.4286),  # 20x → 1.75% sl_pct
            (50, 0.007, 1.4286),   # 50x → 0.7% sl_pct
            (125, 0.0028, 1.4286),  # 125x → 0.28% sl_pct
        ]

        config = {
            "execution_position": {
                "manage": {
                    "brackets": {
                        "aggregated_oco": {
                            "enabled": True,
                            "sl_roi_pct": sl_roi_pct,
                            "tp_roi_pct": tp_roi_pct,
                        }
                    }
                }
            }
        }

        ep_cfg = resolve_execution_position_config(config)

        for leverage, expected_sl_pct, expected_tp_rr in test_cases:
            sl_pct, tp_rr = compute_sl_tp_from_roi(ep_cfg, "SOLUSDT", leverage)

            assert abs(sl_pct - expected_sl_pct) < 0.0001, (
                f"leverage={leverage}: sl_pct expected {expected_sl_pct}, got {sl_pct}"
            )
            assert abs(tp_rr - expected_tp_rr) < 0.001, (
                f"leverage={leverage}: tp_rr expected {expected_tp_rr:.4f}, got {tp_rr:.4f}"
            )
            print(
                f"✓ leverage={leverage:3d}x: sl_pct={sl_pct:.4f} ({sl_pct*100:.2f}%), tp_rr={tp_rr:.4f}")

    def test_compute_sl_tp_from_roi_with_real_config(self, combined_config):
        """Test ROI calculation using actual config files."""
        ep_cfg = resolve_execution_position_config(combined_config)

        agg = ep_cfg.aggregated_oco
        assert agg.sl_roi_pct == 35.0, f"Expected sl_roi_pct=35.0, got {agg.sl_roi_pct}"
        assert agg.tp_roi_pct == 50.0, f"Expected tp_roi_pct=50.0, got {agg.tp_roi_pct}"

        # Get leverage from config
        leverage = resolve_effective_leverage("SOLUSDT", combined_config)
        print(f"✓ SOLUSDT leverage from config = {leverage}")

        sl_pct, tp_rr = compute_sl_tp_from_roi(ep_cfg, "SOLUSDT", leverage)

        # Expected with leverage=20
        expected_sl_pct = 35.0 / 100.0 / leverage
        expected_tp_rr = 50.0 / 35.0

        assert abs(sl_pct - expected_sl_pct) < 0.0001
        assert abs(tp_rr - expected_tp_rr) < 0.001
        print(f"✓ sl_pct = {sl_pct:.4f} ({sl_pct*100:.2f}%)")
        print(f"✓ tp_rr = {tp_rr:.4f}")


# ============================================================================
# Test: End-to-end SL/TP price calculation
# ============================================================================


class TestSLTPPriceCalculation:
    """Tests for final SL/TP price calculation."""

    @pytest.mark.parametrize("side,entry_price,expected_sl,expected_tp", [
        # LONG positions: SL below entry, TP above entry
        ("LONG", Decimal("100.00"), Decimal("98.25"),
         Decimal("102.50")),   # 1.75% distance
        ("LONG", Decimal("138.22"), Decimal("135.80"),
         Decimal("141.68")),  # SOLUSDT real example
        ("LONG", Decimal("50000.00"), Decimal("49125.00"), Decimal(
            "51250.03")),  # BTC example (adjusted for precision)

        # SHORT positions: SL above entry, TP below entry
        ("SHORT", Decimal("100.00"), Decimal("101.75"), Decimal("97.50")),
        ("SHORT", Decimal("138.22"), Decimal("140.64"), Decimal("134.76")),
    ])
    def test_sl_tp_prices_match_roi_formula(
        self, side, entry_price, expected_sl, expected_tp
    ):
        """Verify SL/TP prices are calculated correctly from ROI parameters."""
        # ROI config: sl_roi=35%, tp_roi=50%, leverage=20
        sl_pct = Decimal("0.0175")  # 35%/20 = 1.75%
        tp_rr = Decimal("1.4286")   # 50%/35% = 1.4286

        # Calculate using core_math - returns DesiredLevels dataclass
        levels: DesiredLevels = compute_desired_levels(
            entry_price=entry_price,
            sl_pct=sl_pct,
            tp_rr=tp_rr,
            side=side,
        )

        sl_price = levels.sl_price
        tp_price = levels.tp_price

        # Allow small rounding tolerance (0.05 for larger prices like BTC)
        tolerance = Decimal("0.05")

        assert abs(sl_price - expected_sl) < tolerance, (
            f"{side} SL: Expected {expected_sl}, got {sl_price}"
        )
        assert abs(tp_price - expected_tp) < tolerance, (
            f"{side} TP: Expected {expected_tp}, got {tp_price}"
        )
        print(f"✓ {side} entry={entry_price}: SL={sl_price:.2f}, TP={tp_price:.2f}")

    def test_full_chain_solusdt_example(self, combined_config):
        """
        Complete end-to-end test for SOLUSDT with real config.

        This simulates the exact calculation path in production:
        1. Load leverage from instruments.yaml
        2. Load ROI from execution.yaml
        3. Compute sl_pct and tp_rr
        4. Calculate final SL/TP prices
        """
        symbol = "SOLUSDT"
        entry_price = Decimal("138.22")
        side = "LONG"

        # Step 1: Get leverage
        leverage = resolve_effective_leverage(symbol, combined_config)
        assert leverage == 20.0, f"Expected leverage=20, got {leverage}"
        print(f"\n=== SOLUSDT Full Chain Test ===")
        print(f"Step 1: leverage = {leverage}")

        # Step 2: Get ROI config
        ep_cfg = resolve_execution_position_config(combined_config)
        sl_roi_pct = ep_cfg.aggregated_oco.sl_roi_pct
        tp_roi_pct = ep_cfg.aggregated_oco.tp_roi_pct
        assert sl_roi_pct == 35.0
        assert tp_roi_pct == 50.0
        print(
            f"Step 2: sl_roi_pct = {sl_roi_pct}%, tp_roi_pct = {tp_roi_pct}%")

        # Step 3: Compute sl_pct and tp_rr
        sl_pct, tp_rr = compute_sl_tp_from_roi(ep_cfg, symbol, leverage)
        expected_sl_pct = sl_roi_pct / 100.0 / leverage  # 0.0175
        expected_tp_rr = tp_roi_pct / sl_roi_pct  # 1.4286
        assert abs(sl_pct - expected_sl_pct) < 0.0001
        assert abs(tp_rr - expected_tp_rr) < 0.001
        print(
            f"Step 3: sl_pct = {sl_pct:.4f} ({sl_pct*100:.2f}%), tp_rr = {tp_rr:.4f}")

        # Step 4: Calculate SL/TP prices - returns DesiredLevels dataclass
        levels: DesiredLevels = compute_desired_levels(
            entry_price=entry_price,
            sl_pct=Decimal(str(sl_pct)),
            tp_rr=Decimal(str(tp_rr)),
            side=side,
        )

        sl_price = levels.sl_price
        tp_price = levels.tp_price

        # Expected prices (LONG):
        # SL = entry * (1 - sl_pct) = 138.22 * 0.9825 = 135.80
        # TP = entry * (1 + sl_pct * tp_rr) = 138.22 * 1.025 = 141.68
        expected_sl = entry_price * (1 - Decimal(str(sl_pct)))
        expected_tp = entry_price * \
            (1 + Decimal(str(sl_pct)) * Decimal(str(tp_rr)))

        tolerance = Decimal("0.01")
        assert abs(sl_price - expected_sl) < tolerance
        assert abs(tp_price - expected_tp) < tolerance

        print(f"Step 4: SL = {sl_price:.4f}, TP = {tp_price:.4f}")
        print(f"\n✓ Full chain verification passed!")
        print(f"  Entry: {entry_price}")
        print(
            f"  SL: {sl_price:.2f} ({float(sl_price - entry_price)/float(entry_price)*100:.2f}% from entry)")
        print(
            f"  TP: {tp_price:.2f} (+{float(tp_price - entry_price)/float(entry_price)*100:.2f}% from entry)")
        print(f"  Risk/Reward: 1:{float(tp_rr):.2f}")


# ============================================================================
# Test: Edge cases and error handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_zero_leverage_uses_fallback(self):
        """Test that zero leverage is handled safely."""
        config = {
            "instruments": {"SOLUSDT": {"limits": {"max_leverage": 0}}}
        }

        # Should return default (10.0) when leverage is 0 or invalid
        lev = resolve_effective_leverage("SOLUSDT", config)
        assert lev == 10.0, f"Expected fallback 10.0, got {lev}"

    def test_negative_leverage_uses_fallback(self):
        """Test that negative leverage is handled safely."""
        config = {
            "instruments": {"SOLUSDT": {"limits": {"max_leverage": -5}}}
        }

        lev = resolve_effective_leverage("SOLUSDT", config)
        assert lev == 10.0, f"Expected fallback 10.0, got {lev}"

    def test_missing_roi_uses_fallback_sl_tp(self):
        """Test that zero/missing ROI falls back to legacy sl_pct/tp_rr."""
        # Note: resolve_execution_position_config expects raw config
        # without 'execution_position' wrapper
        config = {
            "manage": {
                "brackets": {
                    "aggregated_oco": {
                        "enabled": True,
                        "sl_pct": 0.02,
                        "tp_rr": 2.0,
                        # Zero ROI values trigger fallback
                        "sl_roi_pct": 0.0,
                        "tp_roi_pct": 0.0,
                    }
                }
            }
        }

        ep_cfg = resolve_execution_position_config(config)
        sl_pct, tp_rr = compute_sl_tp_from_roi(ep_cfg, "SOLUSDT", 20.0)

        # Should fall back to legacy values when ROI is 0
        assert sl_pct == 0.02, f"Expected fallback sl_pct=0.02, got {sl_pct}"
        assert tp_rr == 2.0, f"Expected fallback tp_rr=2.0, got {tp_rr}"

    def test_roi_with_extreme_leverage(self):
        """Test ROI calculation with extreme leverage values."""
        config = {
            "execution_position": {
                "manage": {
                    "brackets": {
                        "aggregated_oco": {
                            "enabled": True,
                            "sl_roi_pct": 35.0,
                            "tp_roi_pct": 50.0,
                        }
                    }
                }
            }
        }

        ep_cfg = resolve_execution_position_config(config)

        # Test with 125x leverage (Binance max)
        sl_pct, tp_rr = compute_sl_tp_from_roi(ep_cfg, "SOLUSDT", 125.0)
        expected_sl_pct = 35.0 / 100.0 / 125.0  # 0.0028 (0.28%)

        assert abs(sl_pct - expected_sl_pct) < 0.0001
        print(f"✓ 125x leverage: sl_pct = {sl_pct:.4f} ({sl_pct*100:.2f}%)")


# ============================================================================
# Integration test: Simulate production flow
# ============================================================================


class TestProductionFlow:
    """Integration test simulating production code flow."""

    def test_simulate_bracket_creation_flow(self, combined_config):
        """
        Simulate the actual production flow for bracket creation.

        This mirrors the code path in:
        - runtime.py: _get_bracket_cfg()
        - engine.py: compute_bracket_plan_from_views()
        - core_math.py: compute_desired_levels()
        """
        symbol = "SOLUSDT"
        entry_price = Decimal("138.22")
        side = "LONG"

        # === Step 1: _get_bracket_cfg() logic ===
        ep_cfg = resolve_execution_position_config(combined_config)
        agg = ep_cfg.aggregated_oco

        # Resolve leverage (like runtime.py does)
        lev = resolve_effective_leverage(symbol, combined_config)

        # Compute ROI-based values (like runtime.py does)
        sl_pct_price, tp_rr_val = compute_sl_tp_from_roi(ep_cfg, symbol, lev)

        # Apply fallback logic (like runtime.py does)
        sl_pct_cfg = sl_pct_price if sl_pct_price else agg.sl_pct
        tp_rr_cfg = tp_rr_val if tp_rr_val else agg.tp_rr

        # === Step 2: engine.py converts to BracketConfig ===
        sl_pct_decimal = Decimal(str(sl_pct_cfg))
        tp_rr_decimal = Decimal(str(tp_rr_cfg))

        # === Step 3: core_math.py calculates prices - returns DesiredLevels ===
        levels: DesiredLevels = compute_desired_levels(
            entry_price=entry_price,
            sl_pct=sl_pct_decimal,
            tp_rr=tp_rr_decimal,
            side=side,
        )

        sl_price = levels.sl_price
        tp_price = levels.tp_price

        # === Verify results ===
        print(f"\n=== Production Flow Simulation ===")
        print(f"Symbol: {symbol}")
        print(f"Entry: {entry_price}")
        print(f"Side: {side}")
        print(f"Leverage: {lev}")
        print(f"sl_pct: {sl_pct_cfg:.4f} ({sl_pct_cfg*100:.2f}%)")
        print(f"tp_rr: {tp_rr_cfg:.4f}")
        print(f"SL Price: {sl_price:.4f}")
        print(f"TP Price: {tp_price:.4f}")

        # Verify ROI targets
        sl_distance_pct = float(abs(entry_price - sl_price) / entry_price)
        tp_distance_pct = float(abs(tp_price - entry_price) / entry_price)

        # With 20x leverage:
        # SL distance 1.75% * 20 = 35% ROI loss
        # TP distance 2.5% * 20 = 50% ROI profit
        sl_roi_actual = sl_distance_pct * lev * 100
        tp_roi_actual = tp_distance_pct * lev * 100

        print(f"\nROI Verification:")
        print(f"  SL ROI: {sl_roi_actual:.1f}% (expected 35%)")
        print(f"  TP ROI: {tp_roi_actual:.1f}% (expected 50%)")

        assert abs(sl_roi_actual -
                   35.0) < 0.5, f"SL ROI mismatch: {sl_roi_actual}"
        assert abs(tp_roi_actual -
                   50.0) < 0.5, f"TP ROI mismatch: {tp_roi_actual}"

        print(f"\n✓ Production flow simulation passed!")
