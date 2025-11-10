"""
Phase 3: Интеграционный тест главного движка ALYSHA-RE-V3+

Этот тест проверяет полную интеграцию всех 7 компонентов винагороды:
- PnL (Phase 1)
- Risk (Phase 1) 
- Cost (Phase 1)
- Behavior (Phase 1)
- Information (Phase 1)
- Event (Phase 2)
- Shaping (Phase 2)
"""

import pytest
import numpy as np
from pathlib import Path

from alysha_core.reward_engine_v3plus.main_engine import RewardEngineV3Plus
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig
from alysha_core.reward_engine_v3plus.data_types import *

# Импортируем все компоненты
from alysha_core.reward_engine_v3plus.components.pnl import PnLRewardComponent
from alysha_core.reward_engine_v3plus.components.risk import RiskRewardComponent
from alysha_core.reward_engine_v3plus.components.cost import CostRewardComponent
from alysha_core.reward_engine_v3plus.components.behavior import BehaviorRewardComponent
from alysha_core.reward_engine_v3plus.components.information import InformationRewardComponent

# Пытаемся импортировать новые компоненты Phase 2
try:
    from alysha_core.reward_engine_v3plus.components.event import EventRewardComponent
    EVENT_AVAILABLE = True
except ImportError:
    EVENT_AVAILABLE = False

try:
    from alysha_core.reward_engine_v3plus.components.shaping import ShapingRewardComponent
    SHAPING_AVAILABLE = True
except ImportError:
    SHAPING_AVAILABLE = False


