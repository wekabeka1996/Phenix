"""
Структури даних для ALYSHA-RE-V3+ Reward Engine

Цей модуль містить dataclass'и та типи для передачі даних між компонентами винагороди.
Всі структури спроектовані згідно з математичними формулами з роадмапу.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Union, Any
from enum import Enum
import numpy as np
from datetime import datetime


# CONSOLIDATED: Use canonical MarketRegime from core.research.market_regime
# Legacy mapping: CRISIS -> PANIC, HIGH_VOLATILITY -> VOLATILITY
# See Road_discusion.md for context
from core.research.market_regime import MarketRegime


class ActionType(Enum):
    """Типи торгових дій"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"


@dataclass
class ARCEData:
    """Дані з ARCE (Adaptive Risk Control Engine)"""
    # Ризикові метрики
    var_current: float
    var_limit: float
    cvar_current: float
    cvar_limit: float
    drawdown_current: float
    drawdown_limit: float
    
    # Волатільність портфеля
    portfolio_volatility: float
    target_volatility: float
    volatility_range: float
    
    # Активні ARCE прапори
    active_flags: List[Dict[str, Any]]  # [{"name": str, "severity": float, "penalty_multiplier": float}]
    
    # Ринковий режим
    regime_tag: MarketRegime
    
    # Ліміти позицій
    position_limits: Dict[str, float]  # {asset_id: max_position_limit}


@dataclass
class MarketData:
    """Ринкові дані"""
    # Основні ціни
    current_price: float
    previous_price: float
    high_price: float
    low_price: float
    open_price: float
    
    # Об'єм торгів
    current_volume: float
    average_volume: float
    volume_history: List[float]
    
    # Волатільність
    current_volatility: float
    volatility_history: List[float]
    
    # Спреди та ліквідність
    bid_ask_spread: float
    market_depth: Dict[str, float]  # {"bid": depth, "ask": depth}
    
    # Додаткові метрики
    price_change: float
    price_change_percent: float
    
    # Історичні дані для детекції подій
    price_history: List[float]
    
    # Часова мітка
    timestamp: float


@dataclass
class PortfolioData:
    """Дані портфеля"""
    # Поточні позиції
    positions: Dict[str, float]  # {asset_id: position_size}
    
    # Поточні ваги портфеля  
    current_weights: Dict[str, float]  # {asset_id: weight}
    
    # Цільові ваги портфеля
    target_weights: Dict[str, float]  # {asset_id: target_weight}
    
    # Загальна вартість портфеля
    total_value: float
    
    # Обіг портфеля
    turnover: float


@dataclass
class TradeData:
    """Дані про одну угоду"""
    asset_id: str
    quantity: float
    price: float
    timestamp: float
    fees: float
    commissions: float
    side: str  # "BUY" або "SELL"


@dataclass
class FillData:
    """Дані про виконання ордеру"""
    asset_id: str
    fill_price: float
    expected_price: float
    quantity: float
    timestamp: float


@dataclass
class ExecutionData:
    """Дані виконання угод з інформацією про витрати"""
    # Угоди за поточний крок
    trades: List[TradeData]
    
    # Виконання ордерів (для slippage)
    fills: List[FillData]
    
    # Статистика ордерів
    num_order_modifications: int
    num_order_cancellations: int
    
    # Витрати на спреди bid-ask
    bid_ask_spreads: Dict[str, Union[float, Dict[str, float]]]  # {asset_id: spread або {spread, volume}}
    
    # Транзакційні комісії
    transaction_fees: Dict[str, Union[float, Dict[str, float]]]  # {asset_id: fee або {fee, volume}}
    
    # Витрати на проковзування (slippage)
    slippage_costs: Dict[str, Union[float, Dict[str, Any]]]  # {asset_id: slippage або {slippage, volume, expected_price, actual_price}}


@dataclass
class AgentActionData:
    """Дані про дії агента"""
    # Вектор дії (може бути різних форматів)
    action_vector: np.ndarray
    
    # Тип дії
    action_type: str  # "HOLD", "BUY", "SELL", "REBALANCE"
    
    # Направлення дії (+1, -1, 0)
    action_direction: int
    
    # Індикатор дослідницької дії
    is_exploratory: bool


@dataclass  
class ModelPredictionData:
    """Дані прогнозів моделі"""
    # Вектор прогнозів
    prediction_vector: np.ndarray
    
    # Впевненість моделі
    confidence: float
    
    # Невизначеність моделі (для exploration)
    model_uncertainty: float
    
    # Прогнозований напрямок
    predicted_direction: int  # +1, -1, 0


@dataclass
class PnLData:
    """Дані PnL"""
    # Реалізований PnL
    realized_pnl: float
    
    # Нереалізований PnL  
    unrealized_pnl: float
    
    # PnL по активах
    asset_pnl: Dict[str, float]  # {asset_id: pnl}


@dataclass
class StateData:
    """Загальні дані стану на час t"""
    timestamp: float
    
    # Дані портфеля
    portfolio: PortfolioData
    
    # Дані ARCE
    arce: ARCEData
    
    # Дані PnL
    pnl: PnLData
    
    # Додаткові ринкові дані
    market_data: Optional[MarketData] = None
    
    # Дані виконання торгів (для Cost компоненти)
    execution: Optional[ExecutionData] = None
    
    # Дані дій агента (для Behavior компоненти)
    agent_action: Optional[AgentActionData] = None
    
    # Дані прогнозів моделі (для Model Uncertainty)
    model_prediction: Optional[ModelPredictionData] = None


@dataclass
class EventData:
    """Дані про дискретні події"""
    event_type: str
    event_name: str
    severity: float
    impact_value: float
    timestamp: float
    metadata: Dict[str, Any]


@dataclass
class ActiveEventsData:
    """Активні події на поточний момент"""
    events: List[EventData]


@dataclass
class RewardComponentResult:
    """Результат розрахунку компоненти винагороди"""
    component_name: str
    raw_value: float
    normalized_value: Optional[float] = None
    subcomponents: Optional[Dict[str, float]] = None  # для детального логування
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TotalRewardResult:
    """Фінальний результат розрахунку винагороди"""
    total_reward: float
    component_rewards: Dict[str, RewardComponentResult]
    adaptive_weights: Dict[str, float]
    normalization_stats: Dict[str, Dict[str, float]]
    timestamp: float
    metadata: Dict[str, Any]


# Типи для зручності
ComponentValue = Union[float, RewardComponentResult]
WeightsDict = Dict[str, float]
ConfigDict = Dict[str, Any]


@dataclass
class TradingState:
    """
    Загальна структура торгового стану для адаптера PPO.
    Об'єднує всі необхідні дані для розрахунку винагороди.
    """
    # Базова інформація
    symbol: str
    timestamp: datetime
    price: float
    
    # Портфель
    portfolio_value: float
    available_balance: float
    
    # Ринок
    market_volatility: float
    market_trend: str
    
    # Позиція
    position_size: float = 0.0
    position_value: float = 0.0
    
    # PnL
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    # Дія
    action_type: ActionType = ActionType.HOLD
    action_size: float = 0.0
    
    # Витрати
    transaction_cost: float = 0.0
    slippage: float = 0.0
    
    # Додаткові дані
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Ініціалізація після створення об'єкта"""
        if self.metadata is None:
            self.metadata = {}
