"""
Тести для Behavior Reward Component

Тестування компоненти розрахунку винагороди за поведінкові паттерни агента.

Автор: ALYSHA система
Версія: V3+
"""

import unittest
import tempfile
import os
import yaml
import numpy as np
from typing import Dict, Any

from alysha_core.reward_engine_v3plus.components.behavior import BehaviorRewardComponent
from alysha_core.reward_engine_v3plus.data_types import (
    ARCEData, PortfolioData, StateData, ExecutionData, AgentActionData, FillData,
    MarketRegime, PnLData
)
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig


class TestBehaviorRewardComponent(unittest.TestCase):
    """Тестовий клас для Behavior Reward Component"""
    
    def setUp(self):
        """Налаштування перед кожним тестом"""
        # Тестова конфігурація
        self.test_config = {
            "components": {
                "behavior": {
                    "enabled": True
                }
            },
            "behavior_component": {
                "enabled": True,
                "beta_strategy": 1.0,
                "beta_frequency": 0.5,
                "beta_latency": 0.3,
                "strategy_consistency": {
                    "consistency_window": 20,
                    "directional_weight": 0.7,
                    "magnitude_weight": 0.3,
                    "baseline_consistency": 0.5
                },
                "trading_frequency": {
                    "frequency_window": 50,
                    "optimal_frequency": 5.0,
                    "frequency_tolerance": 2.0,
                    "penalty_rate": 0.1
                },
                "execution_latency": {
                    "target_latency": 0.1,
                    "latency_tolerance": 0.05,
                    "latency_penalty_rate": 2.0,
                    "latency_history_size": 100
                }
            },
            "validation": {
                "default_safe_reward": -10.0
            }
        }
        
        # Створюємо тимчасовий файл конфігурації
        self.temp_config_file = tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False
        )
        yaml.dump(self.test_config, self.temp_config_file)
        self.temp_config_file.close()
        
        # Створюємо конфігурацію та компоненту
        self.config = RewardEngineConfig(self.temp_config_file.name)
        self.behavior_component = BehaviorRewardComponent(self.config)
        
    def tearDown(self):
        """Очищення після тестів"""
        os.unlink(self.temp_config_file.name)
        
    def create_test_arce_data(self, **kwargs) -> ARCEData:
        """Створення тестових ARCE даних"""
        defaults = {
            "var_current": 0.05,
            "var_limit": 0.1,
            "cvar_current": 0.08,
            "cvar_limit": 0.15,
            "drawdown_current": 0.02,
            "drawdown_limit": 0.1,
            "portfolio_volatility": 0.12,
            "target_volatility": 0.12,
            "volatility_range": 0.05,
            "active_flags": [],
            "regime_tag": MarketRegime.STABLE,  # Mapped from NORMAL
            "position_limits": {"BTCUSDT": 10.0, "ETHUSDT": 5.0}
        }
        defaults.update(kwargs)
        return ARCEData(**defaults)
        
    def create_test_portfolio_data(self, **kwargs) -> PortfolioData:
        """Створення тестових даних портфеля"""
        defaults = {
            "positions": {"BTCUSDT": 1.0, "ETHUSDT": 0.5},
            "current_weights": {"BTCUSDT": 0.7, "ETHUSDT": 0.3},
            "target_weights": {"BTCUSDT": 0.6, "ETHUSDT": 0.4},
            "total_value": 10000.0,
            "turnover": 0.1
        }
        defaults.update(kwargs)
        return PortfolioData(**defaults)
        
    def create_test_agent_action(self, **kwargs) -> AgentActionData:
        """Створення тестових даних дій агента"""
        defaults = {
            "action_vector": np.array([0.1, -0.05, 0.0]),
            "action_type": "REBALANCE",
            "action_direction": 1,
            "is_exploratory": False
        }
        defaults.update(kwargs)
        return AgentActionData(**defaults)
        
    def create_test_execution_data(self, **kwargs) -> ExecutionData:
        """Створення тестових даних виконання"""
        defaults = {
            "trades": [],
            "fills": [],
            "num_order_modifications": 0,
            "num_order_cancellations": 0,
            "bid_ask_spreads": {},
            "transaction_fees": {},
            "slippage_costs": {}
        }
        defaults.update(kwargs)
        return ExecutionData(**defaults)
        
    def create_test_state_data(self, agent_action: AgentActionData = None, 
                              execution_data: ExecutionData = None) -> StateData:
        """Створення тестових даних стану"""
        if agent_action is None:
            agent_action = self.create_test_agent_action()
        if execution_data is None:
            execution_data = self.create_test_execution_data()
            
        return StateData(
            timestamp=1640995200.0,
            portfolio=self.create_test_portfolio_data(),
            arce=self.create_test_arce_data(),
            pnl=PnLData(realized_pnl=0.0, unrealized_pnl=0.0, asset_pnl={}),
            market_data={},
            agent_action=agent_action,
            execution=execution_data
        )
        
    def test_no_behavior_data(self):
        """Тест 1.4.T1.1: Сценарій без поведінкових даних"""
        # Створюємо state без agent_action
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = StateData(
            timestamp=1640995200.0,
            portfolio=portfolio_data,
            arce=arce_data,
            pnl=PnLData(realized_pnl=0.0, unrealized_pnl=0.0, asset_pnl={}),
            market_data={},
            agent_action=None,
            execution=None
        )
        
        result = self.behavior_component.calculate(arce_data, portfolio_data, state_data)
        
        self.assertEqual(result.component_name, "behavior")
        self.assertAlmostEqual(result.raw_value, 0.0, places=6)
        
        # Перевіряємо всі підкомпоненти
        self.assertAlmostEqual(result.subcomponents["strategy_consistency"], 0.0)
        self.assertAlmostEqual(result.subcomponents["trading_frequency"], 0.0)
        self.assertAlmostEqual(result.subcomponents["execution_latency"], 0.0)
        
    def test_single_action(self):
        """Тест 1.4.T1.2: Перша дія агента"""
        agent_action = self.create_test_agent_action()
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(agent_action=agent_action)
        
        result = self.behavior_component.calculate(arce_data, portfolio_data, state_data)
        
        self.assertEqual(result.component_name, "behavior")
        
        # При першій дії стратегічна консистентність має бути 0
        self.assertAlmostEqual(result.subcomponents["strategy_consistency"], 0.0)
        
    def test_consistent_actions(self):
        """Тест 1.4.T1.3: Консистентні дії агента"""
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        
        # Симулюємо серію консистентних дій
        consistent_actions = [
            self.create_test_agent_action(
                action_vector=np.array([0.1, -0.05, 0.0]),
                action_direction=1,
                action_type="BUY"
            ) for _ in range(10)
        ]
        
        # Додаємо дії по одній і перевіряємо консистентність
        for i, action in enumerate(consistent_actions):
            state_data = self.create_test_state_data(agent_action=action)
            result = self.behavior_component.calculate(arce_data, portfolio_data, state_data)
            
            if i > 5:  # Після кількох дій повинна з'явитися консистентність
                self.assertGreaterEqual(result.subcomponents["strategy_consistency"], 0.0)
                
    def test_inconsistent_actions(self):
        """Тест 1.4.T1.4: Неконсистентні дії агента"""
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        
        # Симулюємо серію неконсистентних дій
        inconsistent_actions = [
            self.create_test_agent_action(
                action_vector=np.array([0.1, -0.05, 0.0]),
                action_direction=1,
                action_type="BUY"
            ),
            self.create_test_agent_action(
                action_vector=np.array([-0.2, 0.1, 0.05]),
                action_direction=-1,
                action_type="SELL"
            ),
            self.create_test_agent_action(
                action_vector=np.array([0.0, 0.0, 0.0]),
                action_direction=0,
                action_type="HOLD"
            ),
            self.create_test_agent_action(
                action_vector=np.array([0.15, -0.08, 0.02]),
                action_direction=1,
                action_type="BUY"
            )
        ]
        
        # Додаємо неконсистентні дії
        for action in inconsistent_actions:
            state_data = self.create_test_state_data(agent_action=action)
            result = self.behavior_component.calculate(arce_data, portfolio_data, state_data)
            
        # Остання дія повинна показати низьку консистентність
        self.assertLessEqual(result.subcomponents["strategy_consistency"], 0.5)
        
    def test_execution_latency(self):
        """Тест 1.4.T1.5: Латентність виконання"""
        # Створюємо fills з різною латентністю
        current_time = 1640995200.0
        
        # Гарна латентність (50ms)
        good_fills = [
            FillData(
                asset_id="BTCUSDT",
                fill_price=50000.0,
                expected_price=50000.0,
                quantity=0.1,
                timestamp=current_time - 0.05  # 50ms назад
            )
        ]
        
        # Погана латентність (200ms)
        bad_fills = [
            FillData(
                asset_id="BTCUSDT", 
                fill_price=50000.0,
                expected_price=50000.0,
                quantity=0.1,
                timestamp=current_time - 0.2  # 200ms назад
            )
        ]
        
        # Тест з гарною латентністю
        execution_data_good = self.create_test_execution_data(fills=good_fills)
        state_data_good = self.create_test_state_data(execution_data=execution_data_good)
        result_good = self.behavior_component.calculate(
            self.create_test_arce_data(), 
            self.create_test_portfolio_data(), 
            state_data_good
        )
        
        # Тест з поганою латентністю
        execution_data_bad = self.create_test_execution_data(fills=bad_fills)
        state_data_bad = self.create_test_state_data(execution_data=execution_data_bad)
        result_bad = self.behavior_component.calculate(
            self.create_test_arce_data(),
            self.create_test_portfolio_data(),
            state_data_bad
        )
        
        # Гарна латентність повинна давати кращу винагороду
        self.assertGreater(
            result_good.subcomponents["execution_latency"],
            result_bad.subcomponents["execution_latency"]
        )
        
    def test_component_disabled(self):
        """Тест 1.4.T1.6: Компонента вимкнена"""
        # Змінюємо конфігурацію для вимкнення компоненти
        disabled_config = self.test_config.copy()
        disabled_config["behavior_component"]["enabled"] = False
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        yaml.dump(disabled_config, temp_file)
        temp_file.close()
        
        try:
            config = RewardEngineConfig(temp_file.name)
            behavior_component = BehaviorRewardComponent(config)
            
            arce_data = self.create_test_arce_data()
            portfolio_data = self.create_test_portfolio_data()
            state_data = self.create_test_state_data()
            
            result = behavior_component.calculate(arce_data, portfolio_data, state_data)
            
            self.assertEqual(result.component_name, "behavior")
            self.assertEqual(result.raw_value, 0.0)
            self.assertIn("disabled", result.subcomponents)
            
        finally:
            os.unlink(temp_file.name)
            
    def test_formula_calculation(self):
        """Тест 1.4.T1.7: Перевірка формули розрахунку"""
        agent_action = self.create_test_agent_action()
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(agent_action=agent_action)
        
        result = self.behavior_component.calculate(arce_data, portfolio_data, state_data)
        
        # Перевіряємо формулу: R_Behavior = β_strategy * Φ_strategy + β_freq * Φ_frequency + β_latency * Φ_latency
        expected_total = (
            self.behavior_component.beta_strategy * result.subcomponents["strategy_consistency"] +
            self.behavior_component.beta_frequency * result.subcomponents["trading_frequency"] +
            self.behavior_component.beta_latency * result.subcomponents["execution_latency"]
        )
        
        self.assertAlmostEqual(result.raw_value, expected_total, places=6)
        
        # Перевіряємо зважені компоненти
        self.assertAlmostEqual(
            result.subcomponents["strategy_weighted"],
            self.behavior_component.beta_strategy * result.subcomponents["strategy_consistency"],
            places=6
        )
        
    def test_component_info(self):
        """Тест 1.4.T1.8: Інформація про компоненту"""
        info = self.behavior_component.get_component_info()
        
        self.assertEqual(info["component_name"], "behavior")
        self.assertTrue(info["enabled"])
        self.assertIn("beta_coefficients", info)
        self.assertIn("subcomponents", info)
        self.assertIn("history_stats", info)
        
        # Перевіряємо бета коефіцієнти
        betas = info["beta_coefficients"]
        self.assertEqual(betas["strategy"], 1.0)
        self.assertEqual(betas["frequency"], 0.5)
        self.assertEqual(betas["latency"], 0.3)


if __name__ == '__main__':
    unittest.main()
