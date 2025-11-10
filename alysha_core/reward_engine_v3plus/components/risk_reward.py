"""
Risk Reward Component для ALYSHA-RE-V3+ з адаптивним штрафом
==============================================================

Цей компонент інтегрує оцінку ризиків від RiskManager у винагороду, 
впроваджуючи адаптивний механізм штрафів, що реагує на частоту порушень.
"""

from core.logging.unified_logger import get_logger
import math
import time
from typing import Dict, Any, Optional, Deque, Tuple
from collections import deque
import numpy as np

from ..data_types import StateData, RewardComponentResult, ConfigDict
from ..utils import validate_numeric_value, RewardEngineConfig
from .base import BaseRewardComponent
from core.risk.risk_manager import RiskManager



class RiskRewardComponent(BaseRewardComponent):
    """
    Компонента винагороди за ризики з адаптивним штрафом.
    """
    
    def __init__(self, config: RewardEngineConfig, risk_manager: Optional[RiskManager] = None):
        from typing import cast
        super().__init__(cast(Dict[str, Any], config))
        self.logger = get_logger(self.__class__.__name__)
        
        self.risk_manager = risk_manager
        if self.risk_manager is None:
            self.logger.warning("🚨 RiskManager not provided - risk penalties will be calculated with fallback logic")
        
        risk_reward_config = config.get_component_config("risk_reward")
        if not risk_reward_config:
            raise ValueError("alysha_reward_engine.components.risk_reward not found in configuration")
        
        self.base_penalty = float(risk_reward_config.get("base_penalty", 0.1))
        self.critical_multiplier = float(risk_reward_config.get("critical_multiplier", 3.0))
        self.moderate_multiplier = float(risk_reward_config.get("moderate_multiplier", 1.5))
        
        penalty_function_config = risk_reward_config.get("penalty_function", {})
        self.penalty_function_type = penalty_function_config.get("type", "quadratic")
        self.penalty_steepness = float(penalty_function_config.get("steepness", 2.0))
        
        # --- NEW: Adaptive Penalty Attributes ---
        adaptive_config = risk_reward_config.get("adaptive_penalty", {})
        self.adaptive_penalty_enabled = adaptive_config.get("enabled", True)
        self.violation_window_seconds = adaptive_config.get("violation_window_seconds", 3600) # 1 година
        self.penalty_increase_factor = adaptive_config.get("penalty_increase_factor", 1.2)
        self.penalty_decay_factor = adaptive_config.get("penalty_decay_factor", 0.995)
        self.max_adaptive_multiplier = adaptive_config.get("max_adaptive_multiplier", 5.0)
        self.min_adaptive_multiplier = 1.0
        
        self.violation_history: Deque[float] = deque(maxlen=100) # Зберігаємо timestamp порушень
        self.adaptive_penalty_multiplier = self.min_adaptive_multiplier
        
        self.enabled = config.is_component_enabled("risk_reward")
        
        self.logger.info(f"🛡️ RiskRewardComponent initialized - Adaptive Penalty: {self.adaptive_penalty_enabled}")
        
    def calculate_reward(self, state: StateData) -> RewardComponentResult:
        try:
            if not self.enabled:
                return RewardComponentResult(component_name="risk_reward", raw_value=0.0, metadata={"status": "disabled"})
            
            market_state = self._prepare_market_state_for_risk_manager(state)
            
            risk_score, risk_flags, risk_components = self._get_risk_assessment(market_state)

            # --- NEW: Update violation history ---
            if any(flag in risk_flags for flag in ['circuit_breaker_active', 'adaptive_high_drawdown']):
                try:
                    ts = float(getattr(state, 'timestamp', time.time()))
                except Exception:
                    ts = time.time()
                self.violation_history.append(ts)

            # --- NEW: Update adaptive multiplier ---
            self._update_adaptive_multiplier()

            penalty = self._convert_risk_to_penalty(risk_score, risk_flags)
            penalty = validate_numeric_value(penalty, "risk_penalty", allow_nan=False, allow_inf=False)
            penalty = min(penalty, 0.0)
            
            metadata = self._build_metadata(risk_score, risk_flags, risk_components, penalty)
            
            return RewardComponentResult(component_name="risk_reward", raw_value=penalty, metadata=metadata)
            
        except Exception as e:
            self.logger.error(f"🚨 Risk reward calculation failed: {e}", exc_info=True)
            return RewardComponentResult(component_name="risk_reward", raw_value=-self.base_penalty, metadata={"error": str(e)})

    def _get_risk_assessment(self, market_state: Dict[str, Any]) -> Tuple[float, list, dict]:
        """Отримує оцінку ризику від RiskManager або використовує fallback."""
        if self.risk_manager:
            try:
                assessment = self.risk_manager.assess(market_state)
                return (
                    assessment.get('risk_score', 0.3),
                    assessment.get('risk_flags', []),
                    assessment.get('risk_components', {})
                )
            except Exception as e:
                self.logger.error(f"🚨 RiskManager.assess() failed: {e}")
                return 0.3, ["risk_manager_error"], {"error": str(e)}
        else:
            return 0.3, ["no_risk_manager"], {"method": "fallback"}

    def _update_adaptive_multiplier(self, current_timestamp: Optional[float] = None):
        """Оновлює адаптивний множник штрафу на основі історії порушень."""
        if not self.adaptive_penalty_enabled:
            self.adaptive_penalty_multiplier = 1.0
            return

        now = float(current_timestamp if current_timestamp is not None else time.time())
        # Видаляємо старі порушення
        while self.violation_history and self.violation_history[0] < now - self.violation_window_seconds:
            self.violation_history.popleft()

        recent_violations = len(self.violation_history)

        if recent_violations > 2: # Якщо було більше 2 порушень за останню годину
            # Збільшуємо множник
            self.adaptive_penalty_multiplier *= self.penalty_increase_factor
        else:
            # Зменшуємо множник (повертаємо до норми)
            self.adaptive_penalty_multiplier *= self.penalty_decay_factor
        
        # Обмежуємо множник
        self.adaptive_penalty_multiplier = max(
            self.min_adaptive_multiplier, 
            min(self.adaptive_penalty_multiplier, self.max_adaptive_multiplier)
        )

    def _convert_risk_to_penalty(self, risk_score: float, risk_flags: list) -> float:
        risk_score = max(0.0, min(1.0, float(risk_score)))
        
        flag_multiplier = 1.0
        critical_flags = ['adaptive_high_volatility', 'adaptive_high_drawdown', 'circuit_breaker_active']
        if any(flag in risk_flags for flag in critical_flags):
            flag_multiplier = self.critical_multiplier

        if self.penalty_function_type == "quadratic":
            penalty_factor = math.pow(risk_score, self.penalty_steepness)
        else: # linear fallback
            penalty_factor = risk_score
        
        # Застосовуємо адаптивний множник
        penalty = -self.base_penalty * penalty_factor * flag_multiplier * self.adaptive_penalty_multiplier
        
        # Обмежуємо максимальний штраф
        max_penalty = -self.base_penalty * self.max_adaptive_multiplier * self.critical_multiplier
        return max(penalty, max_penalty)

    def _build_metadata(self, risk_score: float, risk_flags: list, risk_components: dict, penalty: float) -> Dict[str, Any]:
        """Створює метадані для результату."""
        return {
            "risk_score": float(risk_score),
            "risk_flags": risk_flags,
            "risk_components": risk_components,
            "penalty_function": self.penalty_function_type,
            "risk_manager_connected": self.risk_manager is not None,
            "penalty_breakdown": {
                "base_penalty": self.base_penalty,
                "calculated_penalty": penalty,
                "adaptive_multiplier": self.adaptive_penalty_multiplier
            }
        }

    def _prepare_market_state_for_risk_manager(self, state: StateData) -> Dict[str, Any]:
        """Готує market_state для RiskManager з повними kline даними."""
        market_state = {}
        if state.market_data:
            market_state['symbol'] = getattr(state.market_data, 'symbol', 'BTCUSDT')
            market_state['current_price'] = float(getattr(state.market_data, 'current_price', 50000.0))
            market_state['volatility'] = float(getattr(state.market_data, 'current_volatility', 0.02))
            
            # CRITICAL FIX: Add current_kline data for RiskManager volatility calculation
            market_state['current_kline'] = {
                'close': float(getattr(state.market_data, 'current_price', 50000.0)),
                'open': float(getattr(state.market_data, 'open_price', 50000.0)),
                'high': float(getattr(state.market_data, 'high_price', 50000.0)),
                'low': float(getattr(state.market_data, 'low_price', 50000.0)),
                'volume': float(getattr(state.market_data, 'current_volume', 1000.0)),
                'timestamp': float(getattr(state, 'timestamp', 0))
            }
        return market_state