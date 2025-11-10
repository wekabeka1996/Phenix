"""
Утиліти для ALYSHA-RE-V3+ Reward Engine

ОНОВЛЕНО: Інтеграція з canonical_config.py для централізованої конфігурації
"""

import yaml
import logging
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, Union
from datetime import datetime
from .data_types import ConfigDict, TradingState, ActionType

# НОВА ІНТЕГРАЦІЯ з canonical_config
try:
    from core.utils.canonical_config import ConfigManager
    CANONICAL_CONFIG_AVAILABLE = True
except ImportError:
    CANONICAL_CONFIG_AVAILABLE = False
    logging.warning("canonical_config not available, falling back to file-based config")


class RewardEngineConfig:
    """Клас для роботи з конфігурацією reward engine"""
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None, master_config: Optional[Dict] = None):
        """
        Ініціалізація конфігурації
        
        Args:
            config_path: Шлях до файлу конфігурації (deprecated, для backward compatibility)
            master_config: Централізована конфігурація з master_config.yaml
        """
        self.config: ConfigDict
        self.config_path: Optional[Path] = None
        self._using_master_config: bool

        if master_config is not None:
            # НОВИЙ ПІДХІД: використовуємо master_config через canonical_config
            self.config = master_config.get('alysha_reward_engine', {})
            self._using_master_config = True
        else:
            # СТАРИЙ ПІДХІД: для backward compatibility з тестами
            if config_path is None:
                # Цей шлях не повинен використовуватися в production
                self.config_path = Path(__file__).parent / "config" / "reward_engine_config.yaml"
            else:
                self.config_path = Path(config_path)
            
            self.config = self._load_config()
            self._using_master_config = False
        
    def _load_config(self) -> ConfigDict:
        """Завантажити конфігурацію з YAML файлу (legacy method)"""
        if not self.config_path:
            raise ValueError("config_path не встановлено для завантаження конфігурації.")
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config if config else {}
        except FileNotFoundError:
            logging.error(f"Конфігураційний файл не знайдено: {self.config_path}")
            raise
        except yaml.YAMLError as e:
            logging.error(f"Помилка парсингу YAML файлу: {e}")
            raise
    
    def get_component_config(self, component_name: str) -> ConfigDict:
        """Отримати конфігурацію для конкретного компонента"""
        # Спеціальний випадок для xai_engine - він знаходиться в корені alysha_reward_engine
        if component_name == 'xai_engine':
            if 'alysha_reward_engine' in self.config:
                result = self.config.get("alysha_reward_engine", {}).get("xai_engine", {})
            else:
                result = self.config.get("xai_engine", {})
                
            if not result:
                logging.warning(f"Конфігурація для компонента {component_name} не знайдена")
            return result
        
        # Для інших компонентів шукаємо в components
        if 'alysha_reward_engine' in self.config:
            components = self.config.get("alysha_reward_engine", {}).get("components", {})
        else:
            components = self.config.get("components", {})
        
        result = components.get(component_name, {})
        if not result:
            logging.warning(f"Конфігурація для компонента {component_name} не знайдена")
        return result
    
    def get_validation_config(self) -> ConfigDict:
        """Отримати конфігурацію валідації"""
        # Якщо config містить alysha_reward_engine секцію, шукаємо всередині неї
        if 'alysha_reward_engine' in self.config:
            return self.config.get("alysha_reward_engine", {}).get("validation", {})
        else:
            return self.config.get("validation", {})
    
    def get_logging_config(self) -> ConfigDict:
        """Отримати конфігурацію логування"""
        # Якщо config містить alysha_reward_engine секцію, шукаємо всередині неї
        if 'alysha_reward_engine' in self.config:
            return self.config.get("alysha_reward_engine", {}).get("logging", {})
        else:
            return self.config.get("logging", {})
    
    def is_component_enabled(self, component_name: str) -> bool:
        """Перевірити, чи включений компонент"""
        component_config = self.get_component_config(component_name)
        return component_config.get("enabled", True)
            
    def get(self, key_path: str, default=None) -> Any:
        """
        Отримати значення з конфігурації за ключем
        
        Args:
            key_path: Шлях до ключа (наприклад, "risk_component.drawdown.c_dd")
            default: Значення за замовчуванням
            
        Returns:
            Значення з конфігурації або default
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
                
        return value
        
    def get_adaptive_weights(self, regime: str = "DEFAULT") -> Dict[str, float]:
        """Отримати адаптивні ваги для ринкового режиму"""
        weights = self.get(f"adaptive_weights.regime_weights.{regime}")
        if weights is None:
            logging.warning(f"Ваги для режиму {regime} не знайдені, використовуються DEFAULT")
            weights = self.get("adaptive_weights.regime_weights.DEFAULT", {})
        return weights
        
    @classmethod
    def from_file(cls, config_path: str) -> 'RewardEngineConfig':
        """
        Створити конфігурацію з файлу
        
        Args:
            config_path: Шлях до файлу конфігурації
            
        Returns:
            RewardEngineConfig завантажена з файлу
        """
        instance = cls.__new__(cls)
        instance.config_path = Path(config_path)
        instance.config = instance._load_config()
        instance._using_master_config = False
        return instance

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'RewardEngineConfig':
        """
        Створити конфігурацію з словника
        
        Args:
            config_dict: Словник з конфігурацією
            
        Returns:
            RewardEngineConfig з конфігурацією з словника
        """
        instance = cls.__new__(cls)
        instance.config_path = None
        instance.config = config_dict
        instance._using_master_config = False
        return instance


def setup_logging(config: RewardEngineConfig) -> logging.Logger:
    """
    Налаштування логування для reward engine
    ОНОВЛЕНО: БЕЗ HARDCODE значень
    
    Args:
        config: Конфігурація reward engine
        
    Returns:
        Налаштований logger
    """
    logging_config = config.get_logging_config()
    log_level = logging_config.get("log_level")
    
    # КРИТИЧНА ВАЛІДАЦІЯ: немає fallback значень
    if not log_level:
        raise ValueError("alysha_reward_engine.logging.log_level not found in configuration")
    
    # Створюємо logger
    logger = logging.getLogger("alysha_reward_engine")
    logger.setLevel(getattr(logging, log_level))
    
    # Якщо у logger'а вже є handlers, не додаємо нові
    if logger.handlers:
        return logger
    
    # Створюємо console handler
    handler = logging.StreamHandler()
    handler.setLevel(getattr(logging, log_level))
    
    # Створюємо formatter з конфігурації
    log_format = logging_config.get("log_format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    
    return logger


def validate_numeric_value(value: Union[float, int], 
                          name: str,
                          min_val: Optional[float] = None,
                          max_val: Optional[float] = None,
                          allow_nan: bool = False,
                          allow_inf: bool = False) -> float:
    """
    Валідація числових значень
    
    Args:
        value: Значення для перевірки
        name: Назва значення (для повідомлень про помилки)
        min_val: Мінімальне допустиме значення
        max_val: Максимальне допустиме значення  
        allow_nan: Чи дозволяти NaN
        allow_inf: Чи дозволяти Inf
        
    Returns:
        Валідоване значення
        
    Raises:
        ValueError: Якщо значення не пройшло валідацію
    """
    if not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{name} має бути числом, отримано {type(value)}")
    
    value = float(value)
    
    if not allow_nan and np.isnan(value):
        raise ValueError(f"{name} містить NaN")
        
    if not allow_inf and np.isinf(value):
        raise ValueError(f"{name} містить Inf")
        
    if min_val is not None and value < min_val:
        raise ValueError(f"{name} = {value} менше мінімального {min_val}")
        
    if max_val is not None and value > max_val:
        raise ValueError(f"{name} = {value} більше максимального {max_val}")
        
    return value


def safe_divide(numerator: float, denominator: float, epsilon: float = 1e-8) -> float:
    """
    Безпечне ділення з обробкою ділення на нуль
    
    Args:
        numerator: Чисельник
        denominator: Знаменник
        epsilon: Мала константа для додавання до знаменника
        
    Returns:
        Результат ділення
    """
    return numerator / (denominator + epsilon)


def clip_reward(reward: float, min_reward: float, max_reward: float) -> float:
    """
    Обмеження винагороди в певних межах
    
    Args:
        reward: Винагорода для обмеження
        min_reward: Мінімальна винагорода
        max_reward: Максимальна винагорода
        
    Returns:
        Обмежена винагорода
    """
    return np.clip(reward, min_reward, max_reward)


def calculate_cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Розрахунок косинусної подібності між векторами
    
    Args:
        vec1: Перший вектор
        vec2: Другий вектор
        
    Returns:
        Косинусна подібність [-1, 1]
    """
    if len(vec1) != len(vec2):
        raise ValueError("Вектори мають мати однакову довжину")
        
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    return np.dot(vec1, vec2) / (norm1 * norm2)


def format_reward_breakdown(component_rewards: Dict[str, float],
                           adaptive_weights: Dict[str, float],
                           total_reward: float) -> str:
    """
    Форматування детального розкладу винагороди для логування
    
    Args:
        component_rewards: Винагороди компонент
        adaptive_weights: Адаптивні ваги
        total_reward: Загальна винагорода
        
    Returns:
        Форматований рядок з розкладом
    """
    breakdown = f"Total Reward: {total_reward:.6f}\n"
    breakdown += "Component Breakdown:\n"
    
    for component, reward in component_rewards.items():
        weight = adaptive_weights.get(component, 0.0)
        weighted_reward = weight * reward
        breakdown += f"  {component}: {reward:.6f} (weight: {weight:.3f}, weighted: {weighted_reward:.6f})\n"
        
    return breakdown
