"""
Behavior Reward Component для ALYSHA-RE-V3+

Компонент розрахунку винагороди за поведінкові паттерни агента.

Основна формула:
R_Behavior,t = β_strategy * Φ_strategy,t + β_freq * Φ_frequency,t + β_latency * Φ_latency,t

Автор: ALYSHA система
Версія: V3+
"""

import logging
import numpy as np
from typing import Dict, Any, Optional, cast
from ..data_types import ARCEData, PortfolioData, StateData, RewardComponentResult, AgentActionData
from ..utils import RewardEngineConfig, validate_numeric_value, safe_divide
from .base import BaseRewardComponent


class BehaviorRewardComponent(BaseRewardComponent):
    """
    Компонент винагороди за поведінкові паттерни
    
    Розраховує винагороду на основі:
    - Стратегічної консистентності (strategy consistency)
    - Частоти торгівлі (trading frequency) 
    - Латентності виконання (execution latency)
    """
    
    def __init__(self, config: RewardEngineConfig):
        # BaseRewardComponent очікує словник, а не RewardEngineConfig
        # type: ignore використано, щоб не міняти базовий клас
        super().__init__(cast(Any, config))  # type: ignore[arg-type]
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Отримуємо конфігурацію для компоненти поведінки
        behavior_config = config.get_component_config("behavior")
        
        # Коефіцієнти для різних аспектів поведінки
        self.beta_strategy = behavior_config.get("beta_strategy", 1.0)
        self.beta_frequency = behavior_config.get("beta_frequency", 0.5)
        self.beta_latency = behavior_config.get("beta_latency", 0.3)
        
        # Конфігурація підкомпонент
        self.strategy_config = behavior_config.get("strategy_consistency", {})
        self.frequency_config = behavior_config.get("trading_frequency", {})
        self.latency_config = behavior_config.get("execution_latency", {})
        
        # Історія для аналізу поведінки
        self.action_history = []
        self.latency_history = []
        self.trade_timestamps = []
        self.consistency_window = self.strategy_config.get("consistency_window", 20)
        self.frequency_window = self.frequency_config.get("frequency_window", 50)
        self.frequency_window_seconds = self.frequency_config.get("frequency_window_seconds", 60.0)
        
        self.enabled = config.is_component_enabled("behavior")
        
        self.logger.info(f"Behavior Component initialized with betas: "
                        f"strategy={self.beta_strategy}, frequency={self.beta_frequency}, "
                        f"latency={self.beta_latency}")
        
    def calculate_reward(self, state: StateData) -> RewardComponentResult:
        """
        Розрахувати винагороду компонента (BaseRewardComponent interface)
        
        Args:
            state: Дані стану на поточний момент часу
            
        Returns:
            RewardComponentResult: Результат розрахунку компонента
        """
        # Extract data from state for the existing calculate method
        arce_data = state.arce if hasattr(state, 'arce') else None
        portfolio_data = state.portfolio if hasattr(state, 'portfolio') else None
        return self.calculate(arce_data, portfolio_data, state)
        
    def calculate(self,
                  arce_data: Optional[ARCEData],          # ← дозволити None
                  portfolio_data: Optional[PortfolioData],  # ← дозволити None
                  state_data: StateData) -> RewardComponentResult:
        """
        Розрахунок винагороди за поведінку
        
        Args:
            arce_data: Дані з ARCE системи
            portfolio_data: Дані портфеля
            state_data: Загальні дані стану
            
        Returns:
            Результат розрахунку компоненти поведінки
        """
        if not self.enabled:
            self.logger.debug("Behavior component disabled, returning 0")
            return RewardComponentResult(
                component_name="behavior",
                raw_value=0.0,
                subcomponents={"disabled": 0.0}
            )
            
        try:
            # Оновлюємо локальні історії перед розрахунком
            try:
                if hasattr(state_data, 'execution') and state_data.execution is not None:
                    self._update_trade_history(state_data)
            except Exception:
                # Не блокуємо розрахунок при збоях історії
                pass

            # Розрахунок всіх підкомпонент поведінки
            strategy_reward = self._calculate_strategy_consistency(state_data)
            frequency_reward = self._calculate_trading_frequency(state_data)
            latency_reward = self._calculate_execution_latency(state_data)
            
            # Загальна винагорода за поведінку
            total_behavior_reward = (
                self.beta_strategy * strategy_reward +
                self.beta_frequency * frequency_reward +
                self.beta_latency * latency_reward
            )
            
            # Підкомпоненти для детального аналізу
            subcomponents = {
                "strategy_consistency": strategy_reward,
                "trading_frequency": frequency_reward,
                "execution_latency": latency_reward,
                "strategy_weighted": self.beta_strategy * strategy_reward,
                "frequency_weighted": self.beta_frequency * frequency_reward,
                "latency_weighted": self.beta_latency * latency_reward
            }
            
            self.logger.debug(f"Behavior calculation: total={total_behavior_reward:.6f}, "
                             f"strategy={strategy_reward:.6f}, frequency={frequency_reward:.6f}, "
                             f"latency={latency_reward:.6f}")
            
            return RewardComponentResult(
                component_name="behavior",
                raw_value=total_behavior_reward,
                subcomponents=subcomponents
            )
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку Behavior component: {e}")
            safe_reward = self.config.get_validation_config().get("default_safe_reward", -10.0)
            return RewardComponentResult(
                component_name="behavior",
                raw_value=safe_reward,
                subcomponents={"error": safe_reward}       # float, щоб співпасти з Dict[str, float]
            )
            
    def _calculate_strategy_consistency(self, state_data: StateData) -> float:
        """
        Розрахунок винагороди за стратегічну консистентність
        
        Args:
            state_data: Дані стану з інформацією про дії агента
            
        Returns:
            Винагорода за консистентність стратегії
        """
        try:
            if not hasattr(state_data, 'agent_action') or state_data.agent_action is None:
                return 0.0
                
            agent_action = state_data.agent_action
            
            # Додаємо поточну дію до історії
            self._update_action_history(agent_action)
            
            if len(self.action_history) < 2:
                return 0.0  # Недостатньо даних для аналізу
                
            # Аналіз консистентності по останніх діях
            recent_actions = self.action_history[-self.consistency_window:]
            
            if len(recent_actions) < 2:
                return 0.0
                
            # Розрахунок показників консистентності
            directional_consistency = self._calculate_directional_consistency(recent_actions)
            magnitude_consistency = self._calculate_magnitude_consistency(recent_actions)
            
            # Комбінована міра консистентності
            consistency_weight_dir = self.strategy_config.get("directional_weight", 0.7)
            consistency_weight_mag = self.strategy_config.get("magnitude_weight", 0.3)
            
            overall_consistency = (
                consistency_weight_dir * directional_consistency + 
                consistency_weight_mag * magnitude_consistency
            )
            
            # Винагорода за консистентність (позитивна за гарну консистентність)
            baseline_consistency = self.strategy_config.get("baseline_consistency", 0.5)
            consistency_reward = max(0, overall_consistency - baseline_consistency)
            
            self.logger.debug(f"Strategy consistency: dir={directional_consistency:.4f}, "
                             f"mag={magnitude_consistency:.4f}, overall={overall_consistency:.4f}, "
                             f"reward={consistency_reward:.4f}")
            
            return consistency_reward
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку strategy consistency: {e}")
            return 0.0
            
    def _calculate_trading_frequency(self, state_data: StateData) -> float:
        """
        Розрахунок винагороди за частоту торгівлі
        
        Args:
            state_data: Дані стану з інформацією про виконання
            
        Returns:
            Винагорода за оптимальну частоту торгівлі
        """
        try:
            if not hasattr(state_data, 'execution') or state_data.execution is None:
                return 0.0
                
            execution_data = state_data.execution
            num_trades = len(execution_data.trades) if execution_data.trades else 0
            
            # Підрахунок частоти торгівлі в історичному вікні
            recent_trades = self._get_recent_trade_count(current_ts=getattr(state_data, 'timestamp', None))
            total_recent_trades = recent_trades + num_trades
            
            # Оптимальна частота торгівлі (з конфігурації)
            optimal_frequency = self.frequency_config.get("optimal_frequency", 5.0)
            frequency_tolerance = self.frequency_config.get("frequency_tolerance", 2.0)
            
            # Поточна частота (кількість торгів на одиницю часу)
            # Частота як торги на крок історії дій (наближено)
            current_frequency = total_recent_trades / max(1, len(self.action_history[-self.frequency_window:]))
            
            # Розрахунок штрафу/винагороди за відхилення від оптимальної частоти
            frequency_deviation = abs(current_frequency - optimal_frequency)
            
            if frequency_deviation <= frequency_tolerance:
                # В межах толерантності - позитивна винагорода
                frequency_reward = 1.0 - (frequency_deviation / frequency_tolerance) * 0.5
            else:
                # Поза межами толерантності - штраф
                excess_deviation = frequency_deviation - frequency_tolerance
                penalty_rate = self.frequency_config.get("penalty_rate", 0.1)
                frequency_reward = -penalty_rate * excess_deviation
                
            self.logger.debug(f"Trading frequency: current={current_frequency:.4f}, "
                             f"optimal={optimal_frequency:.4f}, deviation={frequency_deviation:.4f}, "
                             f"reward={frequency_reward:.4f}")
            
            return frequency_reward
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку trading frequency: {e}")
            return 0.0
            
    def _calculate_execution_latency(self, state_data: StateData) -> float:
        """
        Розрахунок винагороди за латентність виконання
        
        Args:
            state_data: Дані стану з інформацією про виконання
            
        Returns:
            Винагорода за низьку латентність виконання
        """
        try:
            if not hasattr(state_data, 'execution') or state_data.execution is None:
                return 0.0
                
            execution_data = state_data.execution
            
            # Розрахунок середньої латентності по заповненнях ордерів
            if not execution_data.fills:
                return 0.0
                
            total_latency = 0.0
            fill_count = 0
            
            current_time = state_data.timestamp
            
            for fill in execution_data.fills:
                if hasattr(fill, 'timestamp'):
                    latency = current_time - fill.timestamp
                    if latency >= 0:  # Валідна латентність
                        total_latency += latency
                        fill_count += 1
                        
            if fill_count == 0:
                return 0.0
                
            average_latency = total_latency / fill_count
            
            # Додаємо до історії латентності
            self.latency_history.append(average_latency)
            
            # Утримуємо розмір історії
            max_latency_history = self.latency_config.get("latency_history_size", 100)
            if len(self.latency_history) > max_latency_history:
                self.latency_history = self.latency_history[-max_latency_history:]
                
            # Цільова латентність
            target_latency = self.latency_config.get("target_latency", 0.1)  # 100ms
            latency_tolerance = self.latency_config.get("latency_tolerance", 0.05)  # 50ms
            
            # Розрахунок винагороди/штрафу за латентність
            latency_deviation = average_latency - target_latency
            
            if latency_deviation <= latency_tolerance:
                # Гарна латентність - позитивна винагорода
                if latency_deviation <= 0:
                    latency_reward = 1.0  # Ідеальна латентність
                else:
                    latency_reward = 1.0 - (latency_deviation / latency_tolerance) * 0.5
            else:
                # Погана латентність - штраф
                excess_latency = latency_deviation - latency_tolerance
                penalty_rate = self.latency_config.get("latency_penalty_rate", 2.0)
                latency_reward = -penalty_rate * excess_latency
                
            self.logger.debug(f"Execution latency: avg={average_latency:.4f}, "
                             f"target={target_latency:.4f}, deviation={latency_deviation:.4f}, "
                             f"reward={latency_reward:.4f}")
                             
            return latency_reward
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку execution latency: {e}")
            return 0.0
            
    def _update_action_history(self, agent_action: AgentActionData):
        """Оновлення історії дій агента"""
        action_info = {
            'action_vector': agent_action.action_vector.copy() if agent_action.action_vector is not None else None,
            'action_type': agent_action.action_type,
            'action_direction': agent_action.action_direction,
            'is_exploratory': agent_action.is_exploratory,
            'timestamp': getattr(agent_action, 'timestamp', None)
        }
        
        self.action_history.append(action_info)
        
        # Утримуємо розмір історії
        max_history_size = max(self.consistency_window, self.frequency_window) * 2
        if len(self.action_history) > max_history_size:
            self.action_history = self.action_history[-max_history_size:]

    def _update_trade_history(self, state_data: StateData) -> None:
        """Оновлення історії торгів з ExecutionData з обрізанням вікна за часом."""
        try:
            if not hasattr(state_data, 'execution') or state_data.execution is None:
                return
            ts_now = float(getattr(state_data, 'timestamp', 0.0) or 0.0)
            # Додаємо таймстампи трейдів, якщо є
            for tr in (state_data.execution.trades or []):
                tr_ts = getattr(tr, 'timestamp', None)
                if tr_ts is None:
                    continue
                try:
                    self.trade_timestamps.append(float(tr_ts))
                except Exception:
                    continue
            # Актуалізуємо вікно по часу
            if ts_now > 0 and self.trade_timestamps:
                cutoff = ts_now - float(self.frequency_window_seconds)
                self.trade_timestamps = [t for t in self.trade_timestamps if t >= cutoff]
            # Також лімітуємо загальний розмір списку
            max_keep = max(self.frequency_window * 10, 500)
            if len(self.trade_timestamps) > max_keep:
                self.trade_timestamps = self.trade_timestamps[-max_keep:]
        except Exception:
            # Не провалюємо розрахунок поведінки через історію торгів
            pass
            
    def _calculate_directional_consistency(self, recent_actions) -> float:
         """Розрахунок консистентності напрямку дій"""
         if len(recent_actions) < 2:
             return 0.0
             
         directions = [action.get('action_direction', 0) for action in recent_actions]
         
         # Розрахунок частоти зміни напрямку
         direction_changes = 0
         for i in range(1, len(directions)):
             if directions[i] != directions[i-1] and directions[i] != 0 and directions[i-1] != 0:
                 direction_changes += 1
                 
         # Консистентність = 1 - (частота змін / максимальна можлива частота)
         max_possible_changes = len(directions) - 1
         if max_possible_changes == 0:
             return 1.0
             
         change_rate = direction_changes / max_possible_changes
         consistency = 1.0 - change_rate
         
         return float(max(0.0, min(1.0, consistency)))      # приведено до float
        
    def _calculate_magnitude_consistency(self, recent_actions) -> float:
         """Розрахунок консистентності величини дій"""
         if len(recent_actions) < 2:
             return 0.0
             
         action_vectors = []
         for action in recent_actions:
             if action.get('action_vector') is not None:
                 action_vectors.append(action['action_vector'])
                 
         if len(action_vectors) < 2:
             return 0.0
             
         # Розрахунок коваріації магнітуд
         magnitudes = [np.linalg.norm(vec) for vec in action_vectors]
         
         if len(set(magnitudes)) == 1:
             return 1.0  # Всі магнітуди однакові - ідеальна консистентність
             
         # Використовуємо коефіцієнт варіації як міру консистентності
         mean_magnitude = np.mean(magnitudes)
         std_magnitude = np.std(magnitudes)
         
         if mean_magnitude == 0:
             return 1.0
         
         coefficient_of_variation = std_magnitude / mean_magnitude
         consistency: float = 1.0 / (1.0 + float(coefficient_of_variation))
         
         # Clamp to [0, 1] and return
         return max(0.0, min(1.0, consistency))      # приведено до float
        
    def _get_recent_trade_count(self, current_ts: Optional[float] = None) -> int:
        """Кількість торгів за останнє вікно часу frequency_window_seconds."""
        try:
            if not self.trade_timestamps:
                return 0
            if current_ts is None:
                # Якщо немає метки часу стану, оцінюємо по останньому трейду
                current_ts = float(self.trade_timestamps[-1])
            cutoff = float(current_ts) - float(self.frequency_window_seconds)
            return int(sum(1 for t in self.trade_timestamps if t >= cutoff))
        except Exception:
            return 0

    def reset(self) -> None:
        """Скидання внутрішнього стану компоненту поведінки."""
        # Copilot: Refactor — додаємо явний reset для уникнення витоків стану між епізодами
        self.action_history.clear()
        self.latency_history.clear()
        self.trade_timestamps.clear()
        
    def get_component_info(self) -> Dict[str, Any]:
        """Отримання інформації про компоненту поведінки"""
        return {
            "component_name": "behavior",
            "enabled": self.enabled,
            "beta_coefficients": {
                "strategy": self.beta_strategy,
                "frequency": self.beta_frequency,
                "latency": self.beta_latency
            },
            "subcomponents": [
                "strategy_consistency",
                "trading_frequency",
                "execution_latency"
            ],
            "history_stats": {
                "action_history_size": len(self.action_history),
                "latency_history_size": len(self.latency_history),
                "consistency_window": self.consistency_window,
                "frequency_window": self.frequency_window
            },
            "description": "Розрахунок винагороди за поведінкові паттерни агента"
        }
