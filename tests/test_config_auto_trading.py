"""Test helper to inspect AuroraConfig via config v2 resolvers."""

from apps.reference.config_loader import load_config
from apps.reference.domains.execution_position.manage_config import (
    resolve_execution_manage_config,
)
from apps.reference.config_sizing import resolve_sizing_policy
from apps.reference.config_symbols import get_trading_symbols, resolve_instrument_profile


def _pick_symbol() -> str:
    symbols = get_trading_symbols()
    return symbols[0] if symbols else "BTCUSDT"


def main() -> None:
    config = load_config()
    symbol = _pick_symbol()

    manage_cfg = resolve_execution_manage_config(config)
    sizing_cfg = resolve_sizing_policy(config, symbol=symbol, regime="NORMAL")

    print("=" * 60)
    print("AUTO-TRADING CONFIGURATION CHECK (config v2)")
    print("=" * 60)
    print(f"execution.manage.auto = {getattr(manage_cfg, 'auto', False)}")
    print(f"guardian.emit_tidy_event = {manage_cfg.guardian.emit_tidy_event}")
    print(f"brackets.enable = {manage_cfg.brackets.enable}")
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
