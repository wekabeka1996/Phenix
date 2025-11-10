"""
Базовий клас для компонентів винагороди ALYSHA-RE-V3+

Цей модуль містить абстрактний базовий клас для всіх компонентів винагороди.
Кожен компонент повинен успадковувати від BaseRewardComponent та реалізувати
метод calculate_reward.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

from ..data_types import StateData, RewardComponentResult


class BaseRewardComponent(ABC):
    """
    Абстрактний базовий клас для всіх компонентів винагороди.
    
    Кожен компонент винагороди повинен успадковувати від цього класу
    та реалізувати метод calculate_reward.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Ініціалізація базового компонента
        
        Args:
            config: Конфігурація компонента
        """
        self.config = config
        self.component_name = self.__class__.__name__
        
    @abstractmethod
    def calculate_reward(self, state: StateData) -> RewardComponentResult:
        """
        Розрахувати винагороду компонента
        
        Args:
            state: Дані стану на поточний момент часу
            
        Returns:
            RewardComponentResult: Результат розрахунку компонента
        """
        pass
    
    def get_component_name(self) -> str:
        """Отримати назву компонента"""
        return self.component_name
    
    def update_config(self, new_config: Dict[str, Any]):
        """Оновити конфігурацію компонента рекурсивно."""
        def _deep_update(d: Dict[str, Any], u: Dict[str, Any]) -> Dict[str, Any]:
            for k, v in u.items():
                if isinstance(v, dict) and isinstance(d.get(k), dict):
                    d[k] = _deep_update(d.get(k, {}), v)
                else:
                    d[k] = v
            return d
        if isinstance(self.config, dict) and isinstance(new_config, dict):
            _deep_update(self.config, new_config)
        else:
            self.config = new_config
