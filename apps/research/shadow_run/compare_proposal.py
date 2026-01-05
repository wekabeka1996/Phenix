#!/usr/bin/env python3
"""
Compare Current vs Proposed Config from SHORT_TREND_ANALYSIS_AND_PROPOSALS.md

This script runs a shadow comparison between:
- Current weights: OBI=0.10, delta_price=0.05
- Proposed weights: OBI=0.03, delta_price=0.15

Usage:
    python -m apps.research.shadow_run.compare_proposal
    
    # Or with specific symbols:
    python -m apps.research.shadow_run.compare_proposal --symbols ETHUSDT BTCUSDT
"""

import argparse
from decimal import Decimal
from apps.research.shadow_run.shadow_engine import ShadowEngine


def main():
    parser = argparse.ArgumentParser(
        description="Compare current vs proposed config from SHORT_TREND_ANALYSIS_AND_PROPOSALS.md"
    )
    parser.add_argument(
        "--logs-dir", 
        default="logs/features", 
        help="Feature logs directory"
    )
    parser.add_argument(
        "--symbols", 
        nargs="+", 
        help="Symbols to test (default: all available)"
    )
    parser.add_argument(
        "--position-size", 
        type=float, 
        default=100.0,
        help="Position size in USD for simulation"
    )
    parser.add_argument(
        "--sl-pct",
        type=float,
        default=0.005,
        help="Stop loss percentage (default: 0.5%%)"
    )
    parser.add_argument(
        "--tp-pct",
        type=float,
        default=0.01,
        help="Take profit percentage (default: 1.0%%)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed trade logs"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("  SHADOW RUN: Comparing Config from SHORT_TREND_ANALYSIS_AND_PROPOSALS.md")
    print("="*70)
    
    # Create engine
    engine = ShadowEngine(
        feature_logs_dir=args.logs_dir,
        symbols=args.symbols,
        default_position_size_usd=Decimal(str(args.position_size)),
    )
    
    # Set exit parameters
    engine.set_exit_params(
        sl_pct=args.sl_pct,
        tp_pct=args.tp_pct,
        max_hold=60,
    )
    
    print(f"\n📊 Simulation Parameters:")
    print(f"   - Position Size: ${args.position_size}")
    print(f"   - Stop Loss: {args.sl_pct*100:.2f}%")
    print(f"   - Take Profit: {args.tp_pct*100:.2f}%")
    print(f"   - Symbols: {engine.symbols}")
    
    # Define configurations to compare
    # FROM SHORT_TREND_ANALYSIS_AND_PROPOSALS.md:
    # "obi: 0.10 -> 0.03, delta_price: 0.05 -> 0.15"
    
    current_config = {
        "obi": 0.10,
        "delta_price": 0.05,
    }
    
    proposed_config = {
        "obi": 0.03,
        "delta_price": 0.15,
    }
    
    print(f"\n📋 Configurations:")
    print(f"   CURRENT:  OBI={current_config['obi']}, delta_price={current_config['delta_price']}")
    print(f"   PROPOSED: OBI={proposed_config['obi']}, delta_price={proposed_config['delta_price']}")
    
    # Run comparison
    engine.compare_configs(
        current_config,
        proposed_config,
        label_a="Current",
        label_b="Proposed",
    )
    
    # Detailed trade analysis for proposed config
    if args.verbose:
        print("\n" + "="*70)
        print("  DETAILED TRADE LOG (Proposed Config)")
        print("="*70)
        
        results = engine.run_with_overrides(proposed_config)
        
        for symbol, res in results.items():
            print(f"\n--- {symbol} ---")
            for i, trade in enumerate(res.trades[:20]):  # First 20 trades
                print(
                    f"  [{i+1:3d}] {trade.side.upper():5s} @ {float(trade.entry_price):>10.2f} -> "
                    f"{float(trade.exit_price):>10.2f} | P&L: ${float(trade.pnl):>+8.2f} | "
                    f"Exit: {trade.exit_reason}"
                )
            if len(res.trades) > 20:
                print(f"  ... and {len(res.trades) - 20} more trades")
    
    # Additional analysis: What if we apply Flash Crash Guard?
    print("\n" + "="*70)
    print("  ADDITIONAL ANALYSIS: Testing Flash Crash Guard Effect")
    print("="*70)
    
    # This simulates the effect of blocking longs when delta_price < -0.35%
    # We can't fully simulate this without modifying the engine, but we can
    # show P&L breakdown by delta_price at entry
    
    results_proposed = engine.run_with_overrides(proposed_config)
    
    for symbol, res in results_proposed.items():
        # Analyze trades by delta_price at entry
        crash_trades = []
        normal_trades = []
        
        for trade in res.trades:
            if trade.side == "long":
                # Get delta_price at entry
                dp = trade.entry_features.get("delta_price", 0)
                try:
                    dp_val = float(dp)
                    price = float(trade.entry_features.get("price", 1))
                    dp_pct = dp_val / price if price > 0 else 0
                except Exception:
                    dp_pct = 0
                
                if dp_pct < -0.0035:  # Flash crash threshold from proposal
                    crash_trades.append(trade)
                else:
                    normal_trades.append(trade)
        
        if crash_trades:
            crash_pnl = sum(t.pnl for t in crash_trades)
            normal_pnl = sum(t.pnl for t in normal_trades)
            
            print(f"\n{symbol}:")
            print(f"   Trades during 'crash' (dp < -0.35%): {len(crash_trades)}, P&L: ${float(crash_pnl):+.2f}")
            print(f"   Normal trades (dp >= -0.35%):        {len(normal_trades)}, P&L: ${float(normal_pnl):+.2f}")
            print(f"   → Potential improvement if we blocked crash entries: ${float(-crash_pnl):+.2f}")
    
    print("\n✅ Shadow run complete!")


if __name__ == "__main__":
    main()
