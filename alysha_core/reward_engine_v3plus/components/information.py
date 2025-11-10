"""
Information Reward Component для ALYSHA-RE-V3+

Компонент розрахунку винагороди за інформаційні аспекти торгівлі.

Основна формула:
R_Information,t = γ_align * Φ_align,t + γ_explore * Φ_explore,t

де:
- Φ_align,t - міра узгодженості з сигналами (Signal Alignment)
- Φ_explore,t - міра стратегічного дослідження (Strategic Exploration)

Автор: ALYSHA система
Версія: V3+
"""

import logging
import numpy as np
from typing import Dict, Any, Optional
from ..data_types import (
    ARCEData, PortfolioData, StateData, RewardComponentResult, 
    AgentActionData, ModelPredictionData
)
from ..utils import RewardEngineConfig, validate_numeric_value, calculate_cosine_similarity
from .base import BaseRewardComponent


class InformationRewardComponent(BaseRewardComponent):
    """
    Компонент винагороди за інформаційні аспекти
    
    Розраховує винагороду на основі:
    - Signal Alignment - узгодженості дій з ринковими сигналами
    - Strategic Exploration - стратегічного дослідження невизначених областей
    """
    
    def __init__(self, config: RewardEngineConfig):
        info_config = config.get_component_config("information")
        super().__init__(info_config)
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Отримуємо конфігурацію для компоненти інформації
        
        # Коефіцієнти для різних аспектів інформації
        self.gamma_align = info_config.get("signal_alignment", {}).get("c_align", 4.0)
        self.gamma_explore = info_config.get("strategic_exploration", {}).get("c_explore", 2.0)
        
        # Конфігурація підкомпонент
        self.signal_config = info_config.get("signal_alignment", {})
        self.exploration_config = info_config.get("strategic_exploration", {})
        
        # Історія дій для розрахунку новизни
        self.action_history = []
        
        # Функція для розрахунку узгодженості
        self.alignment_function = self.signal_config.get("alignment_function", "cosine_similarity")
        
        # Історія для аналізу exploration
        self.exploration_history = []
        self.max_exploration_history = self.exploration_config.get("exploration_history_size", 100)
        
        self.enabled = config.is_component_enabled("information")
        
        self.logger.info(f"Information Component initialized with gammas: "
                        f"align={self.gamma_align}, explore={self.gamma_explore}, "
                        f"alignment_function={self.alignment_function}")
        
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
        
        if arce_data is None or portfolio_data is None:
            self.logger.warning("ARCE or Portfolio data is missing, returning 0 reward.")
            return RewardComponentResult(component_name="information", raw_value=0.0)

        return self.calculate(arce_data, portfolio_data, state)
        
    def calculate(self, arce_data: ARCEData, portfolio_data: PortfolioData, 
                 state_data: StateData) -> RewardComponentResult:
        """
        Розрахунок винагороди за інформацію
        
        Args:
            arce_data: Дані з ARCE системи
            portfolio_data: Дані портфеля
            state_data: Загальні дані стану
            
        Returns:
            Результат розрахунку компоненти інформації
        """
        if not self.enabled:
            self.logger.debug("Information component disabled, returning 0")
            return RewardComponentResult(
                component_name="information",
                raw_value=0.0,
                subcomponents={"disabled": 0.0}
            )
            
        try:
            # Розрахунок всіх підкомпонент інформації
            signal_alignment_reward = self._calculate_signal_alignment(state_data)
            strategic_exploration_reward = self._calculate_strategic_exploration(state_data)
            
            # Загальна винагорода за інформацію
            total_information_reward = (
                self.gamma_align * signal_alignment_reward +
                self.gamma_explore * strategic_exploration_reward
            )
            
            # Підкомпоненти для детального аналізу
            subcomponents = {
                "signal_alignment": signal_alignment_reward,
                "strategic_exploration": strategic_exploration_reward,
                "signal_weighted": self.gamma_align * signal_alignment_reward,
                "exploration_weighted": self.gamma_explore * strategic_exploration_reward
            }
            
            self.logger.debug(f"Information calculation: total={total_information_reward:.6f}, "
                             f"signal_alignment={signal_alignment_reward:.6f}, "
                             f"strategic_exploration={strategic_exploration_reward:.6f}")
            
            return RewardComponentResult(
                component_name="information",
                raw_value=total_information_reward,
                subcomponents=subcomponents
            )
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку Information component: {e}")
            safe_reward = self.config.get_validation_config().get("default_safe_reward", -10.0)
            return RewardComponentResult(
                component_name="information",
                raw_value=safe_reward,
                subcomponents={"error": safe_reward}
            )
            
    def _calculate_signal_alignment(self, state_data: StateData) -> float:
        """
        Розрахунок винагороди за узгодженість з сигналами
        
        Формула: Φ_align,t = AlignmentFunc(Action_t, Signal_t)
        
        Args:
            state_data: Дані стану з інформацією про дії та прогнози
            
        Returns:
            Винагорода за узгодженість з сигналами
        """
        try:
            # Перевіряємо наявність дій агента та прогнозів моделі
            if not hasattr(state_data, 'agent_action') or state_data.agent_action is None:
                return 0.0
                
            if not hasattr(state_data, 'model_prediction') or state_data.model_prediction is None:
                # Спробуємо отримати сигнали з market_data
                market_signals = getattr(state_data.market_data, 'signals', {}) if state_data.market_data else {}
                if not market_signals:
                    return 0.0
                signal_vector = self._extract_signal_vector(market_signals)
            else:
                signal_vector = state_data.model_prediction.prediction_vector
                
            action_vector = state_data.agent_action.action_vector
            
            if action_vector is None or signal_vector is None:
                return 0.0
                
            # Нормалізуємо вектори до однакової довжини
            min_length = min(len(action_vector), len(signal_vector))
            action_norm = action_vector[:min_length]
            signal_norm = signal_vector[:min_length]
            
            # Розрахунок узгодженості залежно від функції
            if self.alignment_function == "cosine_similarity":
                alignment = calculate_cosine_similarity(action_norm, signal_norm)
            elif self.alignment_function == "direction_product":
                alignment = self._calculate_direction_product(action_norm, signal_norm)
            else:
                # За замовчуванням - косинусна подібність
                alignment = calculate_cosine_similarity(action_norm, signal_norm)
                
            # Нормалізуємо до діапазону [0, 1]
            normalized_alignment = max(0.0, min(1.0, (alignment + 1.0) / 2.0))
            
            self.logger.debug(f"Signal alignment: alignment={alignment:.4f}, "
                             f"normalized={normalized_alignment:.4f}")
            
            return normalized_alignment
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку signal alignment: {e}")
            return 0.0
            
    def _calculate_strategic_exploration(self, state_data: StateData) -> float:
        """
        Розрахунок винагороди за стратегічне дослідження
        
        Винагорода за дослідження невизначених або нових областей
        
        Args:
            state_data: Дані стану з інформацією про дії та невизначеність
            
        Returns:
            Винагорода за стратегічне дослідження
        """
        try:
            if not hasattr(state_data, 'agent_action') or state_data.agent_action is None:
                return 0.0
                
            agent_action = state_data.agent_action
            
            # Перевіряємо чи є дія дослідницькою
            if not agent_action.is_exploratory:
                return 0.0  # Не дослідницька дія
                
            # Отримуємо невизначеність моделі
            model_uncertainty = 0.0
            if hasattr(state_data, 'model_prediction') and state_data.model_prediction is not None:
                model_uncertainty = state_data.model_prediction.model_uncertainty
            else:
                # Спробуємо оцінити невизначеність з ринкових даних
                model_uncertainty = self._estimate_market_uncertainty(state_data)
                
            # Розрахунок винагороди за exploration
            base_exploration_reward = self.exploration_config.get("base_exploration_reward", 0.1)
            uncertainty_multiplier = self.exploration_config.get("uncertainty_multiplier", 2.0)
            
            # Винагорода пропорційна невизначеності
            exploration_reward = base_exploration_reward + uncertainty_multiplier * model_uncertainty
            
            # Додаємо бонус за новизну області дослідження
            novelty_bonus = self._calculate_novelty_bonus(agent_action)
            exploration_reward += novelty_bonus
            
            # Обмеження максимальної винагороди
            max_exploration_reward = self.exploration_config.get("max_exploration_reward", 1.0)
            exploration_reward = min(exploration_reward, max_exploration_reward)
            
            # Оновлюємо історію exploration
            self._update_exploration_history(agent_action, model_uncertainty)
            
            self.logger.debug(f"Strategic exploration: uncertainty={model_uncertainty:.4f}, "
                             f"novelty_bonus={novelty_bonus:.4f}, reward={exploration_reward:.4f}")
            
            return exploration_reward
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку strategic exploration: {e}")
            return 0.0
            
    def _extract_signal_vector(self, market_signals: Dict[str, Any]) -> Optional[np.ndarray]:
        """Витяг вектора сигналів з ринкових даних"""
        try:
            # Спробуємо отримати різні типи сигналів
            signals = []
            
            # Технічні індикатори
            if 'technical' in market_signals:
                tech_signals = market_signals['technical']
                for indicator in ['rsi', 'macd', 'bb_position', 'momentum']:
                    if indicator in tech_signals:
                        signals.append(float(tech_signals[indicator]))
                        
            # Фундаментальні сигнали
            if 'fundamental' in market_signals:
                fund_signals = market_signals['fundamental']
                for factor in ['sentiment', 'volume_ratio', 'news_score']:
                    if factor in fund_signals:
                        signals.append(float(fund_signals[factor]))
                        
            # Sentiment сигнали
            if 'sentiment_score' in market_signals:
                signals.append(float(market_signals['sentiment_score']))
                
            if len(signals) > 0:
                return np.array(signals)
            else:
                return None
                
        except Exception as e:
            self.logger.error(f"Помилка в витягу signal vector: {e}")
            return None
            
    def _calculate_direction_product(self, action_vector: np.ndarray, 
                                   signal_vector: np.ndarray) -> float:
        """Розрахунок direction product для узгодженості"""
        try:
            # Нормалізуємо вектори
            action_norm = action_vector / (np.linalg.norm(action_vector) + 1e-8)
            signal_norm = signal_vector / (np.linalg.norm(signal_vector) + 1e-8)
            
            # Dot product нормалізованих векторів
            direction_product = np.dot(action_norm, signal_norm)
            
            return float(direction_product)
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку direction product: {e}")
            return 0.0
            
    def _estimate_market_uncertainty(self, state_data: StateData) -> float:
        """Оцінка невизначеності ринку з доступних даних"""
        try:
            uncertainty = 0.0
            
            # Використовуємо волатильність як міру невизначеності
            if hasattr(state_data, 'arce') and state_data.arce:
                portfolio_vol = state_data.arce.portfolio_volatility
                target_vol = state_data.arce.target_volatility
                
                # Нормалізована волатільність як міра невизначеності
                vol_ratio = portfolio_vol / max(target_vol, 0.01)
                uncertainty = max(0.0, min(1.0, (vol_ratio - 1.0) / 2.0))
                
            # Додаткові фактори невизначеності з ринкових даних
            if state_data.market_data:
                market_data = state_data.market_data
                if hasattr(market_data, 'volatility_spike'):
                    uncertainty += 0.2 * float(getattr(market_data, 'volatility_spike', 0.0))
                    
                if hasattr(market_data, 'regime_uncertainty'):
                    uncertainty += 0.3 * float(getattr(market_data, 'regime_uncertainty', 0.0))
                
            # Переконуємося, що тип float, щоб уникнути помилки Pylance
            uncertainty = float(uncertainty)
            return max(0.0, min(1.0, uncertainty))
            
        except Exception as e:
            self.logger.error(f"Помилка в оцінці market uncertainty: {e}")
            return 0.0
            
    def _calculate_novelty_bonus(self, agent_action: AgentActionData) -> float:
        """Розрахунок бонусу за новизну дослідження"""
        try:
            if len(self.exploration_history) == 0:
                return 0.1  # Перше дослідження завжди отримує бонус
                
            current_action = agent_action.action_vector
            if current_action is None:
                return 0.0
                
            # Порівнюємо з попередніми дослідницькими діями
            similarities = []
            for past_exploration in self.exploration_history[-10:]:  # Останні 10 дій
                past_action = past_exploration.get('action_vector')
                if past_action is not None:
                    similarity = calculate_cosine_similarity(current_action, past_action)
                    similarities.append(abs(similarity))
                    
            if len(similarities) == 0:
                return 0.1
                
            # Чим менше схожість з попередніми діями, тим більший бонус
            avg_similarity = np.mean(similarities)
            novelty_bonus = 1.0 - avg_similarity  # Інвертуємо схожість
            
            # Нормалізуємо та масштабуємо бонус
            novelty_multiplier = self.exploration_config.get("novelty_multiplier", 0.2)
            return max(0.0, min(0.5, novelty_bonus * novelty_multiplier))
            
        except Exception as e:
            self.logger.error(f"Помилка в розрахунку novelty bonus: {e}")
            return 0.0
            
    def _update_exploration_history(self, agent_action: AgentActionData, uncertainty: float):
        """Оновлення історії дослідження"""
        exploration_record = {
            'action_vector': agent_action.action_vector.copy() if agent_action.action_vector is not None else None,
            'action_type': agent_action.action_type,
            'uncertainty': uncertainty,
            'timestamp': getattr(agent_action, 'timestamp', None)
        }
        
        self.exploration_history.append(exploration_record)
        
        # Утримуємо розмір історії
        if len(self.exploration_history) > self.max_exploration_history:
            self.exploration_history = self.exploration_history[-self.max_exploration_history:]
            
    def get_component_info(self) -> Dict[str, Any]:
        """Отримання інформації про компоненту інформації"""
        return {
            "component_name": "information",
            "enabled": self.enabled,
            "gamma_coefficients": {
                "align": self.gamma_align,
                "explore": self.gamma_explore
            },
            "subcomponents": [
                "signal_alignment",
                "strategic_exploration"
            ],
            "configuration": {
                "alignment_function": self.alignment_function,
                "exploration_history_size": len(self.exploration_history),
                "max_exploration_history": self.max_exploration_history
            },
            "description": "Розрахунок винагороди за інформаційні аспекти торгівлі"
        }

    def reset(self) -> None:
        """Скидання внутрішнього стану інформаційного компоненту."""
        try:
            self.action_history.clear()
            self.exploration_history.clear()
        except Exception:
            pass
