"""
Event Reward Component для ALYSHA-RE-V3+

Реалізує компоненту нагороди за події R_Event,t за формулою:
R_Event,t = Σ δ_e × I_e,t

де:
- δ_e - коефіцієнт впливу події типу e
- I_e,t - індикатор події (1 якщо подія відбулася, 0 інакше)

Події включають:
- Ринкові події (стрибки волатільності, гепи цін, сплески обсягу)
- Торгові події (виконання ордерів, слипаж, відхилення)
- Системні події (зміни режимів, алерти ARCE)
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from ..data_types import (
    StateData, RewardComponentResult, MarketData, PortfolioData, 
    ARCEData, ExecutionData, AgentActionData
)
from ..utils import RewardEngineConfig
from .base import BaseRewardComponent


class EventType(Enum):
    """Типи подій для відстеження"""
    # Ринкові події
    VOLATILITY_SPIKE = "volatility_spike"
    PRICE_GAP = "price_gap"
    VOLUME_SURGE = "volume_surge"
    LIQUIDITY_SHORTAGE = "liquidity_shortage"
    
    # Торгові події
    LARGE_ORDER_FILL = "large_order_fill"
    PARTIAL_FILL = "partial_fill"
    ORDER_REJECTION = "order_rejection"
    EXCESSIVE_SLIPPAGE = "excessive_slippage"
    
    # Системні події
    REGIME_CHANGE = "regime_change"
    SIGNAL_DIVERGENCE = "signal_divergence"
    MODEL_UNCERTAINTY = "model_uncertainty"
    ARCE_ALERT = "arce_alert"


@dataclass
class EventDetection:
    """Результат детекції події"""
    event_type: EventType
    intensity: float        # інтенсивність події [0, 1]
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None  # ✅ допускаємо None


class EventRewardComponent(BaseRewardComponent):
    """
    Event Reward Component - винагорода за важливі ринкові, торгові та системні події.
    
    Відстежує та реагує на:
    - Ринкові події (волатільність, ліквідність, обсяги)
    - Торгові події (виконання ордерів, слипаж) 
    - Системні події (зміни режимів, алерти)
    """
    
    def __init__(self, config: RewardEngineConfig):
        super().__init__(config.get_component_config("event"))
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Отримуємо конфігурацію для компоненти подій
        event_config = config.get_component_config("event")
        
        # Коефіцієнти впливу подій
        coeffs = event_config.get("event_coefficients", {})
        self.market_coeffs = coeffs.get("market_events", {})
        self.trading_coeffs = coeffs.get("trading_events", {})
        self.system_coeffs = coeffs.get("system_events", {})
        
        # Пороги детекції
        self.thresholds = event_config.get("detection_thresholds", {})
        
        # Обмеження впливу
        self.impact_limits = event_config.get("impact_limits", {})
        self.max_negative = self.impact_limits.get("max_negative_impact", -50.0)
        self.max_positive = self.impact_limits.get("max_positive_impact", 10.0)
        self.decay_factor = self.impact_limits.get("event_decay_factor", 0.9)
        
        # Історія подій для згасання
        self.event_history: List[EventDetection] = []
        self.max_history_size = 100
        
        # Статистики для детекції аномалій
        self.volatility_history: List[float] = []
        self.volume_history: List[float] = []
        self.price_history: List[float] = []
        
        self.logger.info(f"EventRewardComponent ініціалізовано з {len(self.market_coeffs)} ринковими, "
                        f"{len(self.trading_coeffs)} торговими та {len(self.system_coeffs)} системними подіями")
    
    def calculate_reward(self, state: StateData) -> RewardComponentResult:
        """
        Основний метод для розрахунку винагороди Event компонента
        
        Args:
            state: Поточні дані стану
            
        Returns:
            RewardComponentResult з винагородою та метаданими
        """
        return self.calculate(state)
    
    def calculate(self, state_data: StateData) -> RewardComponentResult:
        """
        Розраховує винагороду за події
        
        Args:
            state_data: Поточні дані стану
            
        Returns:
            RewardComponentResult з деталями винагороди за події
        """
        try:
            # Детектуємо події
            detected_events = self._detect_events(state_data)
            
            total_reward = 0.0
            event_details: Dict[str, Any] = {}
            simple_subcomponents: Dict[str, float] = {}   # тільки числові значення для type-safety
             
            for event in detected_events:
                coeff = self._get_event_coefficient(event.event_type)
                event_impact = coeff * event.intensity
                total_reward += event_impact
                
                event_details[event.event_type.value] = {
                    "coefficient": coeff,
                    "intensity": event.intensity,
                    "impact": event_impact,
                    "metadata": event.metadata or {}
                }
                simple_subcomponents[event.event_type.value] = event_impact
                
                self.logger.debug(f"Подія {event.event_type.value}: коеф={coeff:.3f}, "
                                f"інтенсивність={event.intensity:.3f}, вплив={event_impact:.3f}")
            
            decay_reward = self._calculate_decay_effects()
            total_reward += decay_reward
            if decay_reward != 0:
                simple_subcomponents["decay_effects"] = decay_reward
            
            total_reward = float(np.clip(total_reward, self.max_negative, self.max_positive))
            
            # Зберігаємо нові події в історію
            self.event_history.extend(detected_events)
            self._cleanup_history()
            
            self.logger.debug(f"Загальна винагорода за події: {total_reward:.4f} "
                            f"(детектовано {len(detected_events)} подій)")
            
            return RewardComponentResult(
                component_name="event",
                raw_value=total_reward,
                subcomponents=simple_subcomponents,      # ✅ Dict[str, float]
                metadata={                               # детальні дані в metadata
                    "events_detected": len(detected_events),
                    "total_events_in_history": len(self.event_history),
                    "decay_contribution": decay_reward,
                    "event_details": event_details
                }
            )
            
        except Exception as e:
            self.logger.error(f"Помилка розрахунку Event винагороди: {e}")
            return RewardComponentResult(
                component_name="event",
                raw_value=0.0,
                subcomponents=None,                       # ✅ допускається None
                metadata={"error": True, "message": str(e)}
            )
    
    def _detect_events(self, state_data: StateData) -> List[EventDetection]:
        """Детектує події з поточних даних стану"""
        events = []
        
        # Детекція ринкових подій
        events.extend(self._detect_market_events(state_data))
        
        # Детекція торгових подій
        events.extend(self._detect_trading_events(state_data))
        
        # Детекція системних подій
        events.extend(self._detect_system_events(state_data))
        
        return events
    
    def _detect_market_events(self, state_data: StateData) -> List[EventDetection]:
        """Детектує ринкові події"""
        events = []
        
        if not state_data.market_data:
            return events
        
        market = state_data.market_data
        
        # Детекція стрибка волатільності
        vol_event = self._detect_volatility_spike(market)
        if vol_event:
            events.append(vol_event)
        
        # Детекція гепу цін
        gap_event = self._detect_price_gap(market)
        if gap_event:
            events.append(gap_event)
        
        # Детекція сплеску обсягу
        volume_event = self._detect_volume_surge(market)
        if volume_event:
            events.append(volume_event)
        
        # Детекція нестачі ліквідності
        liquidity_event = self._detect_liquidity_shortage(market)
        if liquidity_event:
            events.append(liquidity_event)
        
        # Оновлюємо історію ПІСЛЯ детекції для наступних циклів
        self._update_market_history(market)
        
        return events
    
    def _detect_trading_events(self, state_data: StateData) -> List[EventDetection]:
        """Детектує торгові події"""
        events = []
        
        if not state_data.execution:
            return events
        
        execution = state_data.execution
        
        # Детекція великого виконання ордеру через trades
        if execution.trades:
            for trade in execution.trades:
                # Порівнюємо з середнім обсягом
                avg_volume = state_data.market_data.average_volume if state_data.market_data else 1000.0
                if trade.quantity > 2.0 * avg_volume:
                    intensity = min(trade.quantity / avg_volume / 5.0, 1.0)
                    events.append(EventDetection(
                        event_type=EventType.LARGE_ORDER_FILL,
                        intensity=intensity,
                        timestamp=state_data.timestamp,
                        metadata={"trade_size": trade.quantity, "avg_volume": avg_volume}
                    ))
        
        # Детекція часткового виконання через fills
        if execution.fills:
            for fill in execution.fills:
                # Слипаж як індикатор часткового виконання
                if fill.expected_price != 0:
                    slippage_ratio = abs(fill.fill_price - fill.expected_price) / fill.expected_price
                    if slippage_ratio > 0.01:  # 1% slippage threshold
                        intensity = min(slippage_ratio * 10, 1.0)  # Scale to 0-1
                        events.append(EventDetection(
                            event_type=EventType.PARTIAL_FILL,
                            intensity=intensity,
                            timestamp=state_data.timestamp,
                            metadata={"slippage_ratio": slippage_ratio, "expected": fill.expected_price, "actual": fill.fill_price}
                        ))
        
        # Детекція надмірного слипажу через slippage_costs
        slippage_threshold = self.thresholds.get("slippage_threshold", 0.001)
        for asset, slippage_cost in execution.slippage_costs.items():
            if isinstance(slippage_cost, (int, float)) and slippage_cost > slippage_threshold:
                intensity = min(slippage_cost / slippage_threshold, 1.0)
                events.append(EventDetection(
                    event_type=EventType.EXCESSIVE_SLIPPAGE,
                    intensity=intensity,
                    timestamp=state_data.timestamp,
                    metadata={"slippage": slippage_cost, "threshold": slippage_threshold, "asset": asset}
                ))
        
        return events
    
    def _detect_system_events(self, state_data: StateData) -> List[EventDetection]:
        """Детектує системні події"""
        events = []
        
        # Детекція алертів ARCE
        if state_data.arce and hasattr(state_data.arce, 'active_flags'):
            active_alerts = sum(1 for flag in state_data.arce.active_flags if flag)
            if active_alerts > 0:
                intensity = min(active_alerts / 5.0, 1.0)  # максимум 5 флагів
                events.append(EventDetection(
                    event_type=EventType.ARCE_ALERT,
                    intensity=intensity,
                    timestamp=state_data.timestamp,
                    metadata={"active_alerts": active_alerts, "flags": state_data.arce.active_flags}
                ))
        
        # Детекція невизначеності моделі
        if (state_data.model_prediction and 
            hasattr(state_data.model_prediction, 'confidence') and 
            state_data.model_prediction.confidence < 0.5):
            intensity = 1.0 - state_data.model_prediction.confidence
            events.append(EventDetection(
                event_type=EventType.MODEL_UNCERTAINTY,
                intensity=intensity,
                timestamp=state_data.timestamp,
                metadata={"confidence": state_data.model_prediction.confidence}
            ))
        
        return events
    
    def _detect_volatility_spike(self, market: MarketData) -> Optional[EventDetection]:
        """Детектує стрибки волатільності"""
        if len(self.volatility_history) < 10:
            return None
        
        current_vol = market.current_volatility
        if current_vol == 0.0:
            return None
        
        recent_vol = np.array(self.volatility_history[-10:])
        vol_mean = np.mean(recent_vol)
        vol_std = np.std(recent_vol)
        
        if vol_std == 0:
            return None
        
        z_score = (current_vol - vol_mean) / vol_std
        threshold = self.thresholds.get("volatility_spike_threshold", 2.0)
        
        if z_score > threshold:
            intensity = min(z_score / (threshold * 2), 1.0)
            return EventDetection(
                event_type=EventType.VOLATILITY_SPIKE,
                intensity=intensity,
                timestamp=market.timestamp,
                metadata={"z_score": z_score, "current_vol": current_vol, "avg_vol": vol_mean}
            )
        
        return None
    
    def _detect_price_gap(self, market: MarketData) -> Optional[EventDetection]:
        """Детектує гепи цін"""
        if len(self.price_history) < 2:
            return None
        
        current_price = market.current_price
        previous_price = self.price_history[-1]
        
        if previous_price == 0:
            return None
        
        gap_ratio = abs(current_price - previous_price) / previous_price
        threshold = self.thresholds.get("price_gap_threshold", 0.005)
        
        if gap_ratio > threshold:
            intensity = min(gap_ratio / threshold, 1.0)
            return EventDetection(
                event_type=EventType.PRICE_GAP,
                intensity=intensity,
                timestamp=market.timestamp,
                metadata={"gap_ratio": gap_ratio, "current_price": current_price, "previous_price": previous_price}
            )
        
        return None
    
    def _detect_volume_surge(self, market: MarketData) -> Optional[EventDetection]:
        """Детектує сплески обсягу"""
        if len(self.volume_history) < 10:
            return None
        
        current_volume = market.current_volume
        if current_volume == 0.0:
            return None
        
        recent_volumes = np.array(self.volume_history[-10:])
        avg_volume = np.mean(recent_volumes)
        
        if avg_volume == 0:
            return None
        
        volume_ratio = current_volume / avg_volume
        threshold = self.thresholds.get("volume_surge_threshold", 3.0)
        
        if volume_ratio > threshold:
            intensity = min((volume_ratio - 1.0) / threshold, 1.0)
            return EventDetection(
                event_type=EventType.VOLUME_SURGE,
                intensity=intensity,
                timestamp=market.timestamp,
                metadata={"volume_ratio": volume_ratio, "current_volume": current_volume, "avg_volume": avg_volume}
            )
        
        return None
    
    def _detect_liquidity_shortage(self, market: MarketData) -> Optional[EventDetection]:
        """Детектує нестачу ліквідності"""
        # Используем bid_ask_spread напрямую
        spread = market.bid_ask_spread
        current_price = market.current_price
        
        if spread == 0 or current_price == 0:
            return None
        
        # Спред як індикатор ліквідності відносно ціни
        spread_ratio = spread / current_price
        
        # Порогове значення для нестачі ліквідності
        threshold = self.thresholds.get("liquidity_ratio_threshold", 0.01)  # 1%
        
        if spread_ratio > threshold:
            intensity = min(spread_ratio / threshold, 1.0)
            return EventDetection(
                event_type=EventType.LIQUIDITY_SHORTAGE,
                intensity=intensity,
                timestamp=market.timestamp,
                metadata={"spread_ratio": spread_ratio, "spread": spread, "price": current_price}
            )
        
        return None
    
    def _update_market_history(self, market: MarketData):
        """Оновлює історію ринкових даних"""
        # Волатільність
        volatility = market.current_volatility
        if volatility > 0:
            self.volatility_history.append(volatility)
            if len(self.volatility_history) > 100:
                self.volatility_history.pop(0)
        
        # Обсяг
        volume = market.current_volume
        if volume > 0:
            self.volume_history.append(volume)
            if len(self.volume_history) > 100:
                self.volume_history.pop(0)
        
        # Ціна
        price = market.current_price
        if price > 0:
            self.price_history.append(price)
            if len(self.price_history) > 100:
                self.price_history.pop(0)
    
    def _get_event_coefficient(self, event_type: EventType) -> float:
        """Отримує коефіцієнт для типу події"""
        if event_type.value in ["volatility_spike", "price_gap", "volume_surge", "liquidity_shortage"]:
            return self.market_coeffs.get(event_type.value, 0.0)
        elif event_type.value in ["large_order_fill", "partial_fill", "order_rejection", "excessive_slippage"]:
            return self.trading_coeffs.get(event_type.value, 0.0)
        elif event_type.value in ["regime_change", "signal_divergence", "model_uncertainty", "arce_alert"]:
            return self.system_coeffs.get(event_type.value, 0.0)
        else:
            return 0.0
    
    def _calculate_decay_effects(self) -> float:
        """Розраховує згасаючі ефекти попередніх подій"""
        decay_reward = 0.0
        
        for i, event in enumerate(self.event_history):
            # Розраховуємо фактор згасання на основі віку події
            age = len(self.event_history) - i
            decay = self.decay_factor ** age
            
            # Додаємо згасаючий вплив
            coeff = self._get_event_coefficient(event.event_type)
            event_contribution = coeff * event.intensity * decay * 0.1  # 10% від оригіналу
            decay_reward += event_contribution
        
        return decay_reward
    
    def _cleanup_history(self):
        """Очищає стару історію подій"""
        if len(self.event_history) > self.max_history_size:
            # Залишаємо тільки останні події
            self.event_history = self.event_history[-self.max_history_size:]
    
    def get_component_info(self) -> Dict[str, Any]:
        """Повертає інформацію про компоненту"""
        return {
            "name": "EventRewardComponent",
            "description": "Винагорода за важливі ринкові, торгові та системні події",
            "formula": "R_Event,t = Σ δ_e × I_e,t",
            "parameters": {
                "market_coefficients": self.market_coeffs,
                "trading_coefficients": self.trading_coeffs,
                "system_coefficients": self.system_coeffs,
                "detection_thresholds": self.thresholds,
                "impact_limits": self.impact_limits
            },
            "current_state": {
                "events_in_history": len(self.event_history),
                "volatility_samples": len(self.volatility_history),
                "volume_samples": len(self.volume_history),
                "price_samples": len(self.price_history)
            }
        }

    def reset(self) -> None:
        """Скидання внутрішнього стану компоненту подій."""
        try:
            self.event_history.clear()
            self.volatility_history.clear()
            self.volume_history.clear()
            self.price_history.clear()
        except Exception:
            # Безпечний no-op
            pass
