"""
Normalizers для ALYSHA-RE-V3+ Reward Engine

Реалізує різні методи нормалізації для компонентів винагород:
- AdaptiveZScoreNormalizer - адаптивна Z-score нормалізація
- ClippedScalingNormalizer - обмежене масштабування для подій
- MinMaxNormalizer - мін-макс нормалізація
- RobustNormalizer - стійка до викидів нормалізація

Забезпечує консистентне масштабування винагород для збалансованого навчання.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod
from collections import deque
import statistics

from .utils import RewardEngineConfig


@dataclass
class NormalizationStats:
    """Статистики для нормалізації"""
    mean: float = 0.0
    std: float = 1.0
    min_val: float = 0.0
    max_val: float = 1.0
    count: int = 0
    last_updated: float = 0.0


class BaseNormalizer(ABC):
    """Базовий клас для нормалізаторів"""
    
    @abstractmethod
    def normalize(self, value: float, timestamp: float = 0.0) -> float:
        """Нормалізує значення"""
        pass
    
    @abstractmethod
    def update_stats(self, value: float, timestamp: float = 0.0):
        """Оновлює статистики нормалізатора"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Повертає поточні статистики"""
        pass
    
    @abstractmethod
    def reset(self):
        """Скидає статистики нормалізатора"""
        pass


