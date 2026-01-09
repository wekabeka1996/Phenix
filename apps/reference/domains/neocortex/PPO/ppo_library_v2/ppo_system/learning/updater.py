# path: ppo_library/ppo_system/learning/updater.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional
import torch
import torch.nn.functional as F
from torch.distributions import Distribution
from torch.optim import Optimizer

from ..core.dataclasses import AgentConfig
from ..utils.safety import NumericalSafetyManager
from ..models.base_model import BaseActorCritic


@dataclass
class PolicyUpdater:
    """
    Інкапсулює всю логіку оновлення політики PPO.
    - Працює з "сплющеним" батчем даних [T*N, ...].
    - Виконує цикл по епохах та мікробатчах.
    - Використовує NumericalSafetyManager для всіх критичних обчислень.
    - Повертає усереднені метрики за всі кроки оновлення.
    """
    config: AgentConfig
    safety: Optional[NumericalSafetyManager] = None

    def _get_logp_and_entropy(
        self, dist: Distribution, actions: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Розраховує log_prob та ентропію з об'єкта розподілу."""
        logp = dist.log_prob(actions)

        # Для багатовимірних неперервних дій, log_prob має форму [Batch, ActionDim].
        # Нам потрібно просумувати їх, щоб отримати log_prob для всієї дії.
        if logp.dim() > 1 and actions.dim() > 1:
            logp = logp.sum(dim=-1)

        entropy = dist.entropy()
        # Аналогічно, ентропія може бути покомпонентною.
        if entropy.dim() > 1:
            entropy = entropy.sum(dim=-1)

        return logp, entropy.mean()

    def _get_minibatches(self, batch_data: Dict[str, torch.Tensor]):
        """Генератор мікробатчів."""
        num_samples = batch_data["obs"].shape[0]
        indices = torch.randperm(num_samples, device=batch_data["obs"].device)

        for start in range(0, num_samples, self.config.batch_size):
            end = start + self.config.batch_size
            mb_indices = indices[start:end]
            yield {key: value[mb_indices] for key, value in batch_data.items()}

    def update(
        self,
        model: BaseActorCritic,
        optimizer: Optimizer,
        batch_data: Dict[str, torch.Tensor],
    ) -> Dict[str, float]:
        """
        Виконує повний цикл оновлення PPO (епохи та мікробатчі).
        """
        cfg = self.config
        # Нормалізуємо advantages один раз для всього батча
        adv = batch_data["adv"]
        batch_data["adv"] = (adv - adv.mean()) / (adv.std() + 1e-8)

        # Словник для агрегації метрик
        metrics_agg = {
            "loss": 0.0, "policy_loss": 0.0, "value_loss": 0.0,
            "entropy": 0.0, "approx_kl": 0.0, "grad_norm": 0.0,
        }
        total_updates = 0

        for _ in range(cfg.epochs):
            for mb in self._get_minibatches(batch_data):
                obs, act, ret, adv, logp_old = mb["obs"], mb["act"], mb["ret"], mb["adv"], mb["logp"]

                # Forward pass
                dist, value, _ = model(obs)
                logp, entropy = self._get_logp_and_entropy(dist, act)

                # --- PPO Loss Calculation ---

                # 1. Importance Sampling Ratio (з захистом)
                ratio = self.safety.safe_ratio(logp, logp_old) if self.safety else (logp - logp_old).exp()

                # 2. Policy (Surrogate) Loss
                unclipped_loss = -adv * ratio
                clipped_loss = -adv * torch.clamp(ratio, 1.0 - cfg.clip_range, 1.0 + cfg.clip_range)
                policy_loss = torch.max(unclipped_loss, clipped_loss).mean()

                # 3. Value Loss
                value_loss = F.mse_loss(value.squeeze(-1), ret)

                # 4. Total Loss
                loss = policy_loss + cfg.value_loss_coef * value_loss - cfg.entropy_coef * entropy

                # --- Optimization Step ---
                optimizer.zero_grad()
                loss.backward()
                grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.max_grad_norm).item()

                # --- Gradient Safety Check ---
                should_step = True
                if self.safety:
                    is_ok = self.safety.validate_gradients(model, grad_norm)
                    if not is_ok:
                        strategy = self.safety.config.on_invalid
                        if strategy == "zero_grads":
                            optimizer.zero_grad() # Обнуляємо невалідні градієнти
                            self.safety.stats["zeroed_grads"] += 1
                        elif strategy == "sanitize":
                            for p in model.parameters():
                                if p.grad is not None:
                                    p.grad.data = torch.nan_to_num(p.grad.data, 0.0, 0.0, 0.0)
                            self.safety.stats["sanitized_grads"] += 1
                        elif strategy == "skip_step":
                            should_step = False
                            self.safety.stats["skipped_steps"] += 1

                if should_step:
                    optimizer.step()

                # --- Metrics Aggregation ---
                with torch.no_grad():
                    approx_kl = self.safety.safe_kl(logp, logp_old) if self.safety else 0.5 * ((logp - logp_old)**2).mean().item()

                metrics_agg["loss"] += loss.item()
                metrics_agg["policy_loss"] += policy_loss.item()
                metrics_agg["value_loss"] += value_loss.item()
                metrics_agg["entropy"] += entropy.item()
                metrics_agg["approx_kl"] += approx_kl
                metrics_agg["grad_norm"] += grad_norm
                total_updates += 1

        # Усереднюємо метрики за всі мікробатчі та епохи
        return {key: value / max(1, total_updates) for key, value in metrics_agg.items()}