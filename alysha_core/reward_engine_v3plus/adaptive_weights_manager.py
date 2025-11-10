"""
Адаптивний менеджер ваг для ALYSHA-RE-V3+

Керує адаптивними вагами ω_i(S_t, Θ_t) залежно від ринкового режиму.
Початкова реалізація використовує RiskState.RegimeTag з ARCE.
"""

import logging
from typing import Dict, List, Optional
from .data_types import MarketRegime, ARCEData, WeightsDict, ConfigDict
from .utils import RewardEngineConfig


class AdaptiveWeightsManager:
    """
    Менеджер адаптивних ваг компонент винагороди
    
    Реалізує функцію ω_i(S_t, Θ_t) для динамічного налаштування ваг 
    компонент винагороди залежно від ринкового режиму.
    """
    
    def __init__(self, config: RewardEngineConfig):
        """
        Ініціалізація менеджера адаптивних ваг
        
        Args:
            config: Конфігурація reward engine
        """
        self.config = config
        self.logger = logging.getLogger("alysha_reward_engine.adaptive_weights")
        
        # Завантаження налаштувань адаптивних ваг
        self.enabled = config.get("adaptive_weights.enabled", True)
        self.regime_weights = config.get("adaptive_weights.regime_weights", {})
        
        # Ваги за замовчуванням
        self.default_weights = self.regime_weights.get("DEFAULT", {
            "pnl": 0.35,
            "risk": 0.35, 
            "cost": 0.1,
            "behavior": 0.1,
            "information": 0.1
        })
        
        # Історія для аналізу та відлагодження
        self.regime_history: List[str] = []
        self.weight_history: List[WeightsDict] = []
        
        self.logger.info(f"AdaptiveWeightsManager initialized, enabled={self.enabled}")
        
    def get_weights(self, arce_data: Optional[ARCEData] = None, 
                   regime_tag: Optional[str] = None) -> WeightsDict:
        """
        Отримання адаптивних ваг для поточного ринкового режиму
        
        Args:
            arce_data: Дані з ARCE (містить regime_tag)
            regime_tag: Прямо вказаний ринковий режим
            
        Returns:
            Словник з вагами для кожної компоненти
        """
        if not self.enabled:
            self.logger.debug("Adaptive weights disabled, using default")
            return self.default_weights.copy()
            
        # Визначення ринкового режиму
        if regime_tag:
            regime = regime_tag
        elif arce_data and arce_data.regime_tag:
            regime = arce_data.regime_tag.value if isinstance(arce_data.regime_tag, MarketRegime) else str(arce_data.regime_tag)
        else:
            regime = "DEFAULT"
            self.logger.warning("Не вдалося визначити ринковий режим, використовуються ваги за замовчуванням")
            
        # Отримання ваг для режиму
        weights = self.regime_weights.get(regime, self.default_weights)
        # Нормалізуємо суму ваг до 1.0 для стабільності комбінування
        try:
            total = float(sum(weights.values()))
            if total > 0:
                weights = {k: float(v) / total for k, v in weights.items()}
        except Exception:
            # У разі проблем повертаємо як є
            pass
        
        self.logger.debug(f"Selected weights for regime '{regime}': {weights}")
        
        return weights.copy()
        
    def validate_weights(self, weights: WeightsDict) -> bool:
        """
        Валідація ваг
        
        Args:
            weights: Ваги для валідації
            
        Returns:
            True якщо ваги валідні, False інакше
        """
        try:
            # Перевірка наявності всіх необхідних компонент
            required_components = ["pnl", "risk", "cost", "behavior", "information"]
            for component in required_components:
                if component not in weights:
                    self.logger.warning(f"Відсутня вага для компоненти: {component}")
                    return False
                    
                weight = weights[component]
                if not isinstance(weight, (int, float)) or weight < 0:
                    self.logger.warning(f"Некоректна вага для {component}: {weight}")
                    return False
                    
            # Опціонально: перевірка суми ваг (може не дорівнювати 1.0)
            total_weight = sum(weights.values())
            if total_weight <= 0:
                self.logger.warning(f"Сума ваг повинна бути > 0, отримано: {total_weight}")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"Помилка валідації ваг: {e}")
            return False
            
    def reset(self):
        """Скидає внутрішній стан менеджера ваг."""
        self.regime_history.clear()
        self.weight_history.clear()
        self.logger.debug("AdaptiveWeightsManager has been reset.")

    def update_regime_weights(self, regime: str, new_weights: WeightsDict) -> bool:
        """
        Оновлення ваг для конкретного режиму в runtime
        
        Args:
            regime: Назва ринкового режиму
            new_weights: Нові ваги
            
        Returns:
            True якщо оновлення успішне, False інакше
        """
        if not self.validate_weights(new_weights):
            self.logger.error(f"Не вдалося оновити ваги для режиму {regime}: валідація не пройшла")
            return False
            
        self.regime_weights[regime] = new_weights.copy()
        self.logger.info(f"Оновлено ваги для режиму {regime}: {new_weights}")
        return True
        
    def get_available_regimes(self) -> list:
        """Отримання списку доступних ринкових режимів"""
        return list(self.regime_weights.keys())
        
    def get_regime_info(self, regime: str) -> Dict:
        """
        Отримання інформації про конкретний режим
        
        Args:
            regime: Назва режиму
            
        Returns:
            Інформація про режим
        """
        weights = self.regime_weights.get(regime, {})
        return {
            "regime": regime,
            "weights": weights,
            "total_weight": sum(weights.values()) if weights else 0,
            "components_count": len(weights)
        }