class AdaptiveZScoreNormalizer(BaseNormalizer):
    """
    Адаптивна Z-score нормалізація з ковзним вікном
    
    Нормалізує значення використовуючи ковзне середнє та стандартне відхилення.
    Адаптується до зміни розподілу даних.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # БЕЗ HARDCODE FALLBACK: всі параметри з конфігурації
        self.window_size = config["window_size"]
        self.min_samples = config["min_samples"]
        self.target_range = tuple(config["target_range"])
        self.epsilon = config["epsilon"]
        self.smoothing_factor = config["smoothing_factor"]
        self.outlier_threshold = config["outlier_threshold"]
        
        # Ковзне вікно для збереження значень
        self.values = deque(maxlen=self.window_size)
        
        # Адаптивні статистики
        self.adaptive_mean = 0.0
        self.adaptive_std = 1.0
        self.count = 0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def normalize(self, value: float, timestamp: float = 0.0) -> float:
        """Нормалізує значення використовуючи адаптивну Z-score"""
        # Оновлюємо статистики
        self.update_stats(value, timestamp)
        
        # Якщо недостатньо семплів, повертаємо обрізане значення
        if len(self.values) < self.min_samples:
            return np.clip(value, self.target_range[0], self.target_range[1])
        
        # Z-score нормалізація
        if self.adaptive_std < self.epsilon:
            z_score = 0.0
        else:
            z_score = (value - self.adaptive_mean) / self.adaptive_std
        
        # Обробка викидів
        if abs(z_score) > self.outlier_threshold:
            z_score = np.sign(z_score) * self.outlier_threshold
        
        # Масштабування до цільового діапазону
        normalized = np.clip(z_score, self.target_range[0], self.target_range[1])
        
        return normalized
    
    def update_stats(self, value: float, timestamp: float = 0.0):
        """Оновлює адаптивні статистики"""
        self.values.append(value)
        self.count += 1
        
        if len(self.values) >= self.min_samples:
            # Розраховуємо статистики ковзного вікна
            values_array = np.array(list(self.values))
            window_mean = float(np.mean(values_array))
            window_std = float(np.std(values_array))
            
            # Адаптивне оновлення з експоненціальним згладжуванням
            if self.count == self.min_samples:
                # Перша ініціалізація
                self.adaptive_mean = window_mean
                self.adaptive_std = max(window_std, self.epsilon)
            else:
                # Плавне оновлення
                self.adaptive_mean = (1 - self.smoothing_factor) * self.adaptive_mean + \
                                   self.smoothing_factor * window_mean
                self.adaptive_std = (1 - self.smoothing_factor) * self.adaptive_std + \
                                  self.smoothing_factor * max(window_std, self.epsilon)
    
    def get_stats(self) -> Dict[str, Any]:
        """Повертає поточні статистики"""
        return {
            "type": "AdaptiveZScore",
            "adaptive_mean": self.adaptive_mean,
            "adaptive_std": self.adaptive_std,
            "window_size": len(self.values),
            "total_samples": self.count,
            "target_range": self.target_range,
            "current_values_range": (min(self.values), max(self.values)) if self.values else (0, 0)
        }
    
    def reset(self):
        """Скидає статистики"""
        self.values.clear()
        self.adaptive_mean = 0.0
        self.adaptive_std = 1.0
        self.count = 0


class ClippedScalingNormalizer(BaseNormalizer):
    """
    Обмежене масштабування для подій з жорсткими межами
    
    Використовується для event компонента, де потрібні жорсткі межі
    та згасання впливу.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # БЕЗ HARDCODE FALLBACK: всі параметри з конфігурації
        self.clip_range = tuple(config["clip_range"])
        self.target_range = tuple(config["target_range"])
        self.decay_factor = config["decay_factor"]
        self.history_size = config.get("history_size", 50) # Опціональний параметр
        
        # Історія для згасання
        self.recent_values = deque(maxlen=self.history_size)
        self.count = 0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def normalize(self, value: float, timestamp: float = 0.0) -> float:
        """Нормалізує значення з обмеженням та масштабуванням"""
        # Оновлюємо статистики
        self.update_stats(value, timestamp)
        
        # Обрізаємо до clip_range
        clipped_value = np.clip(value, self.clip_range[0], self.clip_range[1])
        
        # Масштабуємо до target_range
        clip_min, clip_max = self.clip_range
        target_min, target_max = self.target_range
        
        if clip_max - clip_min == 0:
            normalized = target_min
        else:
            # Лінійне масштабування
            scale_factor = (target_max - target_min) / (clip_max - clip_min)
            normalized = target_min + (clipped_value - clip_min) * scale_factor
        
        # Застосовуємо згасання для великих значень
        if abs(normalized) > abs(target_max) * 0.8:
            decay = self.decay_factor ** (abs(normalized) / abs(target_max))
            normalized *= decay
        
        return normalized
    
    def update_stats(self, value: float, timestamp: float = 0.0):
        """Оновлює статистики"""
        self.recent_values.append(value)
        self.count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Повертає поточні статистики"""
        return {
            "type": "ClippedScaling",
            "clip_range": self.clip_range,
            "target_range": self.target_range,
            "decay_factor": self.decay_factor,
            "recent_samples": len(self.recent_values),
            "total_samples": self.count,
            "recent_range": (min(self.recent_values), max(self.recent_values)) if self.recent_values else (0, 0)
        }
    
    def reset(self):
        """Скидає статистики"""
        self.recent_values.clear()
        self.count = 0


class MinMaxNormalizer(BaseNormalizer):
    """
    Min-Max нормалізація з адаптивними межами
    
    Масштабує значення до заданого діапазону на основі спостережуваних
    мінімальних та максимальних значень.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # БЕЗ HARDCODE FALLBACK: всі параметри з конфігурації
        self.target_range = tuple(config["target_range"])
        self.window_size = config["window_size"]
        self.min_samples = config["min_samples"]
        self.epsilon = config["epsilon"]
        
        # Ковзне вікно
        self.values = deque(maxlen=self.window_size)
        
        # Адаптивні межі
        self.observed_min = float('inf')
        self.observed_max = float('-inf')
        self.count = 0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def normalize(self, value: float, timestamp: float = 0.0) -> float:
        """Нормалізує значення використовуючи Min-Max масштабування"""
        # Оновлюємо статистики
        self.update_stats(value, timestamp)
        
        # Якщо недостатньо семплів
        if len(self.values) < self.min_samples:
            return self.target_range[0]
        
        # Min-Max нормалізація
        value_range = self.observed_max - self.observed_min
        if value_range < self.epsilon:
            return (self.target_range[0] + self.target_range[1]) / 2
        
        # Масштабування
        target_min, target_max = self.target_range
        normalized = target_min + (value - self.observed_min) * \
                    (target_max - target_min) / value_range
        
        # Обмежуємо результат цільовим діапазоном
        return np.clip(normalized, target_min, target_max)
    
    def update_stats(self, value: float, timestamp: float = 0.0):
        """Оновлює межі"""
        self.values.append(value)
        self.count += 1
        
        # Оновлюємо межі на основі ковзного вікна
        if len(self.values) >= self.min_samples:
            self.observed_min = min(self.values)
            self.observed_max = max(self.values)
    
    def get_stats(self) -> Dict[str, Any]:
        """Повертає поточні статистики"""
        return {
            "type": "MinMax",
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "target_range": self.target_range,
            "window_size": len(self.values),
            "total_samples": self.count
        }
    
    def reset(self):
        """Скидає статистики"""
        self.values.clear()
        self.observed_min = float('inf')
        self.observed_max = float('-inf')
        self.count = 0


