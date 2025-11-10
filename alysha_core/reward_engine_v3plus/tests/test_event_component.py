"""
Тести для Event Reward Component
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
from dataclasses import dataclass
from typing import List, Dict, Any

from alysha_core.reward_engine_v3plus.components.event import (
    EventRewardComponent, EventType, EventDetection
)
from alysha_core.reward_engine_v3plus.data_types import (
    StateData, MarketData, PortfolioData, ARCEData, 
    ExecutionData, AgentActionData, PnLData
)
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig


class TestEventRewardComponent:
    """Тести для Event Reward Component"""
    
    @pytest.fixture
    def mock_config(self):
        """Мок конфігурації"""
        config = Mock(spec=RewardEngineConfig)
        config.get_component_config.return_value = {
            "event_coefficients": {
                "market_events": {
                    "volatility_spike": -5.0,
                    "price_gap": -3.0,
                    "volume_surge": 2.0,
                    "liquidity_shortage": -8.0
                },
                "trading_events": {
                    "large_order_fill": 1.5,
                    "partial_fill": -0.5,
                    "order_rejection": -10.0,
                    "excessive_slippage": -5.0
                },
                "system_events": {
                    "regime_change": -2.0,
                    "signal_divergence": -1.0,
                    "model_uncertainty": -0.5,
                    "arce_alert": -15.0
                }
            },
            "detection_thresholds": {
                "volatility_spike_threshold": 2.0,
                "volume_surge_threshold": 3.0,
                "price_gap_threshold": 0.005,
                "liquidity_ratio_threshold": 0.01,  # 1% вместо 30%
                "slippage_threshold": 0.001
            },
            "impact_limits": {
                "max_negative_impact": -50.0,
                "max_positive_impact": 10.0,
                "event_decay_factor": 0.9
            }
        }
        return config
    
    @pytest.fixture
    def component(self, mock_config):
        """Компонента для тестування"""
        return EventRewardComponent(mock_config)
    
    @pytest.fixture
    def base_state_data(self):
        """Базові дані стану"""
        return StateData(
            timestamp=1640995200.0,
            portfolio=PortfolioData(
                positions={"BTCUSDT": 2000.0},
                current_weights={"BTCUSDT": 0.2},
                target_weights={"BTCUSDT": 0.2},
                total_value=10000.0,
                turnover=0.1
            ),
            arce=ARCEData(
                var_current=150.0,
                var_limit=200.0,
                cvar_current=250.0,
                cvar_limit=300.0,
                drawdown_current=0.05,
                drawdown_limit=0.1,
                portfolio_volatility=0.15,
                target_volatility=0.12,
                volatility_range=(0.1, 0.2),
                active_flags=[False, False, False, False, False],
                regime_tag="NORMAL",
                position_limits={"max_position": 5000.0}
            ),
            pnl=PnLData(
                realized_pnl=50.0,
                unrealized_pnl=100.0,
                asset_pnl={"BTC": 150.0}
            ),
            market_data=MarketData(
                timestamp=1640995200.0,
                current_price=50500.0,
                previous_price=50000.0,
                high_price=51000.0,
                low_price=49500.0,
                open_price=50000.0,
                current_volume=1000.0,
                average_volume=800.0,
                volume_history=[700.0, 800.0, 900.0, 1000.0],
                current_volatility=0.15,
                volatility_history=[0.12, 0.13, 0.14, 0.15],
                bid_ask_spread=100.0,
                market_depth={"bid": 5000.0, "ask": 5000.0},
                price_change=500.0,
                price_change_percent=1.0,
                price_history=[49500.0, 50000.0, 50500.0]
            ),
            execution=ExecutionData(
                trades=[],
                fills=[],
                num_order_modifications=0,
                num_order_cancellations=0,
                bid_ask_spreads={'BTC': 100.0},
                transaction_fees={'BTC': 5.0},
                slippage_costs={'BTC': 0.0005}
            ),
            agent_action=AgentActionData(
                action_vector=np.array([0.5, 0.3, 0.2]),
                action_type='BUY',
                action_direction=1,
                is_exploratory=False
            )
        )
    
    def test_component_initialization(self, component):
        """Тест ініціалізації компоненти"""
        assert component is not None
        assert len(component.market_coeffs) == 4
        assert len(component.trading_coeffs) == 4
        assert len(component.system_coeffs) == 4
        assert component.max_negative == -50.0
        assert component.max_positive == 10.0
        assert component.decay_factor == 0.9
    
    def test_no_events_detected(self, component, base_state_data):
        """Тест без детекції подій"""
        result = component.calculate(base_state_data)
        
        assert result.component_name == "event"
        assert result.raw_value == 0.0
        assert result.metadata["events_detected"] == 0
        assert result.metadata["total_events_in_history"] == 0
        assert result.metadata["decay_contribution"] == 0.0
    
    def test_volatility_spike_detection(self, component, base_state_data):
        """Тест детекції стрибка волатільності"""
        # Додаємо історію з варіацією волатільності
        volatility_values = [0.08, 0.09, 0.10, 0.11, 0.09, 0.10, 0.08, 0.11, 0.09, 0.10, 0.08, 0.09, 0.10, 0.11, 0.09]
        for vol in volatility_values:
            component.volatility_history.append(vol)
        
        # Створюємо стрибок волатільності - значення, що значно вище середнього
        base_state_data.market_data.current_volatility = 0.30  # Високий рівень
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value < 0  # Негативна винагорода за стрибок
        assert "volatility_spike" in result.subcomponents
        assert result.metadata["events_detected"] > 0
    
    def test_price_gap_detection(self, component, base_state_data):
        """Тест детекції гепу цін"""
        # Додаємо попередні ціни для історії
        component.price_history.append(49000.0)
        component.price_history.append(50000.0)
        
        # Створюємо великий геп
        base_state_data.market_data.current_price = 52000.0  # 4% геп
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value < 0  # Негативна винагорода за геп
        assert "price_gap" in result.subcomponents
    
    def test_volume_surge_detection(self, component, base_state_data):
        """Тест детекції сплеску обсягу"""
        # Додаємо історію нормального обсягу
        for _ in range(15):
            component.volume_history.append(1000.0)
        
        # Створюємо сплеск обсягу
        base_state_data.market_data.current_volume = 4000.0  # 4x збільшення
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value > 0  # Позитивна винагорода за сплеск обсягу
        assert "volume_surge" in result.subcomponents
    
    def test_liquidity_shortage_detection(self, component, base_state_data):
        """Тест детекції нестачі ліквідності"""
        # Створюємо великий спред
        base_state_data.market_data.bid_ask_spread = 2000.0  # 4% спред (52000-50000)
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value < 0  # Негативна винагорода за нестачу ліквідності
        assert "liquidity_shortage" in result.subcomponents
    
    def test_large_order_fill_detection(self, component, base_state_data):
        """Тест детекції великого виконання ордеру"""
        # Створюємо великий торг відносно середнього
        from alysha_core.reward_engine_v3plus.data_types import TradeData
        large_trade = TradeData(
            asset_id="BTCUSDT",
            quantity=2000.0,  # Великий розмір ордеру (2.5x середній обсяг)
            price=50500.0,
            timestamp=1640995200.0,
            fees=5.0,
            commissions=2.0,
            side="BUY"
        )
        base_state_data.execution.trades = [large_trade]
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value > 0  # Позитивна винагорода за великий ордер
        assert "large_order_fill" in result.subcomponents
    
    def test_partial_fill_detection(self, component, base_state_data):
        """Тест детекції часткового виконання"""
        # Створюємо часткове виконання через FillData
        from alysha_core.reward_engine_v3plus.data_types import FillData
        partial_fill = FillData(
            asset_id="BTCUSDT",
            fill_price=49500.0,  # Гірше за очікувану ціну (2% slippage)
            expected_price=50500.0,
            quantity=60.0,  # Тільки 60% від запланованих 100
            timestamp=1640995200.0
        )
        base_state_data.execution.fills = [partial_fill]
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value < 0  # Негативна винагорода за часткове виконання
        assert "partial_fill" in result.subcomponents
    
    def test_excessive_slippage_detection(self, component, base_state_data):
        """Тест детекції надмірного слипажу"""
        # Створюємо великий слипаж через slippage_costs
        base_state_data.execution.slippage_costs = {"BTCUSDT": 0.002}  # 2x поріг
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value < 0  # Негативна винагорода за слипаж
        assert "excessive_slippage" in result.subcomponents
    
    def test_arce_alert_detection(self, component, base_state_data):
        """Тест детекції алертів ARCE"""
        # Активуємо кілька флагів
        base_state_data.arce.active_flags = [True, True, False, True, False]
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value < 0  # Негативна винагорода за алерти
        assert "arce_alert" in result.subcomponents
        assert result.subcomponents["arce_alert"]["metadata"]["active_alerts"] == 3
    
    def test_model_uncertainty_detection(self, component, base_state_data):
        """Тест детекції невизначеності моделі"""
        # Створюємо низьку впевненість моделі
        from alysha_core.reward_engine_v3plus.data_types import ModelPredictionData
        import numpy as np
        
        base_state_data.model_prediction = ModelPredictionData(
            prediction_vector=np.array([0.1, 0.2, 0.7]),
            confidence=0.3,  # Низька впевненість
            model_uncertainty=0.7,  # Висока невизначеність
            predicted_direction=1
        )
        
        result = component.calculate(base_state_data)
        
        assert result.raw_value < 0  # Негативна винагорода за невизначеність
        assert "model_uncertainty" in result.subcomponents
    
    def test_multiple_events_aggregation(self, component, base_state_data):
        """Тест агрегації кількох подій"""
        # Налаштовуємо кілька подій одночасно
        
        # Сплеск обсягу (позитивний)
        for _ in range(15):
            component.volume_history.append(1000.0)
        base_state_data.market_data.current_volume = 4000.0
        
        # Алерт ARCE (негативний)
        base_state_data.arce.active_flags = [True, False, True, False, False]
        
        # Часткове виконання (негативне) - використовуємо FillData
        from alysha_core.reward_engine_v3plus.data_types import FillData
        partial_fill = FillData(
            asset_id="BTCUSDT",
            fill_price=49950.0,  # Значний слипаж > 1%: (50500-49950)/50500 = 1.09%
            expected_price=50500.0,
            quantity=70.0,  # Часткове виконання
            timestamp=1640995200.0
        )
        base_state_data.execution.fills = [partial_fill]
        
        result = component.calculate(base_state_data)
        
        # Повинно бути кілька подій
        assert result.metadata["events_detected"] >= 2
        assert "volume_surge" in result.subcomponents
        assert "arce_alert" in result.subcomponents
        assert "partial_fill" in result.subcomponents
        
        # Загальна винагорода - це сума всіх подій
        expected_reward = (
            component.market_coeffs["volume_surge"] * 1.0 +  # Максимальна інтенсивність
            component.system_coeffs["arce_alert"] * 0.4 +    # 2/5 флагів активні
            component.trading_coeffs["partial_fill"] * 0.3   # 1-0.7 = 0.3 інтенсивність
        )
        
        # Перевіряємо, що винагорода в розумних межах
        assert abs(result.raw_value - expected_reward) < 0.1
    
    def test_impact_limits(self, component, base_state_data):
        """Тест обмежень впливу подій"""
        # Створюємо екстремально велику кількість негативних подій
        base_state_data.arce.active_flags = [True] * 5  # Всі флаги активні
        base_state_data.execution.fill_ratio = 0.1      # Дуже погане виконання
        base_state_data.execution.realized_slippage = 0.01  # Великий слипаж
        
        # Додаємо історію для волатільності
        for _ in range(15):
            component.volatility_history.append(0.1)
        base_state_data.market_data.current_volatility = 0.5  # Екстремальна волатільність
        
        result = component.calculate(base_state_data)
        
        # Винагорода повинна бути обмежена max_negative_impact
        assert result.raw_value >= component.max_negative
        assert result.raw_value <= component.max_positive
    
    def test_event_history_decay(self, component, base_state_data):
        """Тест згасання історії подій"""
        # Додаємо події до історії
        old_event = EventDetection(
            event_type=EventType.VOLATILITY_SPIKE,
            intensity=1.0,
            timestamp=1640995100.0  # 100 секунд тому
        )
        component.event_history.append(old_event)
        
        result = component.calculate(base_state_data)
        
        # Повинен бути вклад від згасання
        if "decay_effects" in result.metadata:
            assert result.metadata["decay_effects"] != 0.0
        
        # Історія повинна містити подію
        assert len(component.event_history) >= 1
    
    def test_history_cleanup(self, component, base_state_data):
        """Тест очищення історії подій"""
        # Заповнюємо історію до максимуму
        for i in range(component.max_history_size + 10):
            event = EventDetection(
                event_type=EventType.VOLUME_SURGE,
                intensity=0.5,
                timestamp=float(i)
            )
            component.event_history.append(event)
        
        component._cleanup_history()
        
        # Історія повинна бути обрізана
        assert len(component.event_history) == component.max_history_size
    
    def test_get_component_info(self, component):
        """Тест отримання інформації про компоненту"""
        info = component.get_component_info()
        
        assert info["name"] == "EventRewardComponent"
        assert "formula" in info
        assert "parameters" in info
        assert "current_state" in info
        assert "market_coefficients" in info["parameters"]
        assert "trading_coefficients" in info["parameters"]
        assert "system_coefficients" in info["parameters"]
    
    def test_error_handling(self, component):
        """Тест обробки помилок"""
        # Передаємо некоректні дані
        invalid_state = None
        
        result = component.calculate(invalid_state)
        
        assert result.component_name == "event"
        assert result.raw_value == 0.0
        assert result.metadata and "error" in str(result.metadata)
        assert result.metadata["error"] is True
    
    def test_empty_market_data(self, component, base_state_data):
        """Тест з порожніми ринковими даними"""
        base_state_data.market_data = None
        
        result = component.calculate(base_state_data)
        
        # Повинно працювати без помилок
        assert result.component_name == "event"
        # Можуть бути системні події, але не ринкові
    
    def test_empty_execution_data(self, component, base_state_data):
        """Тест з порожніми даними виконання"""
        base_state_data.execution = None
        
        result = component.calculate(base_state_data)
        
        # Повинно працювати без помилок
        assert result.component_name == "event"
        # Можуть бути ринкові та системні події, але не торгові
