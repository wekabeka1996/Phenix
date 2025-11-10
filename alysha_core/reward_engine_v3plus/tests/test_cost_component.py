"""
Тести для Cost Reward Component

Тестування компоненти розрахунку винагороди за витрати транзакцій.

Автор: ALYSHA система
Версія: V3+
"""

import unittest
import tempfile
import os
import yaml
from typing import Dict, Any

from alysha_core.reward_engine_v3plus.components.cost import CostRewardComponent
from alysha_core.reward_engine_v3plus.data_types import (
    ARCEData, PortfolioData, StateData, ExecutionData, TradeData, FillData, 
    MarketRegime, PnLData
)
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig


class TestCostRewardComponent(unittest.TestCase):
    """Тестовий клас для Cost Reward Component"""
    
    def setUp(self):
        """Налаштування перед кожним тестом"""
        # Тестова конфігурація
        self.test_config = {
            "components": {
                "cost": {
                    "enabled": True
                }
            },
            "cost_component": {
                "enabled": True,
                "alpha_bid_ask": 1.0,
                "alpha_transaction": 1.0,
                "alpha_slippage": 2.0,
                "bid_ask": {
                    "cost_threshold": 0.001,
                    "max_tolerance": 0.005
                },
                "transaction": {
                    "base_volume": 1000.0,
                    "max_fee_rate": 0.002
                },
                "slippage": {
                    "slippage_threshold": 0.005,
                    "max_slippage": 0.02,
                    "penalty_multiplier": 1.5
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
        self.cost_component = CostRewardComponent(self.config)
        
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
        
    def create_test_state_data(self, execution_data: ExecutionData = None) -> StateData:
        """Створення тестових даних стану"""
        if execution_data is None:
            execution_data = self.create_test_execution_data()
            
        return StateData(
            timestamp=1640995200.0,
            portfolio=self.create_test_portfolio_data(),
            arce=self.create_test_arce_data(),
            pnl=PnLData(realized_pnl=0.0, unrealized_pnl=0.0, asset_pnl={}),
            market_data={},
            execution=execution_data
        )
        
    def test_no_costs(self):
        """Тест 1.3.T1.1: Сценарій без витрат"""
        # Виконання без витрат
        execution_data = self.create_test_execution_data()
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(execution_data)
        
        result = self.cost_component.calculate(arce_data, portfolio_data, state_data)
        
        self.assertEqual(result.component_name, "cost")
        self.assertAlmostEqual(result.raw_value, 0.0, places=6)
        
        # Перевіряємо всі підкомпоненти
        self.assertAlmostEqual(result.subcomponents["bid_ask_cost"], 0.0)
        self.assertAlmostEqual(result.subcomponents["transaction_cost"], 0.0)
        self.assertAlmostEqual(result.subcomponents["slippage_cost"], 0.0)
        
    def test_bid_ask_costs(self):
        """Тест 1.3.T1.2: Витрати на bid-ask спреди"""
        # Створюємо виконання з спредами
        execution_data = self.create_test_execution_data(
            bid_ask_spreads={
                "BTCUSDT": {"spread": 0.002, "volume": 100.0},  # 0.2% спред
                "ETHUSDT": {"spread": 0.001, "volume": 50.0}    # 0.1% спред
            }
        )
        
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(execution_data)
        
        result = self.cost_component.calculate(arce_data, portfolio_data, state_data)
        
        self.assertEqual(result.component_name, "cost")
        self.assertLess(result.raw_value, 0.0)  # Витрати дають негативну винагороду
        
        # Перевіряємо, що є bid-ask витрати
        self.assertGreater(result.subcomponents["bid_ask_cost"], 0.0)
        self.assertAlmostEqual(result.subcomponents["transaction_cost"], 0.0)
        self.assertAlmostEqual(result.subcomponents["slippage_cost"], 0.0)
        
    def test_transaction_costs(self):
        """Тест 1.3.T1.3: Транзакційні витрати"""
        # Створюємо виконання з комісіями
        execution_data = self.create_test_execution_data(
            transaction_fees={
                "BTCUSDT": {"fee": 0.5, "volume": 100.0},  # $0.5 комісія
                "ETHUSDT": {"fee": 0.2, "volume": 50.0}    # $0.2 комісія
            }
        )
        
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(execution_data)
        
        result = self.cost_component.calculate(arce_data, portfolio_data, state_data)
        
        self.assertEqual(result.component_name, "cost")
        self.assertLess(result.raw_value, 0.0)  # Витрати дають негативну винагороду
        
        # Перевіряємо, що є транзакційні витрати
        self.assertAlmostEqual(result.subcomponents["bid_ask_cost"], 0.0)
        self.assertGreater(result.subcomponents["transaction_cost"], 0.0)
        self.assertAlmostEqual(result.subcomponents["slippage_cost"], 0.0)
        
    def test_slippage_costs(self):
        """Тест 1.3.T1.4: Витрати на проковзування"""
        # Створюємо виконання з проковзуванням
        execution_data = self.create_test_execution_data(
            slippage_costs={
                "BTCUSDT": {
                    "slippage": 0.01,           # 1% проковзування 
                    "volume": 100.0,
                    "expected_price": 50000.0,
                    "actual_price": 49500.0     # Lower than expected (worse fill)
                },
                "ETHUSDT": {
                    "slippage": 0.005,          # 0.5% проковзування
                    "volume": 50.0,
                    "expected_price": 3000.0,
                    "actual_price": 2985.0
                }
            }
        )
        
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(execution_data)
        
        result = self.cost_component.calculate(arce_data, portfolio_data, state_data)
        
        self.assertEqual(result.component_name, "cost")
        self.assertLess(result.raw_value, 0.0)  # Витрати дають негативну винагороду
        
        # Перевіряємо, що є slippage витрати
        self.assertAlmostEqual(result.subcomponents["bid_ask_cost"], 0.0)
        self.assertAlmostEqual(result.subcomponents["transaction_cost"], 0.0)
        self.assertGreater(result.subcomponents["slippage_cost"], 0.0)
        
    def test_multiple_costs(self):
        """Тест 1.3.T1.5: Множинні типи витрат"""
        # Створюємо виконання з всіма типами витрат
        execution_data = self.create_test_execution_data(
            bid_ask_spreads={
                "BTCUSDT": {"spread": 0.002, "volume": 100.0}
            },
            transaction_fees={
                "BTCUSDT": {"fee": 0.5, "volume": 100.0}
            },
            slippage_costs={
                "BTCUSDT": {
                    "slippage": 0.01,
                    "volume": 100.0,
                    "expected_price": 50000.0,
                    "actual_price": 49500.0
                }
            }
        )
        
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(execution_data)
        
        result = self.cost_component.calculate(arce_data, portfolio_data, state_data)
        
        self.assertEqual(result.component_name, "cost")
        self.assertLess(result.raw_value, 0.0)  # Загальні витрати негативні
        
        # Перевіряємо, що всі типи витрат присутні
        self.assertGreater(result.subcomponents["bid_ask_cost"], 0.0)
        self.assertGreater(result.subcomponents["transaction_cost"], 0.0)
        self.assertGreater(result.subcomponents["slippage_cost"], 0.0)
        
        # Перевіряємо формулу: R_Cost = -α_bid * bid - α_trans * trans - α_slip * slip
        expected_total = (
            -self.cost_component.alpha_bid_ask * result.subcomponents["bid_ask_cost"] -
            self.cost_component.alpha_transaction * result.subcomponents["transaction_cost"] -
            self.cost_component.alpha_slippage * result.subcomponents["slippage_cost"]
        )
        self.assertAlmostEqual(result.raw_value, expected_total, places=6)
        
    def test_cost_weighted_correctly(self):
        """Тест 1.3.T1.6: Перевірка правильності ваг"""
        # Тест з відомими значеннями для перевірки формули
        execution_data = self.create_test_execution_data(
            bid_ask_spreads={"BTCUSDT": 0.001},     # 1x threshold
            transaction_fees={"BTCUSDT": 1.0},      # Known fee
            slippage_costs={"BTCUSDT": 0.005}       # 1x threshold
        )
        
        arce_data = self.create_test_arce_data()
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data(execution_data)
        
        result = self.cost_component.calculate(arce_data, portfolio_data, state_data)
        
        # Slippage повинен мати найбільшу вагу (alpha=2.0)
        slippage_weighted = result.subcomponents["slippage_weighted"]
        bid_ask_weighted = result.subcomponents["bid_ask_weighted"]
        transaction_weighted = result.subcomponents["transaction_weighted"]
        
        # Slippage штраф повинен бути більшим за absolute value
        self.assertLess(slippage_weighted, bid_ask_weighted)  # More negative
        
    def test_component_disabled(self):
        """Тест 1.3.T1.7: Компонента вимкнена"""
        # Змінюємо конфігурацію для вимкнення компоненти
        disabled_config = self.test_config.copy()
        disabled_config["cost_component"]["enabled"] = False
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        yaml.dump(disabled_config, temp_file)
        temp_file.close()
        
        try:
            config = RewardEngineConfig(temp_file.name)
            cost_component = CostRewardComponent(config)
            
            arce_data = self.create_test_arce_data()
            portfolio_data = self.create_test_portfolio_data()
            state_data = self.create_test_state_data()
            
            result = cost_component.calculate(arce_data, portfolio_data, state_data)
            
            self.assertEqual(result.component_name, "cost")
            self.assertEqual(result.raw_value, 0.0)
            self.assertIn("disabled", result.subcomponents)
            
        finally:
            os.unlink(temp_file.name)
            
    def test_component_info(self):
        """Тест 1.3.T1.8: Інформація про компоненту"""
        info = self.cost_component.get_component_info()
        
        self.assertEqual(info["component_name"], "cost")
        self.assertTrue(info["enabled"])
        self.assertIn("alpha_coefficients", info)
        self.assertIn("subcomponents", info)
        
        # Перевіряємо альфа коефіцієнти
        alphas = info["alpha_coefficients"]
        self.assertEqual(alphas["bid_ask"], 1.0)
        self.assertEqual(alphas["transaction"], 1.0)
        self.assertEqual(alphas["slippage"], 2.0)


if __name__ == '__main__':
    unittest.main()
