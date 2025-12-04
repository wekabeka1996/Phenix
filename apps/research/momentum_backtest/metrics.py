import pandas as pd
import numpy as np

def calculate_metrics(trades: list, equity_curve: pd.Series) -> dict:
    """
    Calculate performance metrics from trades and equity curve.
    """
    if not trades:
        return {
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "total_trades": 0,
            "max_drawdown": 0.0,
            "calmar_ratio": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0
        }
        
    df_trades = pd.DataFrame([t.__dict__ for t in trades])
    
    total_pnl = df_trades['pnl'].sum()
    total_trades = len(df_trades)
    win_rate = len(df_trades[df_trades['pnl'] > 0]) / total_trades if total_trades > 0 else 0.0
    
    # Max Drawdown
    # Equity curve is a Series of equity values over time
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    max_drawdown = drawdown.min() # Negative value
    
    # Calmar Ratio
    # Annualized Return / Max Drawdown
    # Assuming equity curve covers the period.
    # We need duration.
    if len(equity_curve) > 1:
        duration_seconds = (equity_curve.index[-1] - equity_curve.index[0]).total_seconds()
        duration_years = duration_seconds / (365 * 24 * 3600)
        
        initial_equity = equity_curve.iloc[0]
        final_equity = equity_curve.iloc[-1]
        
        if initial_equity > 0:
            total_return = (final_equity - initial_equity) / initial_equity
            annualized_return = total_return / duration_years if duration_years > 0 else 0.0
            
            calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0.0
        else:
            calmar_ratio = 0.0
    else:
        calmar_ratio = 0.0
        
    return {
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar_ratio
    }
