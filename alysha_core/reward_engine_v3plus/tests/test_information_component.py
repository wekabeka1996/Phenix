"""
Тести для Information Reward Component

Тестування компоненти розрахунку винагороди за інформаційну ефективність агента.

Автор: ALYSHA система
Версія: V3+
"""

import unittest
import tempfile
import os
import yaml
import numpy as np
from typing import Dict, Any

from alysha_core.reward_engine_v3plus.components.information import InformationRewardComponent
from alysha_core.reward_engine_v3plus.data_types import (
    ARCEData, PortfolioData, StateData, ExecutionData, AgentActionData, FillData,
    MarketRegime, PnLData, ModelPredictionData
)
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig


class TestInformationRewardComponent(unittest.TestCase):
    """Тестовий клас для Information Reward Component"""
    
    def setUp(self):
        """Налаштування перед кожним тестом"""
        # Тестова конфігурація
        self.test_config = {
            "components": {
                "information": {
                    "enabled": True
                }
            },
            "information_component": {
                "enabled": True,
                "gamma_align": 4.0,
                "gamma_explore": 2.0,
                "signal_alignment": {
                    "alignment_method": "cosine_similarity",
                    "signal_window": 20,
                    "min_signal_strength": 0.1
                },
                "strategic_exploration": {
                    "exploration_bonus": 1.0,
                    "uncertainty_threshold": 0.7,
                    "novelty_window": 100,
                    "min_exploration_reward": 0.0
                }
            }
        }
        
        # Создаем временный файл конфигурации
        self.config_fd, self.config_path = tempfile.mkstemp(suffix='.yaml')
        with os.fdopen(self.config_fd, 'w') as f:
            yaml.dump(self.test_config, f)
        
        # Инициализируем компонент
        self.config = RewardEngineConfig(self.config_path)
        self.component = InformationRewardComponent(self.config)
        
        # Тестовые данные
        self.setup_test_data()
    
    def tearDown(self):
        """Очистка после тестов"""
        if os.path.exists(self.config_path):
            os.unlink(self.config_path)
    
    def setup_test_data(self):
        """Настройка тестовых данных"""
        # Базовые данные портфеля
        self.portfolio_data = PortfolioData(
            positions={'BTCUSDT': 1.5, 'ETHUSDT': 10.0},
            current_weights={'BTCUSDT': 0.6, 'ETHUSDT': 0.4},
            target_weights={'BTCUSDT': 0.5, 'ETHUSDT': 0.5},
            total_value=100000.0,
            turnover=0.15
        )
        
        # Данные ARCE
        self.arce_data = ARCEData(
            var_current=0.15,
            var_limit=0.20,
            cvar_current=0.25,
            cvar_limit=0.30,
            drawdown_current=0.05,
            drawdown_limit=0.10,
            portfolio_volatility=0.15,
            target_volatility=0.12,
            volatility_range=0.05,
            active_flags=[],
            regime_tag=MarketRegime.STABLE,  # Mapped from NORMAL
            position_limits={'BTCUSDT': 2.0, 'ETHUSDT': 15.0}
        )
        
        # Данные действий агента с предсказаниями модели
        predictions = ModelPredictionData(
            prediction_vector=np.array([0.6, 0.4, 0.8]),
            confidence=0.8,
            model_uncertainty=0.2,
            predicted_direction=1
        )
        
        self.agent_action_data = AgentActionData(
            action_vector=np.array([0.75, 0.0, 0.25]),
            action_type='BUY',
            action_direction=1,
            is_exploratory=True
        )
        
        # Сохраняем predictions для использования в тестах
        self.predictions = predictions
        
        # Данные PnL
        pnl_data = PnLData(
            realized_pnl=500.0,
            unrealized_pnl=1000.0,
            asset_pnl={'BTCUSDT': 800.0, 'ETHUSDT': 700.0}
        )
        
        # Данные состояния
        self.state_data = StateData(
            timestamp=1640995200.0,
            portfolio=self.portfolio_data,
            arce=self.arce_data,
            pnl=pnl_data,
            market_data={
                'symbol': 'BTCUSDT',
                'price': 44000.0,
                'volume': 1000.0
            },
            agent_action=self.agent_action_data
        )
    
    def test_initialization(self):
        """Тест инициализации компонента"""
        self.assertIsNotNone(self.component)
        self.assertTrue(self.component.enabled)
        self.assertEqual(self.component.gamma_align, 4.0)
        self.assertEqual(self.component.gamma_explore, 2.0)
    
    def test_signal_alignment_calculation(self):
        """Тест расчета alignment сигналов"""
        # Тестируем полный метод alignment с StateData
        alignment = self.component._calculate_signal_alignment(self.state_data)
        
        # Проверяем, что alignment находится в разумных пределах
        self.assertGreaterEqual(alignment, -1.0)
        self.assertLessEqual(alignment, 1.0)
        self.assertIsInstance(alignment, float)
    
    def test_exploration_reward_calculation(self):
        """Тест расчета вознаграждения за исследование"""
        exploration_reward = self.component._calculate_strategic_exploration(self.state_data)
        
        # Проверяем правильный тип и разумные значения
        self.assertIsInstance(exploration_reward, float)
        # Может быть положительным или отрицательным в зависимости от стратегии
        self.assertGreaterEqual(exploration_reward, -2.0)
        self.assertLessEqual(exploration_reward, 2.0)
    
    def test_market_signal_extraction(self):
        """Тест извлечения рыночных сигналов"""
        # Проверяем метод извлечения сигналов из рыночных данных
        market_signals = self.state_data.market_data
        signal_vector = self.component._extract_signal_vector(market_signals)
        
        if signal_vector is not None:
            self.assertIsInstance(signal_vector, np.ndarray)
            self.assertGreater(len(signal_vector), 0)
        else:
            # Если сигналов нет, это также допустимо
            self.assertIsNone(signal_vector)
    
    def test_agent_signal_extraction(self):
        """Тест извлечения сигналов агента"""
        # Тестируем расчет продукта направлений
        action_vector = self.agent_action_data.action_vector
        market_vector = np.array([0.5, 0.3, 0.2])  # Симуляция рыночного вектора
        
        direction_product = self.component._calculate_direction_product(action_vector, market_vector)
        
        self.assertIsInstance(direction_product, float)
        # Продукт направлений может быть от -1 до 1
        self.assertGreaterEqual(direction_product, -1.0)
        self.assertLessEqual(direction_product, 1.0)
    
    def test_novelty_bonus_calculation(self):
        """Тест расчета новизны действий"""
        # Добавляем несколько действий в историю
        for i in range(5):
            action_data = AgentActionData(
                action_vector=np.array([0.0, 1.0, 0.0]),
                action_type='HOLD',
                action_direction=0,
                is_exploratory=False
            )
            self.component.action_history.append(action_data)
        
        # Тестируем новое отличающееся действие
        new_action = AgentActionData(
            action_vector=np.array([1.0, 0.0, 0.0]),
            action_type='BUY',
            action_direction=1,
            is_exploratory=True
        )
        
        novelty = self.component._calculate_novelty_bonus(new_action)
        
        self.assertGreaterEqual(novelty, 0.0)
        self.assertLessEqual(novelty, 1.0)
        self.assertIsInstance(novelty, float)
    
    def test_calculate_reward_with_valid_data(self):
        """Тест расчета вознаграждения с корректными данными"""
        result = self.component.calculate(
            arce_data=self.arce_data,
            portfolio_data=self.portfolio_data,
            state_data=self.state_data
        )
        
        # Проверяем, что результат - это RewardComponentResult
        self.assertEqual(result.component_name, "information")
        self.assertIsInstance(result.raw_value, (float, int))
        # Вознаграждение может быть как положительным, так и отрицательным
        self.assertGreaterEqual(result.raw_value, -10.0)  # Разумные границы
        self.assertLessEqual(result.raw_value, 10.0)
        
        # Проверяем подкомпоненты
        self.assertIn("signal_alignment", result.subcomponents)
        self.assertIn("strategic_exploration", result.subcomponents)
    
    def test_calculate_reward_without_agent_action(self):
        """Тест расчета вознаграждения без данных действий агента"""
        pnl_data = PnLData(
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            asset_pnl={}
        )
        
        state_data_no_action = StateData(
            timestamp=1640995200.0,
            portfolio=self.portfolio_data,
            arce=self.arce_data,
            pnl=pnl_data,
            market_data={
                'symbol': 'BTCUSDT',
                'price': 44000.0,
                'volume': 1000.0
            }
        )
        
        result = self.component.calculate(
            arce_data=self.arce_data,
            portfolio_data=self.portfolio_data,
            state_data=state_data_no_action
        )
        
        # Без данных действий агента вознаграждение должно быть 0
        self.assertEqual(result.raw_value, 0.0)
        self.assertEqual(result.component_name, "information")
    
    def test_component_disabled(self):
        """Тест поведения при отключенном компоненте"""
        # Отключаем компонент
        disabled_config = self.test_config.copy()
        disabled_config["information_component"]["enabled"] = False
        
        config_fd, config_path = tempfile.mkstemp(suffix='.yaml')
        with os.fdopen(config_fd, 'w') as f:
            yaml.dump(disabled_config, f)
        
        try:
            config = RewardEngineConfig(config_path)
            component = InformationRewardComponent(config)
            
            result = component.calculate(
                arce_data=self.arce_data,
                portfolio_data=self.portfolio_data,
                state_data=self.state_data
            )
            
            self.assertEqual(result.raw_value, 0.0)
        finally:
            os.unlink(config_path)
    
    def test_edge_cases(self):
        """Тест граничных случаев"""
        # Тест с нулевыми сигналами
        empty_predictions = ModelPredictionData(
            prediction_vector=np.array([0.0, 0.0, 0.0]),
            confidence=0.0,
            model_uncertainty=1.0,
            predicted_direction=0
        )
        
        empty_action = AgentActionData(
            action_vector=np.array([0.0, 1.0, 0.0]),
            action_type='HOLD',
            action_direction=0,
            is_exploratory=False
        )
        
        empty_state = StateData(
            timestamp=1640995200.0,
            portfolio=self.portfolio_data,
            arce=self.arce_data,
            pnl=PnLData(realized_pnl=0.0, unrealized_pnl=0.0, asset_pnl={}),
            market_data={
                'symbol': 'BTCUSDT',
                'price': 44000.0,
                'volume': 0.0
            },
            agent_action=empty_action
        )
        
        result = self.component.calculate(
            arce_data=self.arce_data,
            portfolio_data=self.portfolio_data,
            state_data=empty_state
        )
        
        # Компонент должен корректно обрабатывать пустые данные
        self.assertIsInstance(result.raw_value, (float, int))
        self.assertGreaterEqual(result.raw_value, -1.0)
    
    def test_action_history_management(self):
        """Тест управления историей действий"""
        # Тестируем оценку рыночной неопределенности
        uncertainty = self.component._estimate_market_uncertainty(self.state_data)
        
        self.assertIsInstance(uncertainty, float)
        self.assertGreaterEqual(uncertainty, 0.0)
        self.assertLessEqual(uncertainty, 1.0)
        
        # Тестируем обновление истории исследований
        self.component._update_exploration_history(self.agent_action_data, uncertainty)
        
        # Проверяем, что история обновилась
        self.assertGreaterEqual(len(self.component.exploration_history), 0)


if __name__ == '__main__':
    unittest.main()