class RobustNormalizer(BaseNormalizer):
    """
    Стійка до викидів нормалізація використовуючи медіану та MAD
    
    Використовує медіану та медіанне абсолютне відхилення (MAD)
    замість середнього та стандартного відхилення.
    """
    
    def __init__(self, config: Dict[str, Any]):
        # БЕЗ HARDCODE FALLBACK: всі параметри з конфігурації
        self.window_size = config["window_size"]
        self.min_samples = config["min_samples"]
        self.target_range = tuple(config["target_range"])
        self.mad_scaling = config["mad_scaling"]
        
        # Ковзне вікно
        self.values = deque(maxlen=self.window_size)
        self.count = 0
        
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def normalize(self, value: float, timestamp: float = 0.0) -> float:
        """Нормалізує значення використовуючи robust статистики"""
        # Оновлюємо статистики
        self.update_stats(value, timestamp)
        
        # Якщо недостатньо семплів
        if len(self.values) < self.min_samples:
            return np.clip(value, self.target_range[0], self.target_range[1])
        
        # Розраховуємо robust статистики
        values_array = np.array(list(self.values))
        median = np.median(values_array)
        mad = np.median(np.abs(values_array - median))
        
        # Robust z-score
        if mad == 0:
            robust_z = 0.0
        else:
            robust_z = (value - median) / (mad * self.mad_scaling)
        
        # Обмежуємо до цільового діапазону
        normalized = np.clip(robust_z, self.target_range[0], self.target_range[1])
        
        return normalized
    
    def update_stats(self, value: float, timestamp: float = 0.0):
        """Оновлює статистики"""
        self.values.append(value)
        self.count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Повертає поточні статистики"""
        if len(self.values) >= self.min_samples:
            values_array = np.array(list(self.values))
            median = np.median(values_array)
            mad = np.median(np.abs(values_array - median))
        else:
            median = 0.0
            mad = 1.0
        
        return {
            "type": "Robust",
            "median": median,
            "mad": mad,
            "target_range": self.target_range,
            "window_size": len(self.values),
            "total_samples": self.count
        }
    
    def reset(self):
        """Скидає статистики"""
        self.values.clear()
        self.count = 0


class NormalizationManager:
    """
    Менеджер нормалізаторів для всіх компонентів винагород
    
    Керує створенням та використанням нормалізаторів для кожної компоненти
    на основі конфігурації.
    """
    
    def __init__(self, config: RewardEngineConfig):
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Отримуємо конфігурацію нормалізації
        norm_config = config.get_component_config("normalization")
        self.enabled = norm_config.get("enabled", True)
        
        if not self.enabled:
            self.logger.info("Нормалізація вимкнена")
            self.normalizers = {}
            return
        
        # Глобальні налаштування
        global_settings = norm_config.get("global_settings", {})
        self.epsilon = global_settings.get("epsilon", 1e-8)
        self.outlier_threshold = global_settings.get("outlier_threshold", 3.0)
        self.smoothing_factor = global_settings.get("smoothing_factor", 0.1)
        
        # Створюємо нормалізатори для кожної компоненти
        self.normalizers = {}
        component_configs = {k: v for k, v in norm_config.items() 
                           if k not in ["enabled", "global_settings"]}
        
        for component_name, comp_config in component_configs.items():
            self.normalizers[component_name] = self._create_normalizer(
                component_name, comp_config
            )
        
        self.logger.info(f"NormalizationManager ініціалізовано з {len(self.normalizers)} нормалізаторами")
    
    def _create_normalizer(self, component_name: str, config: Dict[str, Any]) -> BaseNormalizer:
        """Створює нормалізатор для компоненти"""
        method = config.get("method", "adaptive_z_score")
        
        # Передаємо глобальні налаштування в конфіг компонента, якщо вони не задані локально
        config.setdefault("epsilon", self.epsilon)
        config.setdefault("outlier_threshold", self.outlier_threshold)
        config.setdefault("smoothing_factor", self.smoothing_factor)

        try:
            if method == "adaptive_z_score":
                return AdaptiveZScoreNormalizer(config)
            
            elif method == "clipped_scaling":
                return ClippedScalingNormalizer(config)
            
            elif method == "min_max":
                return MinMaxNormalizer(config)
            
            elif method == "robust":
                return RobustNormalizer(config)
            
            else:
                self.logger.warning(f"Невідомий метод нормалізації '{method}' для {component_name}, "
                                  f"використовується adaptive_z_score")
                return AdaptiveZScoreNormalizer(config)
        except KeyError as e:
            self.logger.error(f"Критична помилка: відсутній обов'язковий параметр '{e.args[0]}' "
                              f"для нормалізатора '{method}' компонента '{component_name}' в master_config.yaml")
            raise ValueError(f"Missing required parameter '{e.args[0]}' for normalizer '{method}'") from e
    
    def normalize_component_reward(self, component_name: str, reward_value: float, 
                                 timestamp: float = 0.0) -> float:
        """Нормалізує винагороду компоненти"""
        if not self.enabled or component_name not in self.normalizers:
            return reward_value
        
        normalizer = self.normalizers[component_name]
        normalized_value = normalizer.normalize(reward_value, timestamp)
        
        self.logger.debug(f"Нормалізація {component_name}: {reward_value:.4f} -> {normalized_value:.4f}")
        
        return normalized_value
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Повертає статистики всіх нормалізаторів"""
        if not self.enabled:
            return {}
        
        return {name: normalizer.get_stats() 
                for name, normalizer in self.normalizers.items()}
    
    def reset_all(self):
        """Скидає всі нормалізатори"""
        if not self.enabled:
            return
        
        for normalizer in self.normalizers.values():
            normalizer.reset()
        
        self.logger.info("Всі нормалізатори скинуті")
    
    def reset_component(self, component_name: str):
        """Скидає нормалізатор конкретної компоненти"""
        if not self.enabled or component_name not in self.normalizers:
            return
        
        self.normalizers[component_name].reset()
        self.logger.info(f"Нормалізатор {component_name} скинутий")
