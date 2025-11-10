"""
Shaping Reward Component для ALYSHA-RE-V3+

Реалізує компоненту формуючої винагороди R_Shaping,t за формулою:
R_Shaping,t = Σ κ_i × [Φ_i(S_{t+1}) - γ × Φ_i(S_t)]

де:
- κ_i - коефіцієнт i-ї потенціальної функції
- Φ_i(S_t) - i-та потенціальна функція стану
- γ - дисконт-фактор

Потенціальні функції включають:
- Φ_1(S_t) - узгодженість портфеля з цільовими значеннями
- Φ_2(S_t) - близькість до ризикових меж  
- Φ_3(S_t) - прогрес навчання
- Φ_4(S_t) - якість дій
"""

import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod

from ..data_types import (
    StateData, RewardComponentResult, MarketData, PortfolioData, 
    ARCEData, ExecutionData, AgentActionData
)
from ..utils import RewardEngineConfig
from .base import BaseRewardComponent


@dataclass
class PotentialState:
    """Стан потенціальної функції"""
    value: float
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


class PotentialFunction(ABC):
    """Базовий клас для потенціальних функцій"""
    
    @abstractmethod
    def calculate(self, state_data: StateData) -> float:
        """Розраховує значення потенціальної функції"""
        pass
    
    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Повертає інформацію про функцію"""
        pass


class PortfolioAlignmentPotential(PotentialFunction):
    """Φ_1(S_t) - узгодженість портфеля з цільовими значеннями"""
    
    def __init__(self, config: Dict[str, Any]):
        self.target_balance_ratio = config.get("target_balance_ratio", 0.5)
        self.position_size_target = config.get("position_size_target", 0.1)
        self.diversification_target = config.get("diversification_target", 0.3)
        
        # Винесення hardcode-значень в конфігурацію
        self.balance_penalty_multiplier = config.get("balance_penalty_multiplier", 2.0)
        self.position_penalty_multiplier = config.get("position_penalty_multiplier", 5.0)
        
        # Ваги для компонентів score
        self.balance_score_weight = config.get("balance_score_weight", 0.5)
        self.position_score_weight = config.get("position_score_weight", 0.5)

    def calculate(self, state_data: StateData) -> float:
        """Розраховує узгодженість портфеля"""
        if not state_data.portfolio or not hasattr(state_data.portfolio, 'total_value') or state_data.portfolio.total_value <= 0:
            return 0.0
        
        portfolio = state_data.portfolio
        
        # Узгодженість балансу позицій
        balance_score = 0.0
        # Примітка: Замінено cash_balance на available_balance згідно з контрактом даних.
        available_balance = getattr(portfolio, 'available_balance', None)
        total_value = getattr(portfolio, 'total_value', 0)
        if available_balance is not None and total_value > 0:
            cash_ratio = available_balance / total_value
            balance_deviation = abs(cash_ratio - self.target_balance_ratio)
            balance_score = max(0.0, 1.0 - balance_deviation * self.balance_penalty_multiplier)
        
        # Узгодженість розміру позиції
        position_score = 0.0
        if portfolio.positions and portfolio.total_value > 0:
            # Використовуємо суму абсолютних значень позицій
            total_position_value = sum(abs(size) for size in portfolio.positions.values())
            position_ratio = total_position_value / portfolio.total_value
            position_deviation = abs(position_ratio - self.position_size_target)
            position_score = max(0.0, 1.0 - position_deviation * self.position_penalty_multiplier)
        
        # Зважене середнє всіх компонентів
        total_score = (self.balance_score_weight * balance_score + 
                       self.position_score_weight * position_score)
        
        return total_score
    
    def get_info(self) -> Dict[str, Any]:
        return {
            "name": "PortfolioAlignmentPotential",
            "description": "Узгодженість портфеля з цільовими значеннями",
            "parameters": {
                "target_balance_ratio": self.target_balance_ratio,
                "position_size_target": self.position_size_target,
                "diversification_target": self.diversification_target
            }
        }


class RiskProximityPotential(PotentialFunction):
    """Φ_2(S_t) - близькість до ризикових меж"""
    
    def __init__(self, config: Dict[str, Any]):
        self.safety_margin = config.get("safety_margin", 0.2)
        self.risk_escalation_penalty = config.get("risk_escalation_penalty", 2.0)
    
    def calculate(self, state_data: StateData) -> float:
        """Розраховує близькість до ризикових меж"""
        if not state_data.arce:
            return 0.0
        
        arce = state_data.arce
        risk_proximities = []
        
        # VaR близькість
        if hasattr(arce, 'var_current') and hasattr(arce, 'var_limit'):
            if arce.var_limit > 0:
                var_ratio = arce.var_current / arce.var_limit
                if var_ratio > (1.0 - self.safety_margin):
                    proximity = (var_ratio - (1.0 - self.safety_margin)) / self.safety_margin
                    risk_proximities.append(proximity)
        
        # CVaR близькість
        if hasattr(arce, 'cvar_current') and hasattr(arce, 'cvar_limit'):
            if arce.cvar_limit > 0:
                cvar_ratio = arce.cvar_current / arce.cvar_limit
                if cvar_ratio > (1.0 - self.safety_margin):
                    proximity = (cvar_ratio - (1.0 - self.safety_margin)) / self.safety_margin
                    risk_proximities.append(proximity)
        
        # Drawdown близькість
        if hasattr(arce, 'drawdown_current') and hasattr(arce, 'drawdown_limit'):
            if arce.drawdown_limit > 0:
                dd_ratio = arce.drawdown_current / arce.drawdown_limit
                if dd_ratio > (1.0 - self.safety_margin):
                    proximity = (dd_ratio - (1.0 - self.safety_margin)) / self.safety_margin
                    risk_proximities.append(proximity)
        
        # Волатильність
        if hasattr(arce, 'portfolio_volatility') and hasattr(arce, 'target_volatility'):
            if arce.target_volatility > 0:
                vol_ratio = arce.portfolio_volatility / arce.target_volatility
                if vol_ratio > (1.0 + self.safety_margin):
                    proximity = (vol_ratio - (1.0 + self.safety_margin)) / self.safety_margin
                    risk_proximities.append(proximity)
        
        if not risk_proximities:
            return 1.0  # Немає ризикових меж поблизу - максимальний score
        
        # Негативний score пропорційний до найближчої межі
        max_proximity = max(risk_proximities)
        return max(0.0, 1.0 - max_proximity * self.risk_escalation_penalty)
    
    def get_info(self) -> Dict[str, Any]:
        return {
            "name": "RiskProximityPotential",
            "description": "Близькість до ризикових меж (негативна винагорода при наближенні)",
            "parameters": {
                "safety_margin": self.safety_margin,
                "risk_escalation_penalty": self.risk_escalation_penalty
            }
        }


class LearningProgressPotential(PotentialFunction):
    """Φ_3(S_t) - прогрес навчання"""
    
    def __init__(self, config: Dict[str, Any]):
        self.exploration_bonus = config.get("exploration_bonus", 0.1)
        self.convergence_penalty = config.get("convergence_penalty", -0.05)
        self.novelty_threshold = config.get("novelty_threshold", 0.8)
        
        # Історія дій для відстеження новизни
        self.action_history: List[np.ndarray] = []
        self.max_history_size = 100
    
    def calculate(self, state_data: StateData) -> float:
        """Розраховує прогрес навчання"""
        if not state_data.agent_action:
            return 0.0
        
        action = state_data.agent_action
        score = 0.0
        
        # Бонус за дослідницькі дії
        if hasattr(action, 'is_exploratory') and action.is_exploratory:
            score += self.exploration_bonus
        
        # Бонус за новизну дій
        if hasattr(action, 'action_vector'):
            novelty = self._calculate_action_novelty(action.action_vector)
            if novelty > self.novelty_threshold:
                score += self.exploration_bonus * novelty
        
        # Штраф за занадто швидку конвергенцію
        if len(self.action_history) > 20:
            recent_variance = self._calculate_recent_action_variance()
            if recent_variance < 0.1:  # Дуже мала варіація
                score += self.convergence_penalty
        
        # Оновлюємо історію дій
        if hasattr(action, 'action_vector'):
            self._update_action_history(action.action_vector)
        
        return max(0.0, score)  # Обмежуємо знизу нулем
    
    def _calculate_action_novelty(self, action_vector: np.ndarray) -> float:
        """Розраховує новизну дії"""
        if len(self.action_history) < 5:
            return 1.0  # Перші дії завжди нові
        
        # Порівнюємо з останніми діями
        recent_actions = np.array(self.action_history[-10:])
        
        # Розраховуємо мінімальну відстань до попередніх дій
        distances = []
        for hist_action in recent_actions:
            if len(hist_action) == len(action_vector):
                distance = np.linalg.norm(action_vector - hist_action)
                distances.append(distance)
        
        if not distances:
            return 1.0
        
        min_distance = min(distances)
        # Нормалізуємо відстань до [0, 1]
        max_possible_distance = np.sqrt(2 * len(action_vector))  # Для normalized vectors
        novelty = min(min_distance / max_possible_distance, 1.0)
        
        return novelty
    
    def _calculate_recent_action_variance(self) -> float:
        """Розраховує варіацію останніх дій"""
        if len(self.action_history) < 10:
            return 1.0
        
        recent_actions = np.array(self.action_history[-20:])
        return float(np.var(recent_actions))
    
    def _update_action_history(self, action_vector: np.ndarray):
        """Оновлює історію дій"""
        self.action_history.append(action_vector.copy())
        if len(self.action_history) > self.max_history_size:
            self.action_history.pop(0)
    
    def get_info(self) -> Dict[str, Any]:
        return {
            "name": "LearningProgressPotential",
            "description": "Прогрес навчання (дослідження vs експлуатація)",
            "parameters": {
                "exploration_bonus": self.exploration_bonus,
                "convergence_penalty": self.convergence_penalty,
                "novelty_threshold": self.novelty_threshold
            },
            "state": {
                "actions_in_history": len(self.action_history)
            }
        }


class ActionQualityPotential(PotentialFunction):
    """Φ_4(S_t) - якість дій"""
    
    def __init__(self, config: Dict[str, Any]):
        self.confidence_threshold = config.get("confidence_threshold", 0.7)
        self.decisiveness_bonus = config.get("decisiveness_bonus", 0.2)
        self.hesitation_penalty = config.get("hesitation_penalty", -0.1)
    
    def calculate(self, state_data: StateData) -> float:
        """Розраховує якість дій"""
        if not state_data.agent_action:
            return 0.0
        
        action = state_data.agent_action
        score = 0.0
        
        # Бонус за впевненість
        # Примітка: AgentActionData не має 'confidence'. Ця логіка може потребувати перегляду.
        confidence = getattr(action, 'confidence', None)
        if confidence is not None:
            if confidence > self.confidence_threshold:
                confidence_bonus = (confidence - self.confidence_threshold) / (1.0 - self.confidence_threshold)
                score += confidence_bonus * self.decisiveness_bonus
            else:
                # Штраф за невпевненість
                uncertainty = (self.confidence_threshold - confidence) / self.confidence_threshold
                score += uncertainty * self.hesitation_penalty
        
        # Оцінка рішучості дії
        action_vector = getattr(action, 'action_vector', None)
        if action_vector is not None:
            action_magnitude = np.linalg.norm(action_vector)
            if action_magnitude > 0.8:  # Рішуча дія
                score += self.decisiveness_bonus
            elif action_magnitude < 0.2:  # Нерішуча дія
                score += self.hesitation_penalty * 0.5
        
        return score
    
    def get_info(self) -> Dict[str, Any]:
        return {
            "name": "ActionQualityPotential",
            "description": "Якість дій (впевненість та рішучість)",
            "parameters": {
                "confidence_threshold": self.confidence_threshold,
                "decisiveness_bonus": self.decisiveness_bonus,
                "hesitation_penalty": self.hesitation_penalty
            }
        }


class ShapingRewardComponent(BaseRewardComponent):
    """
    Shaping Reward Component - формуюча винагорода для покращення навчання.
    
    Використовує потенціальні функції для надання проміжних винагород,
    які допомагають агенту навчатися ефективніше без зміни оптимальної політики.
    """
    
    def __init__(self, config: RewardEngineConfig):
        super().__init__(config.get_component_config("shaping"))
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Отримуємо конфігурацію для компоненти формування
        shaping_config = config.get_component_config("shaping")
        
        # Дисконт-фактор
        self.gamma = shaping_config.get("gamma", 0.99)
        
        # Коефіцієнти потенціальних функцій
        self.coefficients = shaping_config.get("potential_coefficients", {})
        
        # Конфігурації функцій
        function_configs = shaping_config.get("potential_functions", {})
        
        # Ініціалізуємо потенціальні функції
        self.potential_functions: Dict[str, PotentialFunction] = {}
        
        if function_configs.get("portfolio_alignment", {}).get("enabled", False):
            self.potential_functions["portfolio_alignment"] = PortfolioAlignmentPotential(
                function_configs["portfolio_alignment"]
            )
        
        if function_configs.get("risk_proximity", {}).get("enabled", False):
            self.potential_functions["risk_proximity"] = RiskProximityPotential(
                function_configs["risk_proximity"]
            )
        
        if function_configs.get("learning_progress", {}).get("enabled", False):
            self.potential_functions["learning_progress"] = LearningProgressPotential(
                function_configs["learning_progress"]
            )
        
        if function_configs.get("action_quality", {}).get("enabled", False):
            self.potential_functions["action_quality"] = ActionQualityPotential(
                function_configs["action_quality"]
            )
        
        # Історія станів потенціальних функцій
        self.previous_potentials: Dict[str, float] = {}
        
        self.logger.info(f"ShapingRewardComponent ініціалізовано з {len(self.potential_functions)} "
                        f"потенціальними функціями: {list(self.potential_functions.keys())}")
    
    def calculate_reward(self, state: StateData) -> RewardComponentResult:
        """
        Основний метод для розрахунку винагороди Shaping компонента
        
        Args:
            state: Поточні дані стану
            
        Returns:
            RewardComponentResult з винагородою та метаданими
        """
        return self.calculate(state)
    
    def calculate(self, state_data: StateData) -> RewardComponentResult:
        """
        Розраховує формуючу винагороду
        
        Args:
            state_data: Поточні дані стану
            
        Returns:
            RewardComponentResult з деталями формуючої винагороди
        """
        try:
            current_potentials = {}
            shaping_rewards = {}
            total_shaping_reward = 0.0
            
            # Розраховуємо поточні значення всіх потенціальних функцій
            for name, func in self.potential_functions.items():
                current_value = func.calculate(state_data)
                current_potentials[name] = current_value
                
                # Розраховуємо формуючу винагороду для цієї функції
                if name in self.previous_potentials:
                    # R_shaping = κ × [Φ(s') - γ × Φ(s)]
                    previous_value = self.previous_potentials[name]
                    coefficient = self.coefficients.get(name, 1.0)
                    
                    shaping_reward = coefficient * (current_value - self.gamma * previous_value)
                    shaping_rewards[name] = {
                        "coefficient": coefficient,
                        "current_potential": current_value,
                        "previous_potential": previous_value,
                        "difference": current_value - previous_value,
                        "shaping_reward": shaping_reward
                    }
                    
                    total_shaping_reward += shaping_reward
                    
                    self.logger.debug(f"Потенціал {name}: {previous_value:.3f} -> {current_value:.3f}, "
                                    f"формуюча винагорода: {shaping_reward:.4f}")
                else:
                    # Перший розрахунок - немає попереднього стану
                    shaping_rewards[name] = {
                        "coefficient": self.coefficients.get(name, 1.0),
                        "current_potential": current_value,
                        "previous_potential": None,
                        "difference": 0.0,
                        "shaping_reward": 0.0
                    }
            
            # Оновлюємо історію
            self.previous_potentials = current_potentials.copy()
            
            self.logger.debug(f"Загальна формуюча винагорода: {total_shaping_reward:.4f}")
            
            return RewardComponentResult(
                component_name="shaping",
                raw_value=total_shaping_reward,
                subcomponents=shaping_rewards,
                metadata={
                    "gamma": self.gamma,
                    "active_functions": len(self.potential_functions),
                    "current_potentials": current_potentials
                }
            )
            
        except Exception as e:
            self.logger.error(f"Помилка розрахунку Shaping винагороди: {e}")
            return RewardComponentResult(
                component_name="shaping",
                raw_value=0.0,
                subcomponents={"error": 0.0},
                metadata={"error": True, "error_message": str(e)}
            )
    
    def get_component_info(self) -> Dict[str, Any]:
        """Повертає інформацію про компоненту"""
        function_info = {}
        for name, func in self.potential_functions.items():
            function_info[name] = func.get_info()
        
        return {
            "name": "ShapingRewardComponent",
            "description": "Формуюча винагорода для покращення навчання через потенціальні функції",
            "formula": "R_Shaping,t = Σ κ_i × [Φ_i(S_{t+1}) - γ × Φ_i(S_t)]",
            "parameters": {
                "gamma": self.gamma,
                "coefficients": self.coefficients
            },
            "potential_functions": function_info,
            "current_state": {
                "previous_potentials": self.previous_potentials
            }
        }

    def reset(self) -> None:
        """Скидання внутрішнього стану Shaping компоненту."""
        try:
            self.previous_potentials.clear()
            # Якщо потенціальні функції мають власний стан — на майбутнє:
            # for func in self.potential_functions.values():
            #     if hasattr(func, 'reset'):
            #         func.reset()
        except Exception:
            pass
