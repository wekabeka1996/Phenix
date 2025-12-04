#!/bin/bash
# Run build_features.py in parallel for all symbols

export PYTHONPATH=$PYTHONPATH:.

echo "Starting parallel feature build..."

# BTC (3m & 5m)
nohup python3 apps/research/aurora_optuna/build_features.py --symbol BTCUSDT --year 2024 --month 02 --timeframe 3m > /tmp/feat_btc_3m.log 2>&1 &
nohup python3 apps/research/aurora_optuna/build_features.py --symbol BTCUSDT --year 2024 --month 02 --timeframe 5m > /tmp/feat_btc_5m.log 2>&1 &

# SOL (3m)
nohup python3 apps/research/aurora_optuna/build_features.py --symbol SOLUSDT --year 2024 --month 02 --timeframe 3m > /tmp/feat_sol_3m.log 2>&1 &

# ETH (5m)
nohup python3 apps/research/aurora_optuna/build_features.py --symbol ETHUSDT --year 2024 --month 02 --timeframe 5m > /tmp/feat_eth_5m.log 2>&1 &

# XRP (3m)
nohup python3 apps/research/aurora_optuna/build_features.py --symbol XRPUSDT --year 2024 --month 02 --timeframe 3m > /tmp/feat_xrp_3m.log 2>&1 &

# DOGE (3m)
nohup python3 apps/research/aurora_optuna/build_features.py --symbol DOGEUSDT --year 2024 --month 02 --timeframe 3m > /tmp/feat_doge_3m.log 2>&1 &

echo "All processes launched. Check logs in /tmp/feat_*.log"
