"""Quick Pydantic validation for MVP 2026-02-18 config changes. Read-only."""
import yaml
from apps.reference.config_models import AuroraInstrumentConfig

# aurora.yaml
with open("config/aurora/strategies/aurora.yaml", encoding="utf-8") as f:
    aurora_raw = yaml.safe_load(f)
aurora_data = aurora_raw.get("aurora", {})
assets = aurora_data.get("assets", {})

print("=== ETH ===")
eth = AuroraInstrumentConfig(**assets["ETHUSDT"])
print(
    f"  holding_period.min_duration_sec       = {eth.holding_period.min_duration_sec}")
print(
    f"  holding_period.emergency_exit_threshold= {eth.holding_period.emergency_exit_threshold}")
print(
    f"  volatility_entry_logic.DEFAULT        = {eth.volatility_entry_logic.regime_multipliers['DEFAULT']}")
print(
    f"  volatility_entry_logic.HIGH_VOLATILITY= {eth.volatility_entry_logic.regime_multipliers['HIGH_VOLATILITY']}")

print("=== SOL ===")
sol = AuroraInstrumentConfig(**assets["SOLUSDT"])
print(
    f"  holding_period.min_duration_sec       = {sol.holding_period.min_duration_sec}")
print(
    f"  volatility_entry_logic.DEFAULT        = {sol.volatility_entry_logic.regime_multipliers['DEFAULT']}")
print(
    f"  volatility_entry_logic.HIGH_VOLATILITY= {sol.volatility_entry_logic.regime_multipliers['HIGH_VOLATILITY']}")

print("=== BTC (aurora) ===")
btc = AuroraInstrumentConfig(**assets["BTCUSDT"])
print(f"  leverage.target                       = {btc.leverage.target}")

print("=== decision.gates ===")
gates = aurora_data["decision"]["gates"]
print(f"  anti_flat_sigma  = {gates['anti_flat_sigma']}")
print(f"  anti_fomo_sigma  = {gates['anti_fomo_sigma']}")
print(
    f"  reentry_cooldown = {aurora_data['decision']['reentry_cooldown_sec']}")
print(f"  signal_threshold = {aurora_data['decision']['signal_threshold']}")

# regime.yaml
with open("config/aurora/regime.yaml", encoding="utf-8") as f:
    regime_raw = yaml.safe_load(f)
print("=== regime.yaml ===")
print(f"  uncertain_cutoff       = {regime_raw['uncertain_cutoff']}")
print(f"  hysteresis_bars        = {regime_raw['hysteresis_bars']}")
print(f"  vol_slope_gate_eps     = {regime_raw['vol_slope_gate_eps']}")
sma = regime_raw["models"]["sma_trend"]
print(f"  sma_short_period       = {sma['sma_short_period']}")
print(f"  sma_long_period        = {sma['sma_long_period']}")
print(f"  confidence_multiplier  = {sma['confidence_multiplier']}")
print(f"  confidence_min         = {sma['confidence_min']}")

# mean_reversion.yaml
with open("config/aurora/strategies/mean_reversion.yaml", encoding="utf-8") as f:
    mr_raw = yaml.safe_load(f)
mr = mr_raw.get("mean_reversion", {})
print("=== mean_reversion.yaml ===")
print(f"  global entry_threshold = {mr['strategy']['entry_threshold']}")
doge = mr["assets"]["DOGEUSDT"]
print(f"  DOGE cooldown_sec      = {doge['strategy']['cooldown_sec']}")
btc_mr = mr["assets"]["BTCUSDT"]
print(f"  BTC leverage.target    = {btc_mr['leverage']['target']}")
print(f"  BTC bb_num_std         = {btc_mr['strategy']['bb_num_std']}")
print(f"  BTC entry_threshold    = {btc_mr['strategy']['entry_threshold']}")
print(f"  BTC cooldown_sec       = {btc_mr['strategy']['cooldown_sec']}")

print()
print("ALL OK - no ValidationError raised")
