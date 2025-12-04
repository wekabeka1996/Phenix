"""
Optuna Runner for R&D Pipeline
Balanced objective function: Calmar - λ*MaxDD with trade count penalty
"""

import optuna
import pandas as pd
from typing import Dict, Any

from apps.research.momentum_backtest.walk_forward import run_walk_forward_for_params


# Global reference to features DataFrame (set before optimization)
_df_features_global = None


def build_search_space(trial: optuna.Trial) -> dict:
    """
    Define parameter search space for momentum/scalping strategy.
    Updated for RND-OBJECTIVE-V2 (phi-features [0,1]).
    
    Returns:
        Dictionary of strategy parameters
    """
    params = {}
    
    # Feature weights (for [0,1] phi-features)
    # All weights 0.0 to 1.0, allowing optimizer to find balance
    params["w_tfi"] = trial.suggest_float("w_tfi", 0.0, 1.0)
    params["w_tob"] = trial.suggest_float("w_tob", 0.0, 1.0)
    params["w_bs"] = trial.suggest_float("w_bs", 0.0, 1.0)
    params["w_bl"] = trial.suggest_float("w_bl", 0.0, 1.0)
    params["w_macro"] = trial.suggest_float("w_macro", 0.0, 1.0)
    # Extended weights (Tier 1: Config Gap Analysis)
    params["w_delta_price"] = trial.suggest_float("w_delta_price", 0.0, 1.0)
    params["w_volume_spike"] = trial.suggest_float("w_volume_spike", 0.0, 1.0)
    params["w_volatility_state"] = trial.suggest_float("w_volatility_state", 0.0, 1.0)
    params["w_depth_imbalance"] = trial.suggest_float("w_depth_imbalance", 0.0, 1.0)
    
    # Entry threshold (for additive score of [0,1] features)
    # Score range approx 0 to sum(weights). Typically 0.5-2.0 range.
    # Threshold 0.05-0.25 covers sensitive to conservative entries.
    params["threshold"] = trial.suggest_float("threshold", 0.05, 0.25)
    
    # Entry Gates (Depth Mode)
    params["depth_imbalance_phi_min"] = trial.suggest_float("depth_imbalance_phi_min", 0.6, 0.95)
    params["tob_phi_min"] = trial.suggest_float("tob_phi_min", 0.6, 0.95)
    params["ema_bias_long_phi_min"] = trial.suggest_float("ema_bias_long_phi_min", 0.4, 0.7)
    params["vol_state_phi_min"] = trial.suggest_float("vol_state_phi_min", 0.05, 0.2)
    params["vol_state_phi_max"] = trial.suggest_float("vol_state_phi_max", 0.6, 0.95)
    
    # Risk parameters (Refined for Depth Mode)
    params["sl_pct"] = trial.suggest_float("sl_pct", 0.002, 0.007)  # 0.2%-0.7% (tighter SL)
    params["sl_tp_ratio"] = trial.suggest_float("sl_tp_ratio", 1.0, 4.0) # Wider TP range
    params["max_holding_secs"] = trial.suggest_int("max_holding_secs", 60, 600) # Optimize time stop
    
    # Funding veto threshold
    params["funding_threshold_long"] = trial.suggest_float("funding_threshold_long", 0.0003, 0.0010)
    
    # Fixed parameters (not optimized)
    params["position_size"] = 200.0
    params["commission"] = 0.0005
    params["slippage"] = 0.0001
    params["spread_half"] = 0.0001
    
    return params


