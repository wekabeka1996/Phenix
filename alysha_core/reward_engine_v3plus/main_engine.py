"""
Головний двигун ALYSHA-RE-V3+ Reward Engine

Основний клас RewardEngineV3Plus, який оркеструє всі компоненти винагороди,
нормалізацію, адаптивні ваги та розрахунок фінальної винагороди.

Формула загальної винагороди:
R_t = Σ ω_i(S_t, Θ_t) * R̃_i,t(S_t, A_t) + R̃_Event,t(S_t) + R̃_Shaping,t(S_t, S_t+1)

де R̃_i,t - нормалізовані компоненти винагороди
"""

import logging
import time
from typing import Dict, Optional, Any
import numpy as np

from .data_types import (
    StateData, AgentActionData, ExecutionData, ModelPredictionData,
    ActiveEventsData, TotalRewardResult, RewardComponentResult, MarketRegime
)
from .utils import RewardEngineConfig, format_reward_breakdown, clip_reward
from .adaptive_weights_manager import AdaptiveWeightsManager
from .normalizers import NormalizationManager


class RewardEngineV3Plus:
    """
    Головний клас системи винагород ALYSHA-RE-V3+
    
    Оркеструє всі компоненти винагороди та здійснює фінальну агрегацію
    згідно з математичними формулами з роадмапу.
    """
    
    def __init__(self, config: RewardEngineConfig):
        """
        Ініціалізація reward engine
        
        Args:
            config: Конфігурація reward engine
        """
        self.config = config
        self.logger = logging.getLogger("alysha_reward_engine.main")
        
        # Ініціалізація менеджера адаптивних ваг
        self.adaptive_weights_manager = AdaptiveWeightsManager(config)
        
        # Словник для зберігання компонент (будуть додані при ініціалізації)
        self.components = {}
        self.normalizers = {}
        # Централізований менеджер нормалізації
        self.normalization_manager = NormalizationManager(config)
        
        # ВИДАЛЕНО ВСІ HARDCODE ЗНАЧЕННЯ!
        # Тепер все читається з master_config.yaml
        validation_config = config.get_validation_config()
        
        self.max_reward = validation_config.get("max_total_reward")
        self.min_reward = validation_config.get("min_total_reward")
        self.safe_reward = validation_config.get("default_safe_reward")
        self.check_nan_inf = validation_config.get("check_nan_inf")
        
        # КРИТИЧНА ВАЛІДАЦІЯ: обов'язкові параметри
        if self.max_reward is None:
            raise ValueError("alysha_reward_engine.validation.max_total_reward not found in configuration")
        if self.min_reward is None:
            raise ValueError("alysha_reward_engine.validation.min_total_reward not found in configuration")
        if self.safe_reward is None:
            raise ValueError("alysha_reward_engine.validation.default_safe_reward not found in configuration")
        
        # Налаштування логування з конфігурації
        logging_config = config.get_logging_config()
        self.detailed_logging = logging_config.get("log_individual_components", True)
        
        self.logger.info("RewardEngineV3Plus initialized with centralized configuration")
        
    def add_component(self, name: str, component: Any) -> None:
        """
        Додавання компоненти винагороди
        
        Args:
            name: Назва компоненти
            component: Об'єкт компоненти з методом calculate()
        """
        self.components[name] = component
        self.logger.debug(f"Added component: {name}")
        
    def add_normalizer(self, component_name: str, normalizer: Any) -> None:
        """
        Додавання нормалізатора для компоненти
        
        Args:
            component_name: Назва компоненти
            normalizer: Об'єкт нормалізатора з методом normalize()
        """
        self.normalizers[component_name] = normalizer
        self.logger.debug(f"Added normalizer for: {component_name}")
        
    def calculate_total_reward(self,
                              state_t: StateData,
                              action_t: Optional[AgentActionData] = None,
                              state_t_plus_1: Optional[StateData] = None,
                              execution_data: Optional[ExecutionData] = None,
                              model_prediction_data: Optional[ModelPredictionData] = None,
                              active_events_data: Optional[ActiveEventsData] = None) -> TotalRewardResult:
        """
        Розрахунок загальної винагороди
        
        Args:
            state_t: Поточний стан в момент t
            action_t: Дія агента в момент t
            state_t_plus_1: Наступний стан в момент t+1 (для shaping)
            execution_data: Дані виконання угод
            model_prediction_data: Дані прогнозів моделі
            active_events_data: Активні події
            
        Returns:
            Результат розрахунку загальної винагороди
        """
        start_time = time.time()
        
        try:
            # 1. Розрахунок компонент винагороди
            component_rewards = self._calculate_components(
                state_t, action_t, execution_data, model_prediction_data
            )
            
            # 2. Нормалізація компонент (з урахуванням timestamp)
            normalized_rewards = self._normalize_components(component_rewards, timestamp=state_t.timestamp)
            
            # 3. Отримання адаптивних ваг
            adaptive_weights = self.adaptive_weights_manager.get_weights(state_t.arce)
            
            # 4. Розрахунок основної винагороди (зважена сума основних компонент)
            main_reward = self._calculate_weighted_sum(normalized_rewards, adaptive_weights)
            
            # 5. Додавання подієвих компонент
            event_reward = self._calculate_event_reward(active_events_data)
            
            # 6. Додавання shaping reward
            shaping_reward = self._calculate_shaping_reward(state_t, state_t_plus_1)
            
            # 7. Фінальна винагорода
            total_reward = main_reward + event_reward + shaping_reward
            
            # 8. Валідація та обмеження
            total_reward = self._validate_and_clip_reward(total_reward)
            
            # 9. Логування
            if self.detailed_logging:
                self._log_detailed_breakdown(
                    component_rewards, normalized_rewards, adaptive_weights, 
                    main_reward, event_reward, shaping_reward, total_reward
                )
                
            # 10. Створення результату
            result = TotalRewardResult(
                total_reward=total_reward,
                component_rewards=component_rewards,
                adaptive_weights=adaptive_weights,
                normalization_stats=self._get_normalization_stats(),
                timestamp=state_t.timestamp,
                metadata={
                    "calculation_time": time.time() - start_time,
                    "main_reward": main_reward,
                    "event_reward": event_reward, 
                    "shaping_reward": shaping_reward,
                    "regime": state_t.arce.regime_tag.value if state_t.arce else "UNKNOWN"
                }
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку винагороди: {e}")
            # Повертаємо безпечний результат
            return self._create_safe_reward_result(state_t.timestamp, str(e))
            
    def _calculate_components(self, state_t: StateData, 
                            action_t: Optional[AgentActionData],
                            execution_data: Optional[ExecutionData],
                            model_prediction_data: Optional[ModelPredictionData]) -> Dict[str, RewardComponentResult]:
        """Розрахунок всіх компонент винагороди"""
        results = {}
        
        for name, component in self.components.items():
            try:
                if name == "pnl":
                    result = component.calculate(state_t)
                elif name == "risk":
                    # CRITICAL FIX: Correct argument order - arce_data FIRST, then portfolio, then state
                    result = component.calculate(state_t.arce, state_t.portfolio, state_t)
                elif name == "risk_reward":
                    # TASK 5 CRITICAL: New RiskRewardComponent with RiskManager integration
                    result = component.calculate_reward(state_t)
                elif name == "cost":
                    result = component.calculate(execution_data) if execution_data else RewardComponentResult("cost", 0.0)
                elif name == "behavior":
                    # CRITICAL FIX: Correct argument order - arce_data, portfolio_data, state_data
                    result = component.calculate(state_t.arce, state_t.portfolio, state_t)
                elif name == "information":
                    # CRITICAL FIX: Correct argument order - arce_data, portfolio_data, state_data
                    result = component.calculate(state_t.arce, state_t.portfolio, state_t)
                else:
                    # Загальний виклик для інших компонент
                    result = component.calculate(state_t)
                    
                results[name] = result
                
            except Exception as e:
                self.logger.error(f"Помилка в компоненті {name}: {e}")
                safe_reward_value = self.safe_reward if self.safe_reward is not None else 0.0
                results[name] = RewardComponentResult(
                    component_name=name,
                    raw_value=safe_reward_value,
                    metadata={"error": str(e)}
                )
                
        return results
        
    def _normalize_components(self, component_rewards: Dict[str, RewardComponentResult], timestamp: float = 0.0) -> Dict[str, RewardComponentResult]:
        """Нормалізація компонент винагороди"""
        normalized = {}
        
        for name, reward_result in component_rewards.items():
            try:
                # Перевага централізованому менеджеру
                if hasattr(self, 'normalization_manager') and self.normalization_manager:
                    # Copilot: Bugfix — результат нормалізації не зберігався, через що normalized_rewards
                    # залишався порожнім і підсумкова винагорода завжди дорівнювала 0.
                    normalized_value = self.normalization_manager.normalize_component_reward(
                        name, reward_result.raw_value, timestamp
                    )
                    # Створюємо новий об'єкт результату із заповненим normalized_value
                    normalized_result = RewardComponentResult(
                        component_name=reward_result.component_name,
                        raw_value=reward_result.raw_value,
                        normalized_value=normalized_value,
                        subcomponents=reward_result.subcomponents,
                        metadata=reward_result.metadata
                    )
                    normalized[name] = normalized_result
                elif name in self.normalizers:
                    normalizer = self.normalizers[name]
                    # Старий шлях: без timestamp
                    normalized_value = normalizer.normalize(reward_result.raw_value)
                    
                    # Створюємо новий результат з нормалізованим значенням
                    normalized_result = RewardComponentResult(
                        component_name=reward_result.component_name,
                        raw_value=reward_result.raw_value,
                        normalized_value=normalized_value,
                        subcomponents=reward_result.subcomponents,
                        metadata=reward_result.metadata
                    )
                    normalized[name] = normalized_result
                else:
                    # Якщо нормалізатор не знайдений, використовуємо оригінальне значення
                    reward_result.normalized_value = reward_result.raw_value
                    normalized[name] = reward_result
                    
            except Exception as e:
                self.logger.error(f"Помилка нормалізації {name}: {e}")
                reward_result.normalized_value = reward_result.raw_value
                normalized[name] = reward_result
                
        return normalized
        
    def _calculate_weighted_sum(self, normalized_rewards: Dict[str, RewardComponentResult],
                               adaptive_weights: Dict[str, float]) -> float:
        """Розрахунок зваженої суми основних компонент"""
        weighted_sum = 0.0
        
        for component_name, weight in adaptive_weights.items():
            if component_name in normalized_rewards:
                reward_result = normalized_rewards[component_name]
                normalized_value = reward_result.normalized_value or reward_result.raw_value
                weighted_sum += weight * normalized_value
                
        return weighted_sum
        
    def _calculate_event_reward(self, active_events_data: Optional[ActiveEventsData]) -> float:
        """Розрахунок винагороди від подій"""
        if not active_events_data or not active_events_data.events:
            return 0.0
            
        # Використовуємо компоненту подій, якщо вона є
        if "event" in self.components:
            try:
                result = self.components["event"].calculate(active_events_data)
                return result.raw_value
            except Exception as e:
                self.logger.error(f"Помилка в компоненті подій: {e}")
                return 0.0
        else:
            # Простий розрахунок без компоненти
            return sum(event.impact_value for event in active_events_data.events)
            
    def _calculate_shaping_reward(self, state_t: StateData, 
                                 state_t_plus_1: Optional[StateData]) -> float:
        """Розрахунок shaping reward"""
        if not state_t_plus_1 or "shaping" not in self.components:
            return 0.0
            
        try:
            result = self.components["shaping"].calculate(state_t, state_t_plus_1)
            return result.raw_value
        except Exception as e:
            self.logger.error(f"Помилка в shaping компоненті: {e}")
            return 0.0
            
    def _validate_and_clip_reward(self, reward: float) -> float:
        """Валідація та обмеження винагороди"""
        if self.check_nan_inf:
            if np.isnan(reward) or np.isinf(reward):
                self.logger.warning(f"Некоректна винагорода (NaN/Inf): {reward}, використовується безпечне значення")
                return self.safe_reward if self.safe_reward is not None else 0.0
        
        min_r = self.min_reward if self.min_reward is not None else -float('inf')
        max_r = self.max_reward if self.max_reward is not None else float('inf')
        return clip_reward(reward, min_r, max_r)
        
    def _log_detailed_breakdown(self, component_rewards: Dict[str, RewardComponentResult],
                               normalized_rewards: Dict[str, RewardComponentResult],
                               adaptive_weights: Dict[str, float],
                               main_reward: float, event_reward: float, 
                               shaping_reward: float, total_reward: float) -> None:
        """Детальне логування розкладу винагороди"""
        
        raw_values = {name: result.raw_value for name, result in component_rewards.items()}
        norm_values = {name: result.normalized_value or result.raw_value 
                      for name, result in normalized_rewards.items()}
        
        breakdown = format_reward_breakdown(norm_values, adaptive_weights, main_reward)
        breakdown += f"Event Reward: {event_reward:.6f}\n"
        breakdown += f"Shaping Reward: {shaping_reward:.6f}\n"
        breakdown += f"TOTAL REWARD: {total_reward:.6f}"
        
        # ВІДКЛЮЧЕНО: Не логуємо кожну нагороду - це спамить логи!
        # self.logger.info(f"Reward Breakdown:\n{breakdown}")
        
    def _get_normalization_stats(self) -> Dict[str, Dict[str, float]]:
        """Отримання статистики нормалізаторів"""
        # Якщо є менеджер нормалізації — беремо статистику з нього
        if hasattr(self, 'normalization_manager') and self.normalization_manager:
            try:
                return self.normalization_manager.get_all_stats()
            except Exception:
                pass
        stats = {}
        for name, normalizer in self.normalizers.items():
            if hasattr(normalizer, 'get_stats'):
                stats[name] = normalizer.get_stats()
        return stats
        
    def _create_safe_reward_result(self, timestamp: float, error_msg: str) -> TotalRewardResult:
        """Створення безпечного результату при помилці"""
        safe_reward_value = self.safe_reward if self.safe_reward is not None else 0.0
        return TotalRewardResult(
            total_reward=safe_reward_value,
            component_rewards={},
            adaptive_weights={},
            normalization_stats={},
            timestamp=timestamp,
            metadata={"error": error_msg, "safe_mode": True}
        )
    
    def compute_reward(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Основний інтерфейс для розрахунку винагороди з контекстом
        
        Args:
            context: Контекст, що містить стан, дію та інші дані
            
        Returns:
            Результат розрахунку винагороди у форматі словника
        """
        try:
            # Витягуємо необхідні дані з контексту
            state_t = context.get('state_t')
            action_t = context.get('action_t')
            state_t_plus_1 = context.get('state_t_plus_1')
            execution_data = context.get('execution_data')
            model_prediction_data = context.get('model_prediction_data')
            active_events_data = context.get('active_events_data')
            
            # Якщо немає основного стану, повертаємо безпечне значення
            if state_t is None:
                self.logger.warning("compute_reward called without state_t, using safe reward")
                return {
                    'total_reward': self.safe_reward,
                    'metadata': {'error': 'Missing state_t in context', 'safe_mode': True}
                }
            
            # Викликаємо основний метод розрахунку
            result = self.calculate_total_reward(
                state_t=state_t,
                action_t=action_t,
                state_t_plus_1=state_t_plus_1,
                execution_data=execution_data,
                model_prediction_data=model_prediction_data,
                active_events_data=active_events_data
            )
            
            # Перетворюємо в формат словника
            return {
                'total_reward': result.total_reward,
                'component_rewards': {name: comp.raw_value for name, comp in result.component_rewards.items()},
                'adaptive_weights': result.adaptive_weights,
                'normalization_stats': result.normalization_stats,
                'timestamp': result.timestamp,
                'metadata': result.metadata
            }
            
        except Exception as e:
            self.logger.error(f"Error in compute_reward: {e}")
            return {
                'total_reward': self.safe_reward,
                'metadata': {'error': str(e), 'safe_mode': True}
            }
    
    def reset(self):
        """
        Скидання стану reward engine
        """
        try:
            # Скидаємо стан адаптивних вагів
            if hasattr(self.adaptive_weights_manager, 'reset'):
                self.adaptive_weights_manager.reset()
            
            # Скидаємо стан нормалізаторів
            if hasattr(self, 'normalization_manager') and self.normalization_manager:
                self.normalization_manager.reset_all()
            else:
                for normalizer in self.normalizers.values():
                    if hasattr(normalizer, 'reset'):
                        normalizer.reset()
                    
            # Скидаємо стан компонентів
            for component in self.components.values():
                if hasattr(component, 'reset'):
                    component.reset()
                    
            self.logger.debug("RewardEngine reset completed")
            
        except Exception as e:
            self.logger.error(f"Error during reset: {e}")
