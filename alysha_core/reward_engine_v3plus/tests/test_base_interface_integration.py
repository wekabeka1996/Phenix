"""
Тести для перевірки інтеграції BaseRewardComponent інтерфейсу

Цей модуль тестує, що всі компоненти Phase 1 правильно реалізують
BaseRewardComponent інтерфейс та їх calculate_reward методи працюють коректно.
"""

import pytest
import numpy as np
from datetime import datetime
from unittest.mock import Mock

from ..components.pnl import PnLRewardComponent
from ..components.risk import RiskRewardComponent
from ..components.cost import CostRewardComponent
from ..components.behavior import BehaviorRewardComponent
from ..components.information import InformationRewardComponent
from ..components.base import BaseRewardComponent

from ..data_types import (
    StateData, PnLData, ARCEData, PortfolioData, 
    RewardComponentResult, AgentActionData
)
from ..utils import RewardEngineConfig


class TestBaseInterfaceIntegration:
    """Тести для BaseRewardComponent інтерфейсу"""
    
    @pytest.fixture
    def config(self):
        """Створити mock конфігурацію"""
        config = Mock(spec=RewardEngineConfig)
        config.get_component_config.return_value = {
            "enabled": True,
            "realized_pnl": {"scaling_factor": 1.0, "weight": 1.0},
            "unrealized_pnl": {"scaling_factor": 0.8, "weight": 0.8},
            "subcomponent_weights": {},
            "drawdown": {"c_dd": 2.0, "dd_limit": 0.05},
            "var": {"c_var": 3.0, "var_limit": 0.02},
            "cvar": {"c_cvar": 4.0, "cvar_limit": 0.03},
            "volatility": {"c_vol": 1.5, "target_vol": 0.15},
            "arce_flags": {"base_penalty": 1.0},
            "inventory": {"c_inv": 2.5},
            "bid_ask": {"alpha_bid_ask": 0.5},
            "transaction": {"alpha_transaction": 0.3},
            "slippage": {"alpha_slippage": 0.7},
            "strategy_consistency": {"beta_strategy": 2.0},
            "trading_frequency": {"beta_frequency": 1.5},
            "execution_latency": {"beta_latency": 1.0},
            "signal_alignment": {"c_align": 4.0, "alignment_function": "cosine"},
            "strategic_exploration": {"c_explore": 2.0}
        }
        config.is_component_enabled.return_value = True
        config.get.return_value = -10.0
        return config
    
    @pytest.fixture
    def state_data(self):
        """Створити тестові дані стану"""
        from ..data_types import MarketRegime
        
        pnl_data = PnLData(
            realized_pnl=100.0,
            unrealized_pnl=50.0,
            asset_pnl={"BTCUSDT": 150.0}
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
        
        agent_action = AgentActionData(
            action_vector=np.array([1.0, 0.0, 0.0]),
            action_type="BUY",
            action_direction=1,
            is_exploratory=False
        )
        
        return StateData(
            timestamp=1640995200.0,  # 2022-01-01
            portfolio=portfolio_data,
            arce=arce_data,
            pnl=pnl_data,
            market_data={},
            agent_action=agent_action
        )
    
    def test_pnl_component_base_interface(self, config, state_data):
        """Тест PnL компонента з BaseRewardComponent інтерфейсом"""
        component = PnLRewardComponent(config)
        
        # Перевіряємо, що є BaseRewardComponent
        assert isinstance(component, BaseRewardComponent)
        
        # Тестуємо calculate_reward метод
        result = component.calculate_reward(state_data)
        
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "pnl"
        assert isinstance(result.raw_value, (int, float))
        assert "realized_component" in result.subcomponents
        assert "unrealized_component" in result.subcomponents
        
    def test_risk_component_base_interface(self, config, state_data):
        """Тест Risk компонента з BaseRewardComponent інтерфейсом"""
        component = RiskRewardComponent(config)
        
        # Перевіряємо, що є BaseRewardComponent
        assert isinstance(component, BaseRewardComponent)
        
        # Тестуємо calculate_reward метод
        result = component.calculate_reward(state_data)
        
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "risk"
        assert isinstance(result.raw_value, (int, float))
        
    def test_cost_component_base_interface(self, config, state_data):
        """Тест Cost компонента з BaseRewardComponent інтерфейсом"""
        component = CostRewardComponent(config)
        
        # Перевіряємо, що є BaseRewardComponent
        assert isinstance(component, BaseRewardComponent)
        
        # Тестуємо calculate_reward метод
        result = component.calculate_reward(state_data)
        
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "cost"
        assert isinstance(result.raw_value, (int, float))
        
    def test_behavior_component_base_interface(self, config, state_data):
        """Тест Behavior компонента з BaseRewardComponent інтерфейсом"""
        component = BehaviorRewardComponent(config)
        
        # Перевіряємо, що є BaseRewardComponent
        assert isinstance(component, BaseRewardComponent)
        
        # Тестуємо calculate_reward метод
        result = component.calculate_reward(state_data)
        
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "behavior"
        assert isinstance(result.raw_value, (int, float))
        
    def test_information_component_base_interface(self, config, state_data):
        """Тест Information компонента з BaseRewardComponent інтерфейсом"""
        component = InformationRewardComponent(config)
        
        # Перевіряємо, що є BaseRewardComponent
        assert isinstance(component, BaseRewardComponent)
        
        # Тестуємо calculate_reward метод
        result = component.calculate_reward(state_data)
        
        assert isinstance(result, RewardComponentResult)
        assert result.component_name == "information"
        assert isinstance(result.raw_value, (int, float))
        
    def test_all_components_have_base_interface(self, config):
        """Тест, що всі компоненти реалізують BaseRewardComponent"""
        components = [
            PnLRewardComponent(config),
            RiskRewardComponent(config),
            CostRewardComponent(config),
            BehaviorRewardComponent(config),
            InformationRewardComponent(config)
        ]
        
        for component in components:
            assert isinstance(component, BaseRewardComponent)
            assert hasattr(component, 'calculate_reward')
            assert callable(component.calculate_reward)
            assert hasattr(component, 'get_component_name')
            assert callable(component.get_component_name)
            
    def test_interface_consistency(self, config, state_data):
        """Тест консистентності між calculate та calculate_reward методами"""
        # Тестуємо PnL компонент
        pnl_component = PnLRewardComponent(config)
        
        # Результати повинні бути однаковими
        result_old = pnl_component.calculate(state_data)
        result_new = pnl_component.calculate_reward(state_data)
        
        assert result_old.component_name == result_new.component_name
        assert result_old.raw_value == result_new.raw_value
        assert result_old.subcomponents == result_new.subcomponents
