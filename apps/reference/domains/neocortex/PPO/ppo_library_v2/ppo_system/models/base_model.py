# QUARANTINED: legacy_runtime
# path: ppo_library/ppo_system/models/base_model.py
from __future__ import annotations
__quarantined__ = True
from abc import ABC, abstractmethod
from typing import Tuple, Union, Optional
import torch
import torch.nn as nn
from torch.distributions import Distribution

class BaseActorCritic(nn.Module, ABC):
    """
    Абстрактний базовий клас для всіх actor-critic моделей в ppo_system.
    Визначає єдиний контракт: forward pass повертає розподіл, оцінку та прихований стан.
    """
    @abstractmethod
    def init_hidden(
        self, batch_size: int, device: Union[str, torch.device]
    ) -> Optional[Tuple[torch.Tensor, ...]]:
        """
        Ініціалізує прихований стан для рекурентних моделей.
        Повертає None для нерекурентних моделей.
        """
        ...

    @abstractmethod
    def forward(
        self,
        x: torch.Tensor,
        hidden: Optional[Tuple[torch.Tensor, ...]] = None
    ) -> Tuple[Distribution, torch.Tensor, Optional[Tuple[torch.Tensor, ...]]]:
        """
        Виконує forward pass.

        Args:
            x (torch.Tensor): Вхідний тензор спостережень.
            hidden (Optional): Попередній прихований стан.

        Returns:
            Tuple[Distribution, torch.Tensor, Optional[Tuple[torch.Tensor, ...]]]:
            - Об'єкт розподілу для дій (напр., Categorical або Normal).
            - Тензор оцінки стану (value).
            - Новий прихований стан.
        """
        ...