# QUARANTINED: legacy_runtime
# path: ppo_library/ppo_system/utils/safety.py
from __future__ import annotations
__quarantined__ = True
from dataclasses import dataclass
from typing import Dict, Tuple, Optional, Any, Literal
import logging
import torch

# Визначаємо тип для стратегії обробки невалідних градієнтів
InvalidGradStrategy = Literal["zero_grads", "skip_step", "sanitize"]

@dataclass
class SafetyConfig:
    """
    Типізована конфігурація для всіх параметрів чисельної безпеки.
    """
    # Параметри для розрахунку ratio
    max_log_ratio: float = 10.0
    min_ratio: float = 0.01
    max_ratio: float = 20.0
    fallback_ratio: float = 1.0

    # Параметри для KL-дивергенції та градієнтів
    max_kl_divergence: float = 1.0
    gradient_clip_threshold: float = 0.5

    # Загальні параметри безпеки
    nan_detection: bool = True
    inf_detection: bool = True
    epsilon: float = 1e-8

    # Стратегія обробки невалідних градієнтів
    on_invalid: InvalidGradStrategy = "zero_grads"


class NumericalSafetyManager:
    """
    Інкапсулює всю логіку чисельної безпеки для PPO.
    - Централізована конфігурація через SafetyConfig.
    - Безпечний розрахунок ratio та KL.
    - Валідація градієнтів.
    - Детальна статистика для моніторингу.
    """
    def __init__(self, cfg: SafetyConfig):
        self.config = cfg
        self.logger = logging.getLogger(self.__class__.__name__)
        self.stats = {
            "ratio_corrections": 0,
            "nan_corrections": 0,
            "inf_corrections": 0,
            "kl_corrections": 0,
            "gradient_warnings": 0,
            "zeroed_grads": 0,
            "skipped_steps": 0,
            "sanitized_grads": 0,
        }

    def _sanitize(self, t: torch.Tensor, name: str) -> torch.Tensor:
        """Замінює NaN/Inf на 0 та оновлює статистику."""
        if self.config.nan_detection and torch.isnan(t).any():
            self.stats["nan_corrections"] += 1
            self.logger.warning(f"NaN detected in tensor '{name}'. Replacing with zeros.")
            t = torch.nan_to_num(t, nan=0.0)
        if self.config.inf_detection and torch.isinf(t).any():
            self.stats["inf_corrections"] += 1
            self.logger.warning(f"Inf detected in tensor '{name}'. Replacing with zeros.")
            t = torch.nan_to_num(t, posinf=0.0, neginf=0.0)
        return t

    def safe_ratio(self, logp: torch.Tensor, logp_old: torch.Tensor) -> torch.Tensor:
        """Безпечно розраховує importance sampling ratio."""
        logp = self._sanitize(logp, "logp")
        logp_old = self._sanitize(logp_old, "logp_old")

        log_ratio = (logp - logp_old).clamp(-self.config.max_log_ratio, self.config.max_log_ratio)
        ratio = log_ratio.exp()

        # Фінальне обмеження та перевірка на скінченність
        ratio_clamped = ratio.clamp(self.config.min_ratio, self.config.max_ratio)
        if not torch.isfinite(ratio_clamped).all():
            self.stats["ratio_corrections"] += 1
            self.logger.error("Non-finite values in ratio after clamping. Using fallback.")
            return torch.full_like(ratio, self.config.fallback_ratio)

        return ratio_clamped

    def safe_kl(self, logp: torch.Tensor, logp_old: torch.Tensor) -> float:
        """Безпечно розраховує апроксимацію KL-дивергенції."""
        diff = (logp - logp_old).clamp(-self.config.max_kl_divergence, self.config.max_kl_divergence)
        kl = 0.5 * (diff ** 2).mean().item()

        if not (kl == kl and kl != float("inf")):  # Перевірка на NaN та Inf
            self.stats["kl_corrections"] += 1
            self.logger.warning(f"Invalid KL value detected ({kl}). Returning epsilon.")
            return float(self.config.epsilon)

        return min(kl, self.config.max_kl_divergence)

    def validate_gradients(self, model: torch.nn.Module, grad_norm: float) -> bool:
        """
        Перевіряє градієнти на NaN, Inf та екстремальні значення.
        Повертає True, якщо градієнти валідні, інакше False.
        """
        has_nan = False
        has_inf = False
        for p in model.parameters():
            if p.grad is None:
                continue
            if torch.isnan(p.grad).any():
                has_nan = True
                break
            if torch.isinf(p.grad).any():
                has_inf = True
                break

        # Градієнти вважаються невалідними, якщо є NaN/Inf або якщо їхня норма
        # значно перевищує поріг кліппінгу (індикатор вибуху).
        is_ok = not has_nan and not has_inf and (grad_norm <= 10 * self.config.gradient_clip_threshold)

        if not is_ok:
            self.stats["gradient_warnings"] += 1
            self.logger.warning(
                f"Gradient validation FAILED (nan={has_nan}, inf={has_inf}, norm={grad_norm:.3f}). "
                f"Applying strategy: '{self.config.on_invalid}'"
            )
        return is_ok