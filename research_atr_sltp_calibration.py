#!/usr/bin/env python3
"""
ATR-SLTP-CALIBRATION-01

Calibrate volatility-adjusted SL/TP multipliers (k_sl, k_tp) from Binance USD-M Futures OHLCV candles.
Research-only script - does NOT modify runtime code.

Data source: data.binance.vision futures um monthly klines (zip) or API fallback
Symbols: BTCUSDT, ETHUSDT, SOLUSDT, DOGEUSDT, XRPUSDT
Intervals: 5m (primary), 15m (regime proxy)

Method:
1. Load candles -> DataFrame with open_time, O, H, L, C, V
2. Compute returns r_t = log(C_t / C_{t-1})
3. Compute ATR_14 on 5m OR robust vol = median(|r|) over 14 bars
4. Compute regime proxy per timestamp using rolling volatility on 15m-equivalent window
5. Define candidate entry times (every 5m bar close)
6. Simulate LONG/SHORT excursions over horizon H bars (45 min = 9 bars)
7. Compute MAE/MFE for each excursion
8. Compute quantiles by symbol and regime
9. Convert to ATR multipliers
10. Generate report (MD + CSV + optional plots)
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass
import logging

import pandas as pd
import numpy as np
import requests
from datetime import datetime, timezone
import zipfile
import io
import matplotlib.pyplot as plt
import seaborn as sns

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
INTERVAL_5M = "5m"
INTERVAL_15M = "15m"
ATR_PERIOD = 14
HORIZON_MINUTES = 45  # Excursion horizon
HORIZON_BARS = HORIZON_MINUTES // 5  # For 5m candles

# Regime quantile thresholds
REGIME_LOW_THRESHOLD = 0.50   # q50
REGIME_MID_THRESHOLD = 0.80   # q80

# Output paths
REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)
OUTPUT_MD = REPORTS_DIR / "atr_sltp_calibration_01.md"
OUTPUT_CSV = REPORTS_DIR / "atr_sltp_calibration_01.csv"
OUTPUT_PLOTS_DIR = REPORTS_DIR / "atr_sltp_plots"
OUTPUT_PLOTS_DIR.mkdir(exist_ok=True)


@dataclass
class ExcursionStats:
    """Statistics for MAE/MFE excursions"""
    symbol: str
    regime: str
    atr_frac_median: float
    k_sl_q90: float
    k_sl_q95: float
    k_tp_q50: float
    k_tp_q60: float
    k_tp_q70: float
    sample_count: int


def download_binance_klines_zip(symbol: str, interval: str, year: int = 2024, month: int = 12) -> pd.DataFrame:
    """
    Download monthly klines from data.binance.vision (zip format).
    
    URL pattern: https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{interval}/{SYMBOL}-{interval}-{YYYY}-{MM}.zip
    """
    base_url = "https://data.binance.vision/data/futures/um/monthly/klines"
    month_str = f"{month:02d}"
    filename = f"{symbol}-{interval}-{year}-{month_str}.zip"
    url = f"{base_url}/{symbol}/{interval}/{filename}"
    
    logger.info(f"Downloading {url}")
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        # Extract CSV from zip
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            csv_name = filename.replace(".zip", ".csv")
            with z.open(csv_name) as f:
                df = pd.read_csv(
                    f,
                    header=None,
                    names=[
                        "open_time", "open", "high", "low", "close", "volume",
                        "close_time", "quote_volume", "count", "taker_buy_volume",
                        "taker_buy_quote_volume", "ignore"
                    ]
                )
        
        # Convert timestamp
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        
        # Convert OHLCV to numeric
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        logger.info(f"Loaded {len(df)} candles for {symbol} {interval}")
        return df[["open_time", "open", "high", "low", "close", "volume"]]
    
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return pd.DataFrame()


def download_binance_klines_api(symbol: str, interval: str, limit: int = 1000, days_back: int = 30) -> pd.DataFrame:
    """
    Download klines via Binance Futures API for last N days.
    GET /fapi/v1/klines
    """
    base_url = "https://fapi.binance.com"
    endpoint = "/fapi/v1/klines"
    
    all_candles = []
    
    # Calculate time range: last N days
    end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_time = end_time - (days_back * 24 * 60 * 60 * 1000)
    
    logger.info(f"Downloading {symbol} {interval} via API (last {days_back} days, limit={limit})")
    
    current_start = start_time
    
    for page in range(50):  # Max 50 pages for safety
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "startTime": current_start,
            "endTime": end_time
        }
        
        try:
            response = requests.get(base_url + endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                break
            
            all_candles.extend(data)
            
            # Move to next page
            current_start = data[-1][0] + 1
            
            # If we got less than limit, we're done
            if len(data) < limit:
                break
            
            # If we've reached end_time, stop
            if current_start >= end_time:
                break
        
        except Exception as e:
            logger.error(f"API error: {e}")
            break
    
    if not all_candles:
        return pd.DataFrame()
    
    # Convert to DataFrame
    df = pd.DataFrame(
        all_candles,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "count", "taker_buy_volume",
            "taker_buy_quote_volume", "ignore"
        ]
    )
    
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    
    logger.info(f"Loaded {len(df)} candles for {symbol} {interval}")
    return df[["open_time", "open", "high", "low", "close", "volume"]].sort_values("open_time")


def compute_returns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute log returns r_t = log(C_t / C_{t-1})"""
    df = df.copy()
    df["returns"] = np.log(df["close"] / df["close"].shift(1))
    return df


