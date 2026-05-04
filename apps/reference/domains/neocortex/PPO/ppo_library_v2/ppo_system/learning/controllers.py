# QUARANTINED: legacy_runtime
# path: ppo_library/ppo_system/learning/controllers.py
from __future__ import annotations
__quarantined__ = True
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class AdaptiveKLController:
    """
    PID-подібний контролер для коефіцієнта KL-штрафу (beta).
    Мета: утримувати KL-дивергенцію біля цільового значення `target_kl`.
    """
    target_kl: float
    k_p: float = 0.1
    k_i: float = 0.01
    k_d: float = 0.01
    max_beta: float = 10.0

    _prev_err: float = 0.0
    _int_err: float = 0.0
    beta: float = 1.0

    def update(self, measured_kl: float) -> float:
        """Оновлює beta на основі виміряного KL та повертає нове значення."""
        err = measured_kl - self.target_kl
        self._int_err += err
        d_err = err - self._prev_err
        self._prev_err = err

        adjustment = self.k_p * err + self.k_i * self._int_err + self.k_d * d_err
        self.beta = max(0.0, min(self.max_beta, self.beta + adjustment))
        return self.beta

@dataclass
class EntropyScheduler:
    """Лінійний планувальник для коефіцієнта ентропії."""
    start: float
    end: float
    total_steps: int

    def value(self, step: int) -> float:
        """Повертає значення коефіцієнта для поточного кроку."""
        progress = min(1.0, step / max(1, self.total_steps))
        return self.start + (self.end - self.start) * progress

@dataclass
class PPOFallbackController:
    """
    Автоматично стабілізує навчання, пропонуючи знизити lr/clip_range
    при вибухах KL, та поступово відновлює їх до базових значень.
    """
    # Пороги спрацювання
    kl_high_threshold_mult: float = 2.0
    kl_low_threshold_mult: float = 0.5

    # Фактори зміни
    lr_decay_factor: float = 0.7
    lr_growth_factor: float = 1.02
    clip_decay_factor: float = 0.9
    clip_growth_factor: float = 1.01

    # Межі
    lr_min_multiplier: float = 0.1
    clip_min_value: float = 0.05

    # Параметри відновлення
    recover_patience: int = 10

    # Статистика для моніторингу
    stats: Dict[str, int] = field(default_factory=lambda: {
        "kl_high_events": 0,
        "recover_events": 0,
    })

    _recover_counter: int = 0
    _base_lr: float = 3e-4
    _base_clip: float = 0.2

    def attach(self, base_lr: float, base_clip: float):
        """Зберігає базові значення для відновлення."""
        self._base_lr = base_lr
        self._base_clip = base_clip

    def after_update(
        self, metrics: dict, current_lr: float, current_clip: float
    ) -> Dict[str, float]:
        """
        Аналізує метрики та повертає словник з пропозиціями змін, якщо вони потрібні.
        """
        approx_kl = metrics.get("approx_kl", 0.0)
        target_kl = metrics.get("target_kl", 0.0)
        suggestions = {}

        # 1. Аварійне зниження при вибуху KL
        if approx_kl > self.kl_high_threshold_mult * target_kl:
            self._recover_counter = 0
            self.stats["kl_high_events"] += 1

            new_lr = max(self._base_lr * self.lr_min_multiplier, current_lr * self.lr_decay_factor)
            new_clip = max(self.clip_min_value, current_clip * self.clip_decay_factor)

            suggestions = {"learning_rate": new_lr, "clip_range": new_clip, "event": "kl_high"}

        # 2. Поступове відновлення при стабільному KL
        elif approx_kl < self.kl_low_threshold_mult * target_kl:
            self._recover_counter += 1
            if self._recover_counter >= self.recover_patience:
                self._recover_counter = 0
                self.stats["recover_events"] += 1

                new_lr = min(self._base_lr, current_lr * self.lr_growth_factor)
                new_clip = min(self._base_clip, current_clip * self.clip_growth_factor)

                suggestions = {"learning_rate": new_lr, "clip_range": new_clip, "event": "recover"}
        else:
            # KL в нормі, скидаємо лічильник відновлення
            self._recover_counter = 0

        return suggestions