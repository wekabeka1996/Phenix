import csv
import math
import pandas as pd
import numpy as np
import os
import glob
from decimal import Decimal
import sys
from scipy.stats import spearmanr, pearsonr

sys.path.append(r"C:\Users\user\Music\Phenix")
from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRStrategyV11

def load_all_data(symbol):
    pattern = rf"C:\Users\user\Music\Phenix\data\recorder\*\*{symbol}_900.csv"
    files = glob.glob(pattern)
    if not files:
        return None
        
    dfs = []
    for f in files:
        dfs.append(pd.read_csv(f, on_bad_lines='skip'))
    df = pd.concat(dfs, ignore_index=True)
    if 'timestamp' in df.columns:
        df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp']).reset_index(drop=True)
    
    # Pre-calc MTF comparisons
    df['open'] = pd.to_numeric(df['open'], errors='coerce')
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    df['sma_96'] = df['close'].rolling(96).mean()
    # Slope of SMA to estimate true structural direction
    df['sma_slope_96'] = df['sma_96'].diff()
    
    return df

def run_replay(df, symbol, mode="net_config"):
    # mode in: 'gross', 'net_config', 'net_no_dampening'
    fee_bps = 4.0 if mode != "gross" else 0.0
    slippage = 2.0 if mode != "gross" else 0.0
    dampening = 0.5 if mode != "net_no_dampening" else 1.0

    strategy = MDAMRStrategyV11(
        channel_window_bars=12,
        hysteresis_mult=1.2,
        threshold_z=2.20,
        volatility_dampening_factor=dampening,
        thr_base=0.55,
        alpha=0.25,
        conf_min=0.22,
        max_hold_bars=16,
        fee_bps=fee_bps,
        slippage_buffer_bps=slippage,
        scaleout_fraction=0.5,
        weights={"d1": 0.35, "h1": 0.30, "m30": 0.20, "m15": 0.15},
        atr_zscore_clamp=10.0,
        atr_std_floor_pct=0.05,
        thr_floor=0.1
    )

    trades = []
    bar_profiles = []
    
    position = {"qty_signed": 0.0, "bars_held": 0, "entry_ts": None, "entry_price": None, "entry_trace": None, "regime": None}
    
    for idx, row in df.iterrows():
        bar = {
            "open": Decimal(str(row['open'])),
            "high": Decimal(str(row['high'])),
            "low": Decimal(str(row['low'])),
            "close": Decimal(str(row['close']))
        }
        
        if position["qty_signed"] != 0:
            position["bars_held"] += 1
            
        res = strategy.on_bar(bar=bar, position_ctx=position)
        status = res.get('status')
        trace = res.get('trace', {})
        
        # Track every bar for confidence/damp/mtf metrics regardless of position
        bar_profiles.append({
            "mode": mode,
            "ts": row['datetime'],
            "close": row['close'],
            "score": res.get('signal', None).signal_score if status == 'SIGNAL' else 0.0, # Approximate, V11 only outputs score on SIGNAL if not NOOP, actually we need to pull it.
            "dir_score": res.get('dir_score', trace.get('dir_score', 0)),
            "atr_zscore": res.get('atr_zscore', trace.get('atr_zscore', 0)),
            "conf_ratio": trace.get('conf_ratio', 0),
            "qty_new": trace.get('qty_new', 0),
            "thr_buy": trace.get('thr_buy', 0),
            "w_norm_d1": trace.get('w_norm', {}).get('d1', 0),
            "w_norm_m15": trace.get('w_norm', {}).get('m15', 0),
            "dir_comp_d1": trace.get('dir_components', {}).get('d1', 0),
            "band": trace.get('band', 0), # if we could hack it
            # MTF comparators
            "boundary_lookback_val": df.iloc[max(0, idx-96)]['close'] if idx >= 96 else np.nan,
            "sma_96": row['sma_96'],
            "sma_slope_96": row['sma_slope_96']
        })
        
        if status == 'SIGNAL':
            sig = res['signal']
            if sig.intent_kind == "ENTRY":
                if position["qty_signed"] == 0:
                    position["qty_signed"] = 1.0 if sig.side == "BUY" else -1.0
                    position["bars_held"] = 0
                    position["entry_ts"] = row['datetime']
                    position["entry_price"] = sig.price_ref
                    position["entry_trace"] = sig.trace
                    position["regime"] = row.get('regime', 'UNKNOWN')
                    position["signal"] = sig
            elif sig.intent_kind in ("FULL_CLOSE", "PARTIAL_CLOSE"):
                if position["qty_signed"] != 0:
                    target_reached = "FEE_AWARE" in sig.reason_code
                    killswitch = "EDGE_GONE" in sig.reason_code
                    
                    trades.append({
                        "mode": mode,
                        "symbol": symbol,
                        "side": "LONG" if position["qty_signed"] > 0 else "SHORT",
                        "entry_ts": position["entry_ts"],
                        "exit_ts": row['datetime'],
                        "holding_bars": position["bars_held"],
                        "entry_reason": position["signal"].reason_code,
                        "exit_reason": sig.reason_code,
                        "was_target_reached": target_reached, # Actual
                        "was_killswitch_before_target": killswitch,
                        "regime_at_entry": position["regime"],
                        "atr_zscore_at_entry": position["entry_trace"].get("atr_zscore", 0),
                        "atr_zscore_at_exit": trace.get("atr_zscore", 0),
                        "dir_score_at_entry": position["entry_trace"].get("dir_score", 0),
                        "conf_ratio_at_entry": position["entry_trace"].get("conf_ratio", 0),
                        "conf_ratio_before_exit": sig.conf_ratio,
                        "pnl_pct": float((sig.price_ref - position["entry_price"]) / position["entry_price"]) * (1 if position["qty_signed"] > 0 else -1)
                    })
                    if sig.intent_kind == "FULL_CLOSE":
                        position["qty_signed"] = 0.0

    return pd.DataFrame(trades), pd.DataFrame(bar_profiles)

def main():
    symbols = ['XRPUSDT', 'BNBUSDT']
    all_trades = []
    all_profiles = []
    
    for symbol in symbols:
        df = load_all_data(symbol)
        print(f"[{symbol}] Loaded {len(df)} bars")
        
        t1, p1 = run_replay(df, symbol, mode="gross")
        t2, p2 = run_replay(df, symbol, mode="net_config")
        t3, p3 = run_replay(df, symbol, mode="net_no_dampening")
        
        # Attach symbol to profiles
        p1['symbol'] = symbol
        p2['symbol'] = symbol
        p3['symbol'] = symbol
        
        all_trades.extend([t1, t2, t3])
        all_profiles.extend([p1, p2, p3])
        
    trades_df = pd.concat(all_trades, ignore_index=True)
    profiles_df = pd.concat(all_profiles, ignore_index=True)
    
    trades_df.to_csv(r"C:\Users\user\Music\Phenix\scratch\stage3_trades.csv", index=False)
    profiles_df.to_csv(r"C:\Users\user\Music\Phenix\scratch\stage3_profiles.csv", index=False)
    
    print("Replay completed")

if __name__ == "__main__":
    main()