def compute_true_range(df: pd.DataFrame) -> pd.DataFrame:
    """Compute True Range for ATR calculation"""
    df = df.copy()
    df["prev_close"] = df["close"].shift(1)
    df["tr"] = df[["high", "low", "prev_close"]].apply(
        lambda row: max(
            row["high"] - row["low"],
            abs(row["high"] - row["prev_close"]) if pd.notna(row["prev_close"]) else 0,
            abs(row["low"] - row["prev_close"]) if pd.notna(row["prev_close"]) else 0
        ),
        axis=1
    )
    return df


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Compute ATR (Average True Range)"""
    df = compute_true_range(df)
    df["atr"] = df["tr"].rolling(window=period, min_periods=period).mean()
    return df


def compute_robust_volatility(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Compute robust volatility: median(|returns|) over rolling window"""
    df = df.copy()
    df["abs_returns"] = df["returns"].abs()
    df["robust_vol"] = df["abs_returns"].rolling(window=period, min_periods=period).median()
    return df


def compute_regime_proxy(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    Compute regime proxy based on rolling volatility quantiles.
    
    window: rolling window size for 15m-equivalent (3 bars of 5m = 15m)
    Regimes:
      LOW: vol <= q50
      MID: q50 < vol <= q80
      HIGH: vol > q80
    """
    df = df.copy()
    
    # Compute rolling volatility (15m-equivalent)
    df["vol_15m"] = df["robust_vol"].rolling(window=window, min_periods=window).mean()
    
    # Compute quantiles
    q50 = df["vol_15m"].quantile(REGIME_LOW_THRESHOLD)
    q80 = df["vol_15m"].quantile(REGIME_MID_THRESHOLD)
    
    # Assign regime
    def assign_regime(vol):
        if pd.isna(vol):
            return "UNKNOWN"
        if vol <= q50:
            return "LOW"
        elif vol <= q80:
            return "MID"
        else:
            return "HIGH"
    
    df["regime"] = df["vol_15m"].apply(assign_regime)
    
    logger.info(f"Regime quantiles: q50={q50:.6f}, q80={q80:.6f}")
    logger.info(f"Regime distribution:\n{df['regime'].value_counts()}")
    
    return df


def compute_mae_mfe_excursions(df: pd.DataFrame, horizon_bars: int) -> pd.DataFrame:
    """
    For each entry point (bar close), simulate LONG and SHORT excursions over horizon.
    
    MAE_long = (entry_price - min(L_future)) / entry_price
    MFE_long = (max(H_future) - entry_price) / entry_price
    MAE_short = (max(H_future) - entry_price) / entry_price
    MFE_short = (entry_price - min(L_future)) / entry_price
    """
    df = df.copy()
    
    # Pre-allocate columns
    df["mae_long"] = np.nan
    df["mfe_long"] = np.nan
    df["mae_short"] = np.nan
    df["mfe_short"] = np.nan
    
    # Iterate over valid entry points
    for i in range(len(df) - horizon_bars):
        entry_price = df.iloc[i]["close"]
        
        # Future window
        future_window = df.iloc[i+1:i+1+horizon_bars]
        
        if len(future_window) < horizon_bars:
            continue
        
        min_low = future_window["low"].min()
        max_high = future_window["high"].max()
        
        # LONG excursion
        mae_long = (entry_price - min_low) / entry_price
        mfe_long = (max_high - entry_price) / entry_price
        
        # SHORT excursion
        mae_short = (max_high - entry_price) / entry_price
        mfe_short = (entry_price - min_low) / entry_price
        
        df.loc[df.index[i], "mae_long"] = mae_long
        df.loc[df.index[i], "mfe_long"] = mfe_long
        df.loc[df.index[i], "mae_short"] = mae_short
        df.loc[df.index[i], "mfe_short"] = mfe_short
    
    return df


def calibrate_multipliers_by_regime(df: pd.DataFrame, symbol: str) -> List[ExcursionStats]:
    """
    Compute quantiles of MAE/MFE by regime and convert to ATR multipliers.
    
    Returns list of ExcursionStats for each regime.
    """
    results = []
    
    # Filter valid rows with all excursion metrics
    df_valid = df.dropna(subset=["mae_long", "mfe_long", "mae_short", "mfe_short", "atr", "regime"])
    df_valid = df_valid[df_valid["regime"] != "UNKNOWN"]
    
    for regime in ["LOW", "MID", "HIGH"]:
        regime_df = df_valid[df_valid["regime"] == regime]
        
        if len(regime_df) < 10:
            logger.warning(f"Insufficient data for {symbol} {regime}: {len(regime_df)} samples")
            continue
        
        # Combine LONG and SHORT MAE/MFE
        mae_all = pd.concat([regime_df["mae_long"], regime_df["mae_short"]])
        mfe_all = pd.concat([regime_df["mfe_long"], regime_df["mfe_short"]])
        
        # Compute quantiles
        mae_q90 = mae_all.quantile(0.90)
        mae_q95 = mae_all.quantile(0.95)
        mfe_q50 = mfe_all.quantile(0.50)
        mfe_q60 = mfe_all.quantile(0.60)
        mfe_q70 = mfe_all.quantile(0.70)
        
        # Compute ATR fraction (median)
        atr_frac_median = (regime_df["atr"] / regime_df["close"]).median()
        
        # Convert to ATR multipliers
        k_sl_q90 = mae_q90 / atr_frac_median if atr_frac_median > 0 else np.nan
        k_sl_q95 = mae_q95 / atr_frac_median if atr_frac_median > 0 else np.nan
        k_tp_q50 = mfe_q50 / atr_frac_median if atr_frac_median > 0 else np.nan
        k_tp_q60 = mfe_q60 / atr_frac_median if atr_frac_median > 0 else np.nan
        k_tp_q70 = mfe_q70 / atr_frac_median if atr_frac_median > 0 else np.nan
        
        stats = ExcursionStats(
            symbol=symbol,
            regime=regime,
            atr_frac_median=atr_frac_median,
            k_sl_q90=k_sl_q90,
            k_sl_q95=k_sl_q95,
            k_tp_q50=k_tp_q50,
            k_tp_q60=k_tp_q60,
            k_tp_q70=k_tp_q70,
            sample_count=len(regime_df)
        )
        
        results.append(stats)
        
        logger.info(f"{symbol} {regime}: atr_frac={atr_frac_median:.6f}, "
                   f"k_sl_q90={k_sl_q90:.2f}, k_sl_q95={k_sl_q95:.2f}, "
                   f"k_tp_q50={k_tp_q50:.2f}, k_tp_q60={k_tp_q60:.2f}, k_tp_q70={k_tp_q70:.2f}, "
                   f"samples={len(regime_df)}")
    
    return results


def plot_mae_mfe_distributions(df: pd.DataFrame, symbol: str):
    """Generate histogram plots for MAE/MFE by regime"""
    df_valid = df.dropna(subset=["mae_long", "mfe_long", "regime"])
    df_valid = df_valid[df_valid["regime"] != "UNKNOWN"]
    
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle(f"{symbol} - MAE/MFE Distributions by Regime", fontsize=16)
    
    for i, regime in enumerate(["LOW", "MID", "HIGH"]):
        regime_df = df_valid[df_valid["regime"] == regime]
        
        if len(regime_df) == 0:
            continue
        
        # MAE distribution
        mae_all = pd.concat([regime_df["mae_long"], regime_df["mae_short"]])
        axes[0, i].hist(mae_all.clip(0, 0.05), bins=50, alpha=0.7, edgecolor="black")
        axes[0, i].set_title(f"{regime} - MAE")
        axes[0, i].set_xlabel("MAE (fraction)")
        axes[0, i].set_ylabel("Frequency")
        axes[0, i].axvline(mae_all.quantile(0.90), color="red", linestyle="--", label="q90")
        axes[0, i].axvline(mae_all.quantile(0.95), color="darkred", linestyle="--", label="q95")
        axes[0, i].legend()
        
        # MFE distribution
        mfe_all = pd.concat([regime_df["mfe_long"], regime_df["mfe_short"]])
        axes[1, i].hist(mfe_all.clip(0, 0.05), bins=50, alpha=0.7, edgecolor="black")
        axes[1, i].set_title(f"{regime} - MFE")
        axes[1, i].set_xlabel("MFE (fraction)")
        axes[1, i].set_ylabel("Frequency")
        axes[1, i].axvline(mfe_all.quantile(0.50), color="green", linestyle="--", label="q50")
        axes[1, i].axvline(mfe_all.quantile(0.60), color="darkgreen", linestyle="--", label="q60")
        axes[1, i].axvline(mfe_all.quantile(0.70), color="blue", linestyle="--", label="q70")
        axes[1, i].legend()
    
    plt.tight_layout()
    output_path = OUTPUT_PLOTS_DIR / f"{symbol}_mae_mfe_by_regime.png"
    plt.savefig(output_path, dpi=150)
    plt.close()
    
    logger.info(f"Saved plot: {output_path}")


def generate_markdown_report(all_stats: List[ExcursionStats]):
    """Generate human-readable Markdown report"""
    with open(OUTPUT_MD, "w") as f:
        f.write("# ATR-SLTP Calibration Report\n\n")
        f.write(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"**Data Source:** Binance USD-M Futures OHLCV (5m candles)\n\n")
        f.write(f"**Symbols:** {', '.join(SYMBOLS)}\n\n")
        f.write(f"**Horizon:** {HORIZON_MINUTES} minutes ({HORIZON_BARS} bars)\n\n")
        f.write(f"**ATR Period:** {ATR_PERIOD}\n\n")
        f.write(f"**Regime Thresholds:** LOW <= q{int(REGIME_LOW_THRESHOLD*100)}, MID <= q{int(REGIME_MID_THRESHOLD*100)}, HIGH > q{int(REGIME_MID_THRESHOLD*100)}\n\n")
        
        f.write("---\n\n")
        f.write("## Calibration Results by Symbol and Regime\n\n")
        
        for symbol in SYMBOLS:
            symbol_stats = [s for s in all_stats if s.symbol == symbol]
            
            if not symbol_stats:
                f.write(f"### {symbol}\n\n")
                f.write("**No data available**\n\n")
                continue
            
            f.write(f"### {symbol}\n\n")
            f.write("| Regime | ATR Frac (median) | k_sl_q90 | k_sl_q95 | k_tp_q50 | k_tp_q60 | k_tp_q70 | Samples |\n")
            f.write("|--------|-------------------|----------|----------|----------|----------|----------|----------|\n")
            
            for stat in symbol_stats:
                f.write(f"| {stat.regime} | {stat.atr_frac_median:.6f} | "
                       f"{stat.k_sl_q90:.2f} | {stat.k_sl_q95:.2f} | "
                       f"{stat.k_tp_q50:.2f} | {stat.k_tp_q60:.2f} | {stat.k_tp_q70:.2f} | "
                       f"{stat.sample_count} |\n")
            
            f.write("\n")
        
        f.write("---\n\n")
        f.write("## Recommended Defaults per Symbol\n\n")
        
        for symbol in SYMBOLS:
            symbol_stats = [s for s in all_stats if s.symbol == symbol]
            
            if not symbol_stats:
                continue
            
            f.write(f"### {symbol}\n\n")
            
            # TREND/HIGH regime
            high_stat = next((s for s in symbol_stats if s.regime == "HIGH"), None)
            if high_stat:
                f.write(f"**TREND/HIGH regime:**\n")
                f.write(f"- `k_sl = {high_stat.k_sl_q95:.2f}` (q95 MAE)\n")
                f.write(f"- `k_tp = {high_stat.k_tp_q60:.2f}` - `{high_stat.k_tp_q70:.2f}` (q60-q70 MFE)\n\n")
            
            # FLAT/LOW regime
            low_stat = next((s for s in symbol_stats if s.regime == "LOW"), None)
            if low_stat:
                f.write(f"**FLAT/LOW regime:**\n")
                f.write(f"- `k_sl = {low_stat.k_sl_q90:.2f}` (q90 MAE)\n")
                f.write(f"- `k_tp = {low_stat.k_tp_q50:.2f}` - `{low_stat.k_tp_q60:.2f}` (q50-q60 MFE)\n\n")
        
        f.write("---\n\n")
        f.write("## Notes\n\n")
        f.write("- **MAE (Maximum Adverse Excursion):** Maximum price movement against the position\n")
        f.write("- **MFE (Maximum Favorable Excursion):** Maximum price movement in favor of the position\n")
        f.write("- **k_sl, k_tp:** Multipliers to apply to ATR for SL/TP distances\n")
        f.write("- **ATR Frac:** ATR / entry_price (median)\n")
        f.write("- **Regime Proxy:** Based on rolling volatility quantiles (15m-equivalent window)\n")
        f.write("- **Horizon:** Forward-looking window for MAE/MFE computation\n\n")
    
    logger.info(f"Generated report: {OUTPUT_MD}")


def generate_csv_report(all_stats: List[ExcursionStats]):
    """Generate CSV report with tabular data"""
    records = []
    
    for stat in all_stats:
        records.append({
            "symbol": stat.symbol,
            "regime": stat.regime,
            "atr_frac_median": stat.atr_frac_median,
            "k_sl_q90": stat.k_sl_q90,
            "k_sl_q95": stat.k_sl_q95,
            "k_tp_q50": stat.k_tp_q50,
            "k_tp_q60": stat.k_tp_q60,
            "k_tp_q70": stat.k_tp_q70,
            "sample_count": stat.sample_count
        })
    
    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_CSV, index=False)
    
    logger.info(f"Generated CSV: {OUTPUT_CSV}")


def main():
    """Main research workflow"""
    logger.info("=" * 80)
    logger.info("ATR-SLTP-CALIBRATION-01 Research Script")
    logger.info("=" * 80)
    
    all_stats = []
    
    for symbol in SYMBOLS:
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Processing {symbol}")
        logger.info(f"{'=' * 80}")
        
        # 1. Load data - use API for fresh data (last 30 days: 07.12.2025 - 07.01.2026)
        logger.info(f"Loading fresh data for {symbol} (last 30 days)")
        df = download_binance_klines_api(symbol, INTERVAL_5M, limit=1000, days_back=30)
        
        if df.empty:
            logger.error(f"Failed to load data for {symbol}, skipping")
            continue
        
        # 2. Compute returns
        df = compute_returns(df)
        
        # 3. Compute ATR
        df = compute_atr(df, period=ATR_PERIOD)
        
        # 4. Compute robust volatility
        df = compute_robust_volatility(df, period=ATR_PERIOD)
        
        # 5. Compute regime proxy
        df = compute_regime_proxy(df, window=3)
        
        # 6. Compute MAE/MFE excursions
        logger.info(f"Computing MAE/MFE excursions (horizon={HORIZON_BARS} bars)...")
        df = compute_mae_mfe_excursions(df, horizon_bars=HORIZON_BARS)
        
        # 7. Calibrate multipliers by regime
        logger.info(f"Calibrating ATR multipliers by regime...")
        symbol_stats = calibrate_multipliers_by_regime(df, symbol)
        all_stats.extend(symbol_stats)
        
        # 8. Generate plots
        logger.info(f"Generating MAE/MFE distribution plots...")
        plot_mae_mfe_distributions(df, symbol)
    
    # 9. Generate reports
    logger.info("\n" + "=" * 80)
    logger.info("Generating final reports...")
    logger.info("=" * 80)
    
    generate_markdown_report(all_stats)
    generate_csv_report(all_stats)
    
    logger.info("\n" + "=" * 80)
    logger.info("ATR-SLTP-CALIBRATION-01 Research Complete")
    logger.info("=" * 80)
    logger.info(f"Reports saved to:")
    logger.info(f"  - {OUTPUT_MD}")
    logger.info(f"  - {OUTPUT_CSV}")
    logger.info(f"  - {OUTPUT_PLOTS_DIR}/")


if __name__ == "__main__":
    main()
