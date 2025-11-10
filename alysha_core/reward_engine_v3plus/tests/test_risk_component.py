"""
Тести для Risk Reward Component

Завдання 1.2.T1-1.2.6.T1: Тестування всіх підкомпонент ризику
згідно з роадмапом ALYSHA-RE-V3+
"""

import unittest
import numpy as np
import tempfile
import yaml
import os

from alysha_core.reward_engine_v3plus.components.risk import RiskRewardComponent
from alysha_core.reward_engine_v3plus.data_types import (
    ARCEData, PortfolioData, StateData, PnLData, MarketRegime
)
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig


class TestRiskRewardComponent(unittest.TestCase):
    """Тестування Risk компоненти винагороди"""
    
    def setUp(self):
        """Налаштування тестового середовища"""
        # Створюємо тестову конфігурацію
        self.test_config = {
            "risk_component": {
                "enabled": True,
                "subcomponent_weights": {
                    "drawdown": 0.3,
                    "var": 0.2,
                    "cvar": 0.2,
                    "volatility": 0.15,
                    "arce_flags": 0.1,
                    "inventory": 0.05
                },
                "drawdown": {
                    "c_dd": 10.0,
                    "threshold_tolerance": 0.01
                },
                "var": {
                    "c_var": 5.0,
                    "threshold_tolerance": 0.005
                },
                "cvar": {
                    "c_cvar": 15.0,
                    "threshold_tolerance": 0.005
                },
                "volatility": {
                    "c_vol": 8.0,
                    "threshold_tolerance": 0.02
                },
                "arce_flags": {
                    "base_penalty_multiplier": 1.0
                },
                "inventory": {
                    "c_inv": 12.0
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
        self.risk_component = RiskRewardComponent(self.config)
        
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
            "portfolio_volatility": 0.15,
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
        
    def create_test_state_data(self) -> StateData:
        """Створення тестових даних стану"""
        return StateData(
            timestamp=1640995200.0,
            portfolio=self.create_test_portfolio_data(),
            arce=self.create_test_arce_data(),
            pnl=PnLData(realized_pnl=0.0, unrealized_pnl=0.0, asset_pnl={}),
            market_data={}
        )
        
    def test_no_risk_violations(self):
        """Тест 1.2.T1.1: Сценарій без порушень ризику"""
        # Всі метрики в межах лімітів - модифікуємо дані для повного відсутності ризиків
        arce_data = self.create_test_arce_data(
            portfolio_volatility=0.12,  # Точно на цільовому рівні
            var_current=0.05,  # Нижче ліміту
            cvar_current=0.08,  # Нижче ліміту 
            drawdown_current=0.01  # Нижче ліміту
        )
        # Позиції в межах лімітів
        portfolio_data = self.create_test_portfolio_data(
            positions={"BTCUSDT": 5.0, "ETHUSDT": 2.0}  # В межах лімітів 10.0 та 5.0
        )
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # Очікуємо 0 або близько до 0, оскільки немає перевищень
        self.assertEqual(result.component_name, "risk")
        self.assertAlmostEqual(result.raw_value, 0.0, places=6)
        
        # Перевіряємо, що всі підкомпоненти теж 0
        self.assertAlmostEqual(result.subcomponents["drawdown_raw"], 0.0)
        self.assertAlmostEqual(result.subcomponents["var_raw"], 0.0)
        self.assertAlmostEqual(result.subcomponents["cvar_raw"], 0.0)
        self.assertAlmostEqual(result.subcomponents["volatility_raw"], 0.0)
        self.assertAlmostEqual(result.subcomponents["inventory_raw"], 0.0)
        
    def test_drawdown_violation(self):
        """Тест 1.2.1.T1: Порушення DrawDown ліміту"""
        # DrawDown перевищує ліміт
        arce_data = self.create_test_arce_data(
            drawdown_current=0.15,  # Перевищує ліміт 0.1
            drawdown_limit=0.1
        )
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # Перевіряємо розрахунок: excess = 0.15 - 0.1 - 0.01 = 0.04
        # penalty = -10.0 * (0.04)² = -0.016
        # weighted = 0.3 * (-0.016) = -0.0048
        expected_drawdown_penalty = -10.0 * (0.04 ** 2)  # -0.016
        expected_weighted_penalty = 0.3 * expected_drawdown_penalty  # -0.0048
        
        self.assertAlmostEqual(result.subcomponents["drawdown_raw"], expected_drawdown_penalty, places=6)
        self.assertAlmostEqual(result.subcomponents["drawdown_weighted"], expected_weighted_penalty, places=6)
        self.assertLess(result.raw_value, 0)  # Має бути негативна винагорода
        
    def test_var_violation(self):
        """Тест 1.2.2.T1: Порушення VaR ліміту"""
        arce_data = self.create_test_arce_data(
            var_current=0.12,  # Перевищує ліміт 0.1
            var_limit=0.1
        )
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # excess = 0.12 - 0.1 - 0.005 = 0.015
        # penalty = -5.0 * (0.015)² = -0.001125  
        # weighted = 0.2 * (-0.001125) = -0.000225
        expected_var_penalty = -5.0 * (0.015 ** 2)
        expected_weighted_penalty = 0.2 * expected_var_penalty
        
        self.assertAlmostEqual(result.subcomponents["var_raw"], expected_var_penalty, places=6)
        self.assertAlmostEqual(result.subcomponents["var_weighted"], expected_weighted_penalty, places=6)
        
    def test_cvar_violation(self):
        """Тест 1.2.3.T1: Порушення CVaR ліміту"""
        arce_data = self.create_test_arce_data(
            cvar_current=0.18,  # Перевищує ліміт 0.15
            cvar_limit=0.15
        )
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # excess = 0.18 - 0.15 - 0.005 = 0.025
        # penalty = -15.0 * (0.025)² = -0.009375
        # weighted = 0.2 * (-0.009375) = -0.001875
        expected_cvar_penalty = -15.0 * (0.025 ** 2)
        expected_weighted_penalty = 0.2 * expected_cvar_penalty
        
        self.assertAlmostEqual(result.subcomponents["cvar_raw"], expected_cvar_penalty, places=6)
        self.assertAlmostEqual(result.subcomponents["cvar_weighted"], expected_weighted_penalty, places=6)
        
    def test_volatility_violation(self):
        """Тест 1.2.4.T1: Порушення волатильності"""
        arce_data = self.create_test_arce_data(
            portfolio_volatility=0.20,  # Відхилення від target 0.12
            target_volatility=0.12,
            volatility_range=0.05
        )
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # deviation = |0.20 - 0.12| = 0.08 > tolerance 0.02
        # normalized_deviation = (0.20 - 0.12) / 0.05 = 1.6
        # penalty = -8.0 * (1.6)² = -20.48
        # weighted = 0.15 * (-20.48) = -3.072
        deviation = abs(0.20 - 0.12)
        self.assertGreater(deviation, 0.02)  # Перевіряємо, що є порушення
        
        normalized_deviation = (0.20 - 0.12) / 0.05
        expected_penalty = -8.0 * (normalized_deviation ** 2)
        expected_weighted = 0.15 * expected_penalty
        
        self.assertAlmostEqual(result.subcomponents["volatility_raw"], expected_penalty, places=6)
        self.assertAlmostEqual(result.subcomponents["volatility_weighted"], expected_weighted, places=6)
        
    def test_arce_flags_penalty(self):
        """Тест 1.2.5.T1: Штраф за ARCE прапори"""
        active_flags = [
            {
                "name": "HighRiskFlag",
                "severity": 2.0,
                "penalty_multiplier": 1.5,
                "base_penalty": 10.0
            },
            {
                "name": "VolatilityFlag", 
                "severity": 1.0,
                "penalty_multiplier": 1.0,
                "base_penalty": 5.0
            }
        ]
        
        arce_data = self.create_test_arce_data(active_flags=active_flags)
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # Flag 1: 2.0 * 10.0 * 1.5 = 30.0
        # Flag 2: 1.0 * 5.0 * 1.0 = 5.0  
        # Total: -(30.0 + 5.0) = -35.0
        # Weighted: 0.1 * (-35.0) = -3.5
        expected_penalty = -(2.0 * 10.0 * 1.5 + 1.0 * 5.0 * 1.0)  # -35.0
        expected_weighted = 0.1 * expected_penalty  # -3.5
        
        self.assertAlmostEqual(result.subcomponents["arce_flags_raw"], expected_penalty, places=6)
        self.assertAlmostEqual(result.subcomponents["arce_flags_weighted"], expected_weighted, places=6)
        
    def test_inventory_risk_violation(self):
        """Тест 1.2.6.T1: Порушення лімітів позицій"""
        # Позиції перевищують ліміти
        portfolio_data = self.create_test_portfolio_data(
            positions={"BTCUSDT": 15.0, "ETHUSDT": 8.0}  # Перевищують ліміти 10.0 та 5.0
        )
        arce_data = self.create_test_arce_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # BTCUSDT: excess = max(0, 15.0 - 10.0) = 5.0, penalty = 5.0² = 25.0
        # ETHUSDT: excess = max(0, 8.0 - 5.0) = 3.0, penalty = 3.0² = 9.0
        # Total penalty = -(12.0 * (25.0 + 9.0)) = -408.0
        # Weighted = 0.05 * (-408.0) = -20.4
        btc_excess = max(0, 15.0 - 10.0)  # 5.0
        eth_excess = max(0, 8.0 - 5.0)   # 3.0
        total_penalty_raw = btc_excess**2 + eth_excess**2  # 25.0 + 9.0 = 34.0
        expected_penalty = -12.0 * total_penalty_raw  # -408.0
        expected_weighted = 0.05 * expected_penalty  # -20.4
        
        self.assertAlmostEqual(result.subcomponents["inventory_raw"], expected_penalty, places=6)
        self.assertAlmostEqual(result.subcomponents["inventory_weighted"], expected_weighted, places=6)
        
    def test_multiple_risk_violations(self):
        """Тест 1.2.T2: Множинні порушення ризику"""
        # Комбінація порушень
        arce_data = self.create_test_arce_data(
            drawdown_current=0.12,  # Порушення
            var_current=0.11,       # Порушення
            cvar_current=0.16       # Порушення
        )
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # Загальна винагорода має бути сумою всіх зважених штрафів
        total_weighted = (
            result.subcomponents["drawdown_weighted"] +
            result.subcomponents["var_weighted"] + 
            result.subcomponents["cvar_weighted"] +
            result.subcomponents["volatility_weighted"] +
            result.subcomponents["arce_flags_weighted"] +
            result.subcomponents["inventory_weighted"]
        )
        
        self.assertAlmostEqual(result.raw_value, total_weighted, places=6)
        self.assertLess(result.raw_value, 0)  # Має бути негативна через порушення
        
    def test_component_disabled(self):
        """Тест 1.2.T3: Компонента вимкнена"""
        disabled_config = self.test_config.copy()
        disabled_config["risk_component"]["enabled"] = False
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(disabled_config, f)
            disabled_config_path = f.name
            
        try:
            config = RewardEngineConfig(disabled_config_path)
            component = RiskRewardComponent(config)
            
            arce_data = self.create_test_arce_data()
            portfolio_data = self.create_test_portfolio_data()
            state_data = self.create_test_state_data()
            
            result = component.calculate(arce_data, portfolio_data, state_data)
            
            self.assertEqual(result.raw_value, 0.0)
            self.assertIn("disabled", result.subcomponents)
            
        finally:
            os.unlink(disabled_config_path)
            
    def test_tolerance_thresholds(self):
        """Тест 1.2.T4: Перевірка порогів толерантності"""
        # DrawDown в межах толерантності
        arce_data = self.create_test_arce_data(
            drawdown_current=0.105,  # 0.1 + 0.005 (менше ніж tolerance 0.01)
            drawdown_limit=0.1
        )
        portfolio_data = self.create_test_portfolio_data()
        state_data = self.create_test_state_data()
        
        result = self.risk_component.calculate(arce_data, portfolio_data, state_data)
        
        # Має бути 0, оскільки в межах толерантності
        self.assertAlmostEqual(result.subcomponents["drawdown_raw"], 0.0, places=6)
        
    def test_component_info(self):
        """Тест 1.2.T5: Інформація про компоненту"""
        info = self.risk_component.get_component_info()
        
        self.assertEqual(info["component_name"], "risk")
        self.assertTrue(info["enabled"])
        self.assertIn("subcomponent_weights", info)
        self.assertIn("subcomponents", info)
        self.assertEqual(len(info["subcomponents"]), 6)  # 6 підкомпонент
        

if __name__ == '__main__':
    unittest.main()