def objective(trial: optuna.Trial) -> float:
    """
    Balanced objective function for Optuna (V2).
    
    Priorities:
    1. Min trades constraint (>200/month)
    2. Positive Calmar > Negative Calmar
    3. If Calmar > 0: Maximize Calmar (Minimize -Calmar)
    4. If Calmar <= 0: Maximize PnL and Minimize DD
    
    Args:
        trial: Optuna trial
        
    Returns:
        Score to minimize (lower is better)
    """
    global _df_features_global
    
    if _df_features_global is None:
        raise ValueError("Must set _df_features_global before running optimization")
    
    # Build parameters
    params = build_search_space(trial)
    
    # Run Walk-Forward validation
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
    
    # Log metrics as user attributes
    trial.set_user_attr("total_trades", total_trades)
    trial.set_user_attr("calmar", calmar)
    trial.set_user_attr("max_dd_pct", max_dd_pct)
    trial.set_user_attr("pnl_usd", pnl)
    trial.set_user_attr("win_rate", metrics.get("win_rate", 0.0))
    
    # 1. Minimum Trades Constraint
    # We want robust statistical significance, so ~200 trades/month minimum.
    # If < 200, apply heavy penalty proportional to missing trades.
    MIN_TRADES = 200
    if total_trades < MIN_TRADES:
        # Penalty: 1000 + missing trades
        # This ensures 199 trades is better than 50 trades, but all are worse than valid runs.
        score = 1000.0 + (MIN_TRADES - total_trades)
        print(f"  Trial {trial.number}: {total_trades} trades (<{MIN_TRADES}) - PENALTY Score={score:.1f}")
        return score
    
    # 2. Balanced Objective
    # We MINIMIZE this score.
    
    if calmar > 0:
        # POSITIVE CALMAR (Good)
        # Score range: [-inf, 0]
        # Higher Calmar = Lower Score (Better)
        # Example: Calmar 5.0 -> Score -5.0
        score = -calmar
    else:
        # NEGATIVE/ZERO CALMAR (Bad)
        # Score range: [10, +inf]
        # We want to distinguish "bad" from "very bad".
        # Better PnL (less negative) -> Lower Score
        # Lower DD -> Lower Score
        
        # Base penalty for failing to be profitable
        base_penalty = 10.0
        
        # PnL component: PnL is likely negative.
        # -PnL gives positive value. We want to minimize it.
        # Scale: $100 loss -> +0.1 penalty
        pnl_penalty = -pnl * 0.001 
        
        # DD component: MaxDD is positive %.
        # Scale: 10% DD -> +1.0 penalty
        dd_penalty = max_dd_pct * 10.0
        
        score = base_penalty + pnl_penalty + dd_penalty
    
    print(f"  Trial {trial.number}: Trades={total_trades}, Calmar={calmar:.3f}, PnL={pnl:.2f}, Score={score:.3f}")
    
    return score


def run_optuna_study(
    df_features: pd.DataFrame,
    n_trials: int = 50,
    storage_url: str = None,
) -> optuna.Study:
    """
    Run Optuna optimization study.
    
    Args:
        df_features: Features DataFrame
        n_trials: Number of trials to run
        storage_url: Optional SQLite URL for persistence
        
    Returns:
        Optuna Study object
    """
    global _df_features_global
    _df_features_global = df_features
    
    print("="*60)
    print(f"OPTUNA STUDY: {n_trials} trials")
    print("="*60)
    
    # Create study
    sampler = optuna.samplers.TPESampler(seed=42)
    
    study = optuna.create_study(
        direction="minimize",
        sampler=sampler,
        study_name="bnb_momentum_wf_v1",
        storage=storage_url,
        load_if_exists=True if storage_url else False,
    )
    
    # Optimize
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    
    # Print best result
    best = study.best_trial
    print("\n" + "="*60)
    print("BEST TRIAL FOUND")
    print("="*60)
    print(f"Score: {best.value:.3f}")
    print(f"\nBest parameters:")
    for key, value in best.params.items():
        print(f"  {key}: {value:.4f}" if isinstance(value, float) else f"  {key}: {value}")
    
    print(f"\nMetrics:")
    print(f"  Total trades: {best.user_attrs.get('total_trades', 'N/A')}")
    print(f"  Calmar ratio: {best.user_attrs.get('calmar', 'N/A'):.3f}")
    print(f"  Max DD: {best.user_attrs.get('max_dd_pct', 'N/A'):.3f}")
    print(f"  PnL: ${best.user_attrs.get('pnl_usd', 'N/A'):.2f}")
    print(f"  Win rate: {best.user_attrs.get('win_rate', 'N/A'):.1%}")
    
    return study
