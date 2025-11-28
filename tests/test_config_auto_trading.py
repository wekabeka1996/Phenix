"""Test helper to inspect AuroraConfig via config v2 resolvers."""

from apps.reference.config_loader import load_config
from apps.reference.config.execution_position import resolve_execution_position_config
from apps.reference.config_sizing import resolve_sizing_policy
from apps.reference.config_symbols import get_trading_symbols, resolve_instrument_profile


def _pick_symbol() -> str:
    symbols = get_trading_symbols()
    return symbols[0] if symbols else "BTCUSDT"


def main() -> None:
    config = load_config()
    symbol = _pick_symbol()

    raw_exec = config.model_dump().get("execution", {}) if hasattr(config, "model_dump") else {}
    ep_cfg = resolve_execution_position_config(raw_exec)
    sizing_cfg = resolve_sizing_policy(config, symbol=symbol, regime="NORMAL")

    print("=" * 60)
    print("AUTO-TRADING CONFIGURATION CHECK (config v2)")
    print("=" * 60)
    print(f"aggregated_oco.enabled = {ep_cfg.aggregated_oco.enabled}")
    print(f"trailing.enabled = {ep_cfg.trailing.enabled}")
    print()

    print("POSITION SIZING CONFIG (via resolver):")
    print(f"symbol: {symbol}")
    print(f"max_risk_pct: {sizing_cfg.max_risk_pct}")
    print(f"min_notional_usd: {sizing_cfg.min_notional_usd}")
    print(f"max_notional_usd: {sizing_cfg.max_notional_usd}")
    print()

    print("INSTRUMENT PROFILES (config v2)")
    for sym in get_trading_symbols():
        profile = resolve_instrument_profile(config, sym)
        print(f"{sym}: step_size={profile.step_size}, min_notional={profile.min_notional}, source={profile.source}")
    print("=" * 60)


if __name__ == "__main__":
    main()
