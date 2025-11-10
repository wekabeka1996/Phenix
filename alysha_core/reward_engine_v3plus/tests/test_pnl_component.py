"""
Тести для PnL Reward Component

Завдання 1.1.T1: Тестування базових розрахунків PnL компоненти
згідно з роадмапом ALYSHA-RE-V3+
"""

import unittest
import numpy as np
from unittest.mock import Mock, patch
import tempfile
import yaml
import os

from alysha_core.reward_engine_v3plus.components.pnl import PnLRewardComponent
from alysha_core.reward_engine_v3plus.data_types import (
    PnLData, StateData, PortfolioData, ARCEData, MarketRegime
)
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig


class TestPnLRewardComponent(unittest.TestCase):
    """Тестування PnL компоненти винагороди"""
    
    def setUp(self):
        """Налаштування тестового середовища"""
        # Створюємо тимчасовий конфігураційний файл
        self.test_config = {
            "pnl_component": {
                "enabled": True,
                "realized_pnl": {
                    "weight": 1.0,
                    "scaling_factor": 1.0
                },
                "unrealized_pnl": {
                    "weight": 0.8,
                    "scaling_factor": 0.8
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
        self.pnl_component = PnLRewardComponent(self.config)
        
    def tearDown(self):
        """Очищення після тестів"""
        os.unlink(self.temp_config_file.name)
        
    def create_test_state_data(self, realized_pnl: float = 100.0, 
                              unrealized_pnl: float = 50.0) -> StateData:
        """Створення тестових даних стану"""
        pnl_data = PnLData(
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            asset_pnl={"BTCUSDT": realized_pnl + unrealized_pnl}
        )
        
        portfolio_data = PortfolioData(
            positions={"BTCUSDT": 1.0},
            current_weights={"BTCUSDT": 1.0},
            target_weights={"BTCUSDT": 1.0},
            total_value=10000.0,
            turnover=0.1
        )
        
        arce_data = ARCEData(
            var_current=0.05,
            var_limit=0.1,
            cvar_current=0.08,
            cvar_limit=0.15,
            drawdown_current=0.02,
            drawdown_limit=0.1,
            portfolio_volatility=0.15,
            target_volatility=0.12,
            volatility_range=0.05,
            active_flags=[],
            regime_tag=MarketRegime.STABLE,  # Mapped from NORMAL
            position_limits={"BTCUSDT": 10.0}
        )
        
        return StateData(
            timestamp=1640995200.0,  # 2022-01-01
            portfolio=portfolio_data,
            arce=arce_data,
            pnl=pnl_data,
            market_data={}
        )
        
    def test_basic_pnl_calculation(self):
        """Тест 1.1.T1.1: Базовий розрахунок PnL"""
        # Scenario: позитивний реалізований та нереалізований PnL
        state_data = self.create_test_state_data(
            realized_pnl=100.0,
            unrealized_pnl=50.0
        )
        
        result = self.pnl_component.calculate(state_data)
        
        # Перевірка формули: R_PnL,t = 1.0 * (1.0 * 100.0) + 0.8 * (0.8 * 50.0)
        expected_realized = 1.0 * 1.0 * 100.0  # weight * scaling * value
        expected_unrealized = 0.8 * 0.8 * 50.0  # weight * scaling * value
        expected_total = expected_realized + expected_unrealized
        
        self.assertEqual(result.component_name, "pnl")
        self.assertAlmostEqual(result.raw_value, expected_total, places=6)
        self.assertAlmostEqual(result.raw_value, 132.0, places=6)  # 100 + 32
        
        # Перевірка субкомпонент
        self.assertIn("realized_component", result.subcomponents)
        self.assertIn("unrealized_component", result.subcomponents)
        self.assertAlmostEqual(
            result.subcomponents["realized_component"], 100.0, places=6
        )
        self.assertAlmostEqual(
            result.subcomponents["unrealized_component"], 40.0, places=6
        )
        
    def test_negative_pnl_calculation(self):
        """Тест 1.1.T1.2: Розрахунок з негативним PnL"""
        state_data = self.create_test_state_data(
            realized_pnl=-75.0,
            unrealized_pnl=-25.0
        )
        
        result = self.pnl_component.calculate(state_data)
        
        # Очікуваний результат: 1.0 * (1.0 * -75.0) + 0.8 * (0.8 * -25.0) = -75 - 16 = -91
        expected_total = -75.0 + 0.8 * 0.8 * (-25.0)
        
        self.assertAlmostEqual(result.raw_value, expected_total, places=6)
        self.assertAlmostEqual(result.raw_value, -91.0, places=6)
        
    def test_zero_pnl_calculation(self):
        """Тест 1.1.T1.3: Розрахунок з нульовим PnL"""
        state_data = self.create_test_state_data(
            realized_pnl=0.0,
            unrealized_pnl=0.0
        )
        
        result = self.pnl_component.calculate(state_data)
        
        self.assertAlmostEqual(result.raw_value, 0.0, places=6)
        
    def test_mixed_pnl_calculation(self):
        """Тест 1.1.T1.4: Змішаний PnL (позитивний/негативний)"""
        state_data = self.create_test_state_data(
            realized_pnl=200.0,    # позитивний
            unrealized_pnl=-100.0  # негативний
        )
        
        result = self.pnl_component.calculate(state_data)
        
        # Очікуваний результат: 1.0 * 200.0 + 0.8 * 0.8 * (-100.0) = 200 - 64 = 136
        expected_total = 200.0 + 0.8 * 0.8 * (-100.0)
        
        self.assertAlmostEqual(result.raw_value, expected_total, places=6)
        self.assertAlmostEqual(result.raw_value, 136.0, places=6)
        
    def test_component_disabled(self):
        """Тест 1.1.T1.5: Компонента вимкнена"""
        # Створюємо конфігурацію з вимкненою компонентою
        disabled_config = self.test_config.copy()
        disabled_config["pnl_component"]["enabled"] = False
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(disabled_config, f)
            disabled_config_path = f.name
            
        try:
            config = RewardEngineConfig(disabled_config_path)
            component = PnLRewardComponent(config)
            
            state_data = self.create_test_state_data(100.0, 50.0)
            result = component.calculate(state_data)
            
            self.assertEqual(result.raw_value, 0.0)
            self.assertIn("disabled", result.subcomponents)
            
        finally:
            os.unlink(disabled_config_path)
            
    def test_invalid_data_handling(self):
        """Тест 1.1.T1.6: Обробка некоректних даних"""
        # Тест з NaN значеннями
        state_data = self.create_test_state_data(
            realized_pnl=float('nan'),
            unrealized_pnl=50.0
        )
        
        result = self.pnl_component.calculate(state_data)
        
        # Має повернути безпечне значення
        safe_value = self.config.get("validation.default_safe_reward", -10.0)
        self.assertEqual(result.raw_value, safe_value)
        self.assertIn("error", result.subcomponents)
        
    def test_missing_pnl_data(self):
        """Тест 1.1.T1.7: Відсутні PnL дані"""
        state_data = self.create_test_state_data()
        state_data.pnl = None  # Видаляємо PnL дані
        
        result = self.pnl_component.calculate(state_data)
        
        # Має повернути безпечне значення
        safe_value = self.config.get("validation.default_safe_reward", -10.0)
        self.assertEqual(result.raw_value, safe_value)
        
    def test_pnl_data_validation(self):
        """Тест 1.1.T1.8: Валідація PnL даних"""
        # Валідні дані
        valid_pnl = PnLData(
            realized_pnl=100.0,
            unrealized_pnl=50.0,
            asset_pnl={}
        )
        self.assertTrue(self.pnl_component.validate_pnl_data(valid_pnl))
        
        # Невалідні дані (NaN)
        invalid_pnl = PnLData(
            realized_pnl=float('nan'),
            unrealized_pnl=50.0,
            asset_pnl={}
        )
        self.assertFalse(self.pnl_component.validate_pnl_data(invalid_pnl))
        
        # Невалідні дані (Inf)
        invalid_pnl_inf = PnLData(
            realized_pnl=float('inf'),
            unrealized_pnl=50.0,
            asset_pnl={}
        )
        self.assertFalse(self.pnl_component.validate_pnl_data(invalid_pnl_inf))
        
    def test_component_info(self):
        """Тест 1.1.T1.9: Інформація про компоненту"""
        info = self.pnl_component.get_component_info()
        
        self.assertEqual(info["component_name"], "pnl")
        self.assertTrue(info["enabled"])
        self.assertEqual(info["c_real"], 1.0)
        self.assertEqual(info["c_unreal"], 0.8)
        self.assertIn("formula", info)
        
    def test_extreme_values(self):
        """Тест 1.1.T1.10: Екстремальні значення"""
        # Дуже великі значення
        state_data = self.create_test_state_data(
            realized_pnl=1e6,
            unrealized_pnl=1e6
        )
        
        result = self.pnl_component.calculate(state_data)
        
        # Перевіряємо, що розрахунок відбувся без помилок
        self.assertIsInstance(result.raw_value, float)
        self.assertFalse(np.isnan(result.raw_value))
        self.assertFalse(np.isinf(result.raw_value))
        
        # Очікуваний результат: 1e6 + 0.8 * 0.8 * 1e6 = 1e6 + 0.64e6 = 1.64e6
        expected = 1e6 + 0.8 * 0.8 * 1e6
        self.assertAlmostEqual(result.raw_value, expected, places=2)


if __name__ == '__main__':
    unittest.main()
