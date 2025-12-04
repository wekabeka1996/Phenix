"""
TASK: RND-BACKTEST-DEBUG-ZERO-TRADES

Синтетичний тест для виявлення причини нуль трейдів.
Використовуємо тривіальні дані (10-20 сек, лінійний ап-тренд).
"""

import pandas as pd
import numpy as np
import pytest
from apps.research.momentum_backtest.backtest_engine import BacktestEngine


def test_synthetic_uptrend_must_generate_trades():
    """
    Мінімальний синтетичний тест:
    - 20 секунд даних
    - Лінійне зростання ціни 100 → 110
    - tfi_1m = 1.0 (завжди позитивний)
    - threshold = 0.0 (сигнал завжди = 1)
    - funding veto вимкнено (threshold = 1.0 >> funding_rate = 0.0)
    
    Очікування: >= 1 трейд має бути виконаний
    """
    
    # Створюємо синтетичні дані
    n_seconds = 20
    
    data = {
        'ts': pd.date_range(start='2024-01-01 00:00:00', periods=n_seconds, freq='1s'),
        'open_1s': np.linspace(100, 110, n_seconds),
        'high_1s': np.linspace(100, 110, n_seconds),
        'low_1s': np.linspace(100, 110, n_seconds),
        'close_1s': np.linspace(100, 110, n_seconds),
        'tfi_1m': [1.0] * n_seconds,  # Завжди позитивний
        'tob_imbalance': [0.0] * n_seconds,
        'ema_bias_short': [0.0] * n_seconds,
        'ema_bias_long': [0.0] * n_seconds,
        'vol_state': [1.0] * n_seconds,
        'macro_corr_1h': [0.0] * n_seconds,
        'funding_rate_1s': [0.0] * n_seconds,
        'funding_norm': [0.0] * n_seconds
    }
    
    df = pd.DataFrame(data)
    
    # Параметри: максимально агресивні для гарантії сигналів
    params = {
        'w_tfi': 1.0,
        'w_tob': 0.0,
        'w_bs': 0.0,
        'w_bl': 0.0,
        'threshold': 0.0,  # tfi=1.0 > 0.0 → signal=1
        'sl_pct': 0.01,  # 1% SL
        'sl_tp_ratio': 2.0,  # 2% TP
        'macro_corr_weight': 0.0,
        'funding_threshold_long': 1.0,  # Дуже високий, не блокує
        'max_holding_secs': 300,
        'position_size': 100.0,
        'commission': 0.0005,
        'slippage': 0.0001,
        'spread_half': 0.0001
    }
    
    # Запускаємо backtest
    engine = BacktestEngine(df, params)
    results = engine.run()
    
    # Діагностика
    print(f"\n=== SYNTHETIC TEST DIAGNOSTICS ===")
    print(f"Total rows: {len(df)}")
    print(f"Trades executed: {len(results['trades'])}")
    print(f"Total PnL: {results['metrics']['total_pnl']}")
    
    if results['trades']:
        print(f"\nFirst trade:")
        print(f"  Entry: {results['trades'][0].entry_time} @ {results['trades'][0].entry_price}")
        print(f"  Exit: {results['trades'][0].exit_time} @ {results['trades'][0].exit_price}")
        print(f"  Reason: {results['trades'][0].exit_reason}")
        print(f"  PnL: {results['trades'][0].pnl}")
    else:
        print("\n❌ ZERO TRADES - BUG CONFIRMED")
    
    # Assertions
    assert len(results['trades']) >= 1, "Synthetic uptrend MUST generate at least 1 trade!"
    assert not np.isnan(results['metrics']['total_pnl']), "PnL должен быть числом"


def test_synthetic_multiple_signals():
    """
    Тест з кількома періодами сигналів:
    - 0-5s: tfi = 1.0 (сигнал)
    - 6-10s: tfi = -1.0 (no signal)
    - 11-15s: tfi = 1.0 (сигнал)
    
    Очікування: >= 2 трейди (один на 0-5s, один на 11-15s)
    """
    
    n_seconds = 16
    
    # TFI патерн: позитив -> негатив -> позитив
    tfi_pattern = [1.0]*6 + [-1.0]*5 + [1.0]*5
    
    data = {
        'ts': pd.date_range(start='2024-01-01 00:00:00', periods=n_seconds, freq='1s'),
        'open_1s': [100.0] * n_seconds,
        'high_1s': [101.0] * n_seconds,
        'low_1s': [99.0] * n_seconds,
        'close_1s': [100.0] * n_seconds,
        'tfi_1m': tfi_pattern,
        'tob_imbalance': [0.0] * n_seconds,
        'ema_bias_short': [0.0] * n_seconds,
        'ema_bias_long': [0.0] * n_seconds,
        'vol_state': [1.0] * n_seconds,
        'macro_corr_1h': [0.0] * n_seconds,
        'funding_rate_1s': [0.0] * n_seconds,
        'funding_norm': [0.0] * n_seconds
    }
    
    df = pd.DataFrame(data)
    
    params = {
        'w_tfi': 1.0,
        'w_tob': 0.0,
        'w_bs': 0.0,
        'w_bl': 0.0,
        'threshold': 0.0,
        'sl_pct': 0.01,
        'sl_tp_ratio': 2.0,
        'macro_corr_weight': 0.0,
        'funding_threshold_long': 1.0,
        'max_holding_secs': 5,  # Короткий холд для швидкого time exit
        'position_size': 100.0,
        'commission': 0.0005,
        'slippage': 0.0001,
        'spread_half': 0.0001
    }
    
    engine = BacktestEngine(df, params)
    results = engine.run()
    
    print(f"\n=== MULTIPLE SIGNALS TEST ===")
    print(f"Total trades: {len(results['trades'])}")
    
    # Можемо очікувати 1-2 трейди в залежності від time exit
    assert len(results['trades']) >= 1, "Should generate at least 1 trade with multiple signal periods"


if __name__ == "__main__":
    # Запуск тестів з детальним виводом
    pytest.main([__file__, "-v", "-s"])