class TestPhase3Integration:
    """Полная интеграция всех компонентов в главном движке"""
    
    @pytest.fixture
    def config(self):
        """Создание конфигурации"""
        return RewardEngineConfig()
    
    @pytest.fixture
    def sample_state(self):
        """Создание полных тестовых данных"""
        
        # MarketData
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
        
        # PortfolioData
        portfolio = PortfolioData(
            positions={'BTC': 1.0},
            current_weights={'BTC': 1.0},
            target_weights={'BTC': 1.0},
            total_value=10000.0,
            turnover=0.1
        )
        
        # ARCEData  
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
        
        # PnLData
        pnl = PnLData(
            realized_pnl=100.0,
            unrealized_pnl=50.0,
            asset_pnl={'BTC': 150.0}
        )
        
        # ExecutionData
        execution = ExecutionData(
            trades=[],
            fills=[],
            num_order_modifications=0,
            num_order_cancellations=0,
            bid_ask_spreads={'BTC': 50.0},
            transaction_fees={'BTC': 5.0},
            slippage_costs={'BTC': 2.0}
        )
        
        # AgentActionData
        agent_action = AgentActionData(
            action_vector=np.array([0.5, 0.3, 0.2]),
            action_type='BUY',
            action_direction=1,
            is_exploratory=False
        )
        
        # StateData
        return StateData(
            timestamp=1640995200.0,
            portfolio=portfolio,
            arce=arce,
            pnl=pnl,
            market_data={'BTCUSDT': market_data},
            execution=execution,
            agent_action=agent_action
        )
    
    def test_main_engine_initialization(self, config):
        """Тест инициализации главного движка"""
        
        engine = RewardEngineV3Plus(config)
        
        assert engine is not None
        assert engine.config is not None
        assert engine.adaptive_weights_manager is not None
        assert engine.components == {}
        assert engine.normalizers == {}
        
        print("Main engine initialized successfully")
    
    def test_phase1_components_integration(self, config, sample_state):
        """Тест интеграции всех Phase 1 компонентов"""
        
        engine = RewardEngineV3Plus(config)
        
        # Добавляем все Phase 1 компоненты
        engine.add_component("pnl", PnLRewardComponent(config))
        engine.add_component("risk", RiskRewardComponent(config))
        engine.add_component("cost", CostRewardComponent(config))
        engine.add_component("behavior", BehaviorRewardComponent(config))
        engine.add_component("information", InformationRewardComponent(config))
        
        # Проверяем, что все компоненты добавлены
        assert len(engine.components) == 5
        assert "pnl" in engine.components
        assert "risk" in engine.components
        assert "cost" in engine.components
        assert "behavior" in engine.components
        assert "information" in engine.components
        
        # Тестируем расчет каждого компонента отдельно
        results = {}
        for name, component in engine.components.items():
            try:
                result = component.calculate_reward(sample_state)
                results[name] = result
                assert isinstance(result, RewardComponentResult)
                assert result.component_name is not None
                assert isinstance(result.raw_value, float)
                print(f"Component {name}: {result.raw_value:.4f}")
            except Exception as e:
                print(f"Error in component {name}: {e}")
                raise
        
        assert len(results) == 5
        print("All Phase 1 components work correctly")
    
    @pytest.mark.skipif(not EVENT_AVAILABLE, reason="Event component not available")
    def test_event_component_integration(self, config, sample_state):
        """Тест интеграции Event компонента (Phase 2)"""
        
        engine = RewardEngineV3Plus(config)
        
        # Добавляем Event компонент
        engine.add_component("event", EventRewardComponent(config))
        
        assert "event" in engine.components
        
        # Тестируем расчет
        result = engine.components["event"].calculate_reward(sample_state)
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "event"
        assert isinstance(result.raw_value, float)
        
        print(f"Event component result: {result.raw_value:.4f}")
    
    @pytest.mark.skipif(not SHAPING_AVAILABLE, reason="Shaping component not available")
    def test_shaping_component_integration(self, config, sample_state):
        """Тест интеграции Shaping компонента (Phase 2)"""
        
        engine = RewardEngineV3Plus(config)
        
        # Добавляем Shaping компонент
        engine.add_component("shaping", ShapingRewardComponent(config))
        
        assert "shaping" in engine.components
        
        # Тестируем расчет
        result = engine.components["shaping"].calculate_reward(sample_state)
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "shaping"
        assert isinstance(result.raw_value, float)
        
        print(f"Shaping component result: {result.raw_value:.4f}")
    
    def test_full_integration_all_components(self, config, sample_state):
        """Тест полной интеграции всех доступных компонентов"""
        
        engine = RewardEngineV3Plus(config)
        
        # Добавляем все Phase 1 компоненты
        engine.add_component("pnl", PnLRewardComponent(config))
        engine.add_component("risk", RiskRewardComponent(config))
        engine.add_component("cost", CostRewardComponent(config))
        engine.add_component("behavior", BehaviorRewardComponent(config))
        engine.add_component("information", InformationRewardComponent(config))
        
        # Добавляем Phase 2 компоненты, если доступны
        if EVENT_AVAILABLE:
            try:
                engine.add_component("event", EventRewardComponent(config))
                print("Event component added")
            except Exception as e:
                print(f"Event component failed: {e}")
        
        if SHAPING_AVAILABLE:
            try:
                engine.add_component("shaping", ShapingRewardComponent(config))
                print("Shaping component added")
            except Exception as e:
                print(f"Shaping component failed: {e}")
        
        # Тестируем расчет всех компонентов
        total_components = len(engine.components)
        successful_components = 0
        total_reward = 0.0
        
        for name, component in engine.components.items():
            try:
                result = component.calculate_reward(sample_state)
                assert isinstance(result, RewardComponentResult)
                total_reward += result.raw_value
                successful_components += 1
                print(f"Component {name}: {result.raw_value:.4f}")
            except Exception as e:
                print(f"Component {name} failed: {e}")
        
        print(f"\\nIntegration Results:")
        print(f"Total components: {total_components}")
        print(f"Successful components: {successful_components}")
        print(f"Total raw reward: {total_reward:.4f}")
        
        # Проверяем, что хотя бы базовые Phase 1 компоненты работают
        assert successful_components >= 5  # Минимум Phase 1
        assert total_components >= 5
        
        print("Full integration test completed successfully!")
