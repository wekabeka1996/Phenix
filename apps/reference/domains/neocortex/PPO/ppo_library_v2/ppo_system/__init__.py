# QUARANTINED: legacy_runtime
# path: ppo_library/ppo_system/__init__.py
"""
ppo_system: Універсальна, надійна та конфігурована реалізація PPO-агента як бібліотека.

Цей пакет надає ключові компоненти для побудови та тренування PPO-агентів.
Основні точки входу:
- PPOAgent: Головний клас агента.
- train: Універсальний тренувальний цикл.
- PPOConfig: Об'єкт для конфігурації агента.
- SafetyConfig: Об'єкт для конфігурації чисельної безпеки.
"""
__quarantined__ = True

__version__ = "1.0.0"

# "Піднімаємо" ключові класи та функції на верхній рівень пакету
from .agent import PPOAgent
from .training_loop import train
from .core.dataclasses import PPOConfig
from .utils.safety import SafetyConfig

# Визначаємо публічний API пакету
__all__ = [
    "PPOAgent",
    "train",
    "PPOConfig",
    "SafetyConfig",
]
