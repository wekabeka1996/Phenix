"""
Интеграционный тест для Phase 2 компонентов (Event и Shaping)

Этот тест проверяет базовую функциональность новых компонентов
с минимальными тестовыми данными.
"""

import pytest
import numpy as np
from pathlib import Path

from alysha_core.reward_engine_v3plus.components.event import EventRewardComponent
from alysha_core.reward_engine_v3plus.components.shaping import ShapingRewardComponent
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig
from alysha_core.reward_engine_v3plus.data_types import *


class TestPhase2Integration:
    """Интеграционные тесты для Phase 2 компонентов"""
    
    @pytest.fixture
    def config(self):
        """Создание конфигурации из файла"""
        return RewardEngineConfig()
    
    @pytest.fixture
    def sample_state(self):
        """Создание простых тестовых данных"""
        
        # Создаем MarketData
        market_data = MarketData(
            current_price=50000.0,
            previous_price=49500.0,
            high_price=51000.0,
            low_price=49000.0,
            open_price=49500.0,
            current_volume=1000.0,
            average_volume=800.0,
            volume_history=[800.0, 900.0, 1100.0],
            current_volatility=0.15,
            volatility_history=[0.12, 0.14, 0.16],
            bid_ask_spread=50.0,
            market_depth={'bid': 100.0, 'ask': 100.0},
            price_change=500.0,
            price_change_percent=1.01,
            price_history=[49000.0, 49500.0, 50000.0],
            timestamp=1640995200.0
        )
        
        # Создаем PortfolioData
        portfolio = PortfolioData(
            positions={'BTC': 1.0},
            current_weights={'BTC': 1.0},
            target_weights={'BTC': 1.0},
            total_value=10000.0,
            turnover=0.1
        )
        
        # Создаем ARCEData
        arce = ARCEData(
            var_current=150.0,
            var_limit=200.0,
            cvar_current=250.0,
            cvar_limit=300.0,
            drawdown_current=0.05,
            drawdown_limit=0.1,
            portfolio_volatility=0.15,
            target_volatility=0.12,
            volatility_range=0.05,
            active_flags=[],
            regime_tag=MarketRegime.STABLE,  # Mapped from NORMAL
            position_limits={'BTC': 5000.0}
        )
        
        # Создаем PnLData
        pnl = PnLData(
            realized_pnl=100.0,
            unrealized_pnl=50.0,
            asset_pnl={'BTC': 150.0}
        )
        
        # Создаем AgentActionData
        agent_action = AgentActionData(
            action_vector=np.array([0.5, 0.3, 0.2]),
            action_type='BUY',
            action_direction=1,
            is_exploratory=False
        )
        
        # Создаем StateData
        return StateData(
            timestamp=1640995200.0,
            portfolio=portfolio,
            arce=arce,
            pnl=pnl,
            market_data={'BTCUSDT': market_data},
            execution=None,  # Оставляем пустым для простоты
            agent_action=agent_action
        )
    
    def test_event_component_basic_functionality(self, config, sample_state):
        """Тест базовой функциональности Event компонента"""
        
        # Создаем компонент
        event_component = EventRewardComponent(config)
        
        # Проверяем, что компонент создался
        assert event_component is not None
        assert event_component.get_component_name() == "EventRewardComponent"
        
        # Вызываем calculate_reward
        result = event_component.calculate_reward(sample_state)
        
        # Проверяем результат
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "event"
        assert isinstance(result.raw_value, float)
        
        print(f"Event component result: {result.raw_value}")
    
    def test_shaping_component_basic_functionality(self, config, sample_state):
        """Тест базовой функциональности Shaping компонента"""
        
        # Создаем компонент
        shaping_component = ShapingRewardComponent(config)
        
        # Проверяем, что компонент создался
        assert shaping_component is not None
        assert shaping_component.get_component_name() == "ShapingRewardComponent"
        
        # Вызываем calculate_reward
        result = shaping_component.calculate_reward(sample_state)
        
        # Проверяем результат
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "shaping"
        assert isinstance(result.raw_value, float)
        
        print(f"Shaping component result: {result.raw_value}")
    
    def test_both_components_integration(self, config, sample_state):
        """Тест интеграции обоих компонентов"""
        
        # Создаем оба компонента
        event_component = EventRewardComponent(config)
        shaping_component = ShapingRewardComponent(config)
        
        # Получаем результаты
        event_result = event_component.calculate_reward(sample_state)
        shaping_result = shaping_component.calculate_reward(sample_state)
        
        # Проверяем, что оба работают
        assert event_result is not None
        assert shaping_result is not None
        
        # Проверяем, что можем их агрегировать
        total_reward = event_result.raw_value + shaping_result.raw_value
        assert isinstance(total_reward, float)
        
        print(f"Combined Phase 2 reward: Event={event_result.raw_value:.3f}, "
              f"Shaping={shaping_result.raw_value:.3f}, Total={total_reward:.3f}")
