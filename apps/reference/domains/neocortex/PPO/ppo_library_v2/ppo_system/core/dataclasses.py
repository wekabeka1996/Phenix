# QUARANTINED: legacy_runtime
# path: ppo_library/ppo_system/core/dataclasses.py
from __future__ import annotations
__quarantined__ = True
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import torch

# Імпортуємо типізовану конфігурацію безпеки
from ..utils.safety import SafetyConfig


@dataclass
class PPOBatch:
    """
    Типізований контракт для батча даних, що передається в PolicyUpdater.
    Забезпечує чіткість та надійність потоку даних.
    """
    obs: torch.Tensor
    act: torch.Tensor
    ret: torch.Tensor
    adv: torch.Tensor
    logp: torch.Tensor
    extra: Dict[str, torch.Tensor] = field(default_factory=dict)


@dataclass
class StepResult:
    """
    Стандартизований результат одного кроку середовища.
    Забезпечує сумісність з різними реалізаціями середовищ (gym, gymnasium, custom).
    """
    obs: Any
    reward: float
    done: bool
    info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """
    Конфігурація, що стосується виключно архітектури та логіки PPO-агента.
    Не містить параметрів тренувального циклу чи середовища.
    """
    # Параметри алгоритму PPO
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 0.5
    epochs: int = 10
    batch_size: int = 64
    target_kl: Optional[float] = 0.015

    # Параметри архітектури моделі
    hidden_size: int = 256
    lstm_layers: int = 1
    continuous_head: str = "gaussian"  # "gaussian" | "squashed_gaussian"
    log_std_init: float = -0.5
    temperature: float = 1.0
    sigma_min: float = 0.05

    # Параметри безпеки та стабілізації
    numerical_safety: Optional[SafetyConfig] = None


@dataclass
class TrainConfig:
    """
    Конфігурація, що стосується виключно тренувального процесу (циклу).
    """
    total_timesteps: int = 1_000_000
    n_steps: int = 2048  # Довжина однієї траєкторії перед оновленням
    eval_interval: int = 10_000

    # Параметри середовища та виконання
    device: str = "cpu"
    seed: int = 42
    debug_logging: bool = False


@dataclass
class PPOConfig:
    """
    Об'єднана конфігурація для PPO агента, що містить як AgentConfig, так і TrainConfig.
    """
    # AgentConfig поля
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 0.5
    epochs: int = 10
    batch_size: int = 64
    target_kl: Optional[float] = 0.015
    hidden_size: int = 256
    lstm_layers: int = 1
    continuous_head: str = "gaussian"
    log_std_init: float = -0.5
    temperature: float = 1.0
    sigma_min: float = 0.05
    numerical_safety: Optional[SafetyConfig] = None

    # TrainConfig поля
    total_timesteps: int = 1_000_000
    n_steps: int = 2048
    eval_interval: int = 10_000
    device: str = "cpu"
    seed: int = 42
    debug_logging: bool = False
