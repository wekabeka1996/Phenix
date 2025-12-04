import optuna
import pandas as pd
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, ".")

from apps.research.momentum_backtest.walk_forward import run_walk_forward_for_params

# Global reference
_df_features_global = None

def build_search_space_high_leverage(trial: optuna.Trial) -> dict:
    """
    Search space for High-Leverage Strategy (x50-x75).
    Exits based on ROI: TP +40-50%, SL -25%.
    """
    params = {}
    
    # 1. Leverage & ROI Logic
    # Leverage: x50 to x75
    leverage = trial.suggest_int("leverage", 50, 75)
    
    # ROI Targets
    # TP: 40% to 50% ROI
    roi_tp = trial.suggest_float("roi_tp", 0.40, 0.50)
    
    # SL: Fixed 25% ROI (as requested) or small range?
    # User said: "якщо -25% ордер закривається" -> Fixed 25%
    roi_sl = 0.25
    
    # Convert to Price Movement %
    # Price Move = ROI / Leverage
    # Example: 50% ROI / 50x = 1% Price Move
    tp_pct = roi_tp / leverage
    sl_pct = roi_sl / leverage
    
    # Backtest engine uses sl_pct and sl_tp_ratio
    params["sl_pct"] = sl_pct
    params["sl_tp_ratio"] = tp_pct / sl_pct  # = roi_tp / roi_sl
    
    # Store leverage/roi for reference (not used by engine directly but good for logs)
    trial.set_user_attr("leverage", leverage)
    trial.set_user_attr("roi_tp", roi_tp)
    trial.set_user_attr("roi_sl", roi_sl)
    
    # 2. Signal Logic (Parity Aligned)
    # Weights for [0,1] phi-features
    params["w_tfi"] = trial.suggest_float("w_tfi", 0.0, 1.0)
    params["w_tob"] = trial.suggest_float("w_tob", 0.0, 1.0)
    params["w_bs"] = trial.suggest_float("w_bs", 0.0, 1.0)
    params["w_bl"] = trial.suggest_float("w_bl", 0.0, 1.0)
    params["w_macro"] = trial.suggest_float("w_macro", 0.0, 1.0)
    
    # Threshold
    params["threshold"] = trial.suggest_float("threshold", 0.05, 0.25)
    
    # Funding veto
    params["funding_threshold_long"] = trial.suggest_float("funding_threshold_long", 0.0003, 0.0010)
    
    # Fixed parameters
    params["max_holding_secs"] = 300
    params["position_size"] = 200.0 # Notional size. Margin = 200/leverage.
    params["commission"] = 0.0005
    params["slippage"] = 0.0001
    params["spread_half"] = 0.0001
    
    return params

def objective_high_leverage(trial: optuna.Trial) -> float:
    """
    Objective for High-Leverage Strategy.
    Prioritizes robust returns under tight SL constraints.
    """
    global _df_features_global
    
    if _df_features_global is None:
        raise ValueError("Must set _df_features_global")
    
    params = build_search_space_high_leverage(trial)
    
    # Run Walk-Forward
    metrics = run_walk_forward_for_params(
        _df_features_global,
        params,
        train_days=21,
        test_days=7,
        step_days=7
    )
    
    total_trades = metrics["total_trades"]
    calmar = metrics["calmar"]
    max_dd_pct = metrics["max_drawdown_pct"]
    pnl = metrics["total_pnl_usd"]
    
    # Log metrics
    trial.set_user_attr("total_trades", total_trades)
    trial.set_user_attr("calmar", calmar)
    trial.set_user_attr("max_dd_pct", max_dd_pct)
    trial.set_user_attr("pnl_usd", pnl)
    trial.set_user_attr("win_rate", metrics.get("win_rate", 0.0))
    
    # 1. Min Trades Constraint
    # High leverage scalping needs frequency.
    MIN_TRADES = 150 # Slightly lower min for high leverage? Or keep 200?
    if total_trades < MIN_TRADES:
        score = 1000.0 + (MIN_TRADES - total_trades)
        return score
    
    # 2. Objective
    # Minimize -Calmar, Minimize DD
    
    if calmar > 0:
        score = -calmar
    else:
        # Negative Calmar
        # Base 10
        # PnL penalty
        # DD penalty (Heavier penalty for DD in high leverage?)
        # Actually backtest engine calculates DD on Equity (which assumes fixed position size).
        # So DD% is comparable.
        
        base_score = 10.0
        pnl_penalty = -pnl * 0.001
        dd_penalty = max_dd_pct * 10.0
        
        score = base_score + pnl_penalty + dd_penalty
        
    return score

def run_high_leverage_study():
    global _df_features_global
    
    print("="*60)
    print("OPTUNA HIGH LEVERAGE (x50-x75) STUDY")
    print("="*60)
    
    # Load features
    features_path = "apps/research/momentum_backtest/data/BNBUSDT-features-2024-03.csv"
    print(f"Loading features from {features_path}...")
    df = pd.read_csv(features_path)
    df['ts'] = pd.to_datetime(df['ts'])
    _df_features_global = df
    
    # Create study
    study = optuna.create_study(
        direction="minimize",
        study_name="bnb_high_leverage_v1",
        storage="sqlite:///apps/research/momentum_backtest/data/optuna_high_leverage.db",
        load_if_exists=True
    )
    
    # Optimize
    study.optimize(objective_high_leverage, n_trials=200) # 200 trials for full run
    
    print("\nBest High-Leverage Trial:")
    best = study.best_trial
    print(f"Score: {best.value:.3f}")
    print(f"Params: {best.params}")
    print(f"Leverage: {best.user_attrs.get('leverage')}")
    print(f"ROI TP: {best.user_attrs.get('roi_tp'):.1%}")
    print(f"ROI SL: {best.user_attrs.get('roi_sl'):.1%}")
    print(f"Metrics: Trades={best.user_attrs.get('total_trades')}, PnL=${best.user_attrs.get('pnl_usd'):.2f}")

if __name__ == "__main__":
    run_high_leverage_study()
