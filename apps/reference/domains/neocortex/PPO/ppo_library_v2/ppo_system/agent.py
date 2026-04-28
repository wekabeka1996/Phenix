# QUARANTINED: legacy_runtime
# path: ppo_library/ppo_system/agent.py
__quarantined__ = True
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import numpy as np
import torch
from torch import Tensor

from .core.dataclasses import AgentConfig, TrainConfig
from .learning.buffer import TrajectoryBuffer
from .learning.updater import PolicyUpdater
from .learning.controllers import AdaptiveKLController, EntropyScheduler, PPOFallbackController
from .models.actor_critic_lstm import ActorCriticLSTM
from .utils.safety import NumericalSafetyManager
from .utils.seed import set_global_seed


class PPOAgent:
    """
    Головний клас-фасад для PPO-агента.
    - Ініціалізується з конфігурацій та середовища (або його спейсів).
    - Координує роботу моделі, буфера, апдейтера та контролерів.
    - Надає простий API: act(), store(), update().
    - Керує станом LSTM для векторизованих середовищ.
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        train_config: TrainConfig,
        observation_space: Any,
        action_space: Any,
        num_envs: int = 1,
    ):
        self.agent_cfg = agent_config
        self.train_cfg = train_config
        set_global_seed(self.train_cfg.seed)
        self.device = torch.device(self.train_cfg.device)
        self.num_envs = num_envs

        # Визначення розмірностей зі спейсів середовища
        obs_dim = int(np.prod(observation_space.shape))
        if hasattr(action_space, "n"):
            action_dim = int(action_space.n)
            is_continuous = False
        elif hasattr(action_space, "shape"):
            action_dim = int(np.prod(action_space.shape))
            is_continuous = True
        else:
            raise ValueError("Unsupported action space type.")

        # --- Ініціалізація Компонентів ---
        self.model = ActorCriticLSTM(
            obs_dim=obs_dim,
            action_dim=action_dim,
            hidden_size=self.agent_cfg.hidden_size,
            lstm_layers=self.agent_cfg.lstm_layers,
            continuous_head=self.agent_cfg.continuous_head,
            log_std_init=self.agent_cfg.log_std_init,
            temperature=self.agent_cfg.temperature,
            sigma_min=self.agent_cfg.sigma_min,
        ).to(self.device)

        self.is_continuous = self.model.is_continuous

        self.buffer = TrajectoryBuffer(
            obs_dim=obs_dim,
            action_dim=action_dim if self.is_continuous else 1,
            n_envs=self.num_envs,
            n_steps=self.train_cfg.n_steps,
            gamma=self.agent_cfg.gamma,
            gae_lambda=self.agent_cfg.gae_lambda,
            device=self.device,
            is_continuous=self.is_continuous,
        )

        self.optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.agent_cfg.learning_rate, eps=1e-8)

        self.safety = NumericalSafetyManager(
            self.agent_cfg.numerical_safety) if self.agent_cfg.numerical_safety else None
        self.updater = PolicyUpdater(config=self.agent_cfg, safety=self.safety)

        # --- Контролери (опціональні) ---
        self.kl_controller = AdaptiveKLController(
            target_kl=self.agent_cfg.target_kl) if self.agent_cfg.target_kl else None
        # Можна додати логіку ініціалізації
        self.entropy_scheduler: Optional[EntropyScheduler] = None
        self.fallback_controller = PPOFallbackController()
        self.fallback_controller.attach(
            base_lr=self.agent_cfg.learning_rate, base_clip=self.agent_cfg.clip_range)

        # --- Стан LSTM ---
        self._hidden = self.model.init_hidden(self.num_envs, self.device)

    @classmethod
    def from_env(cls, agent_config: AgentConfig, train_config: TrainConfig, env: Any) -> PPOAgent:
        """Фабричний метод для зручної ініціалізації з об'єкта середовища."""
        num_envs = getattr(env, "num_envs", 1)
        return cls(agent_config, train_config, env.observation_space, env.action_space, num_envs)

    def _ensure_hidden_shape(self, batch_size: int):
        """Перевіряє та за потреби змінює розмір прихованого стану LSTM."""
        h, c = self._hidden
        if h.size(1) != batch_size:
            self._hidden = self.model.init_hidden(batch_size, self.device)

    @torch.no_grad()
    def act(self, obs: np.ndarray, deterministic: bool = False) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Генерує дію, оцінку стану та log_prob для поточного спостереження.
        Підтримує як одиночні, так і батчові спостереження.
        """
        self.model.eval()
        x = torch.as_tensor(obs, dtype=torch.float32, device=self.device)
        x = torch.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        is_batched = x.dim() > 1
        if not is_batched:
            x = x.unsqueeze(0)

        self._ensure_hidden_shape(x.shape[0])
        dist, value, self._hidden = self.model(x, self._hidden)

        if deterministic:
            if hasattr(dist, "base_dist"):  # Squashed Gaussian
                action = dist.base_dist.mean
            else:  # Gaussian or Categorical
                action = dist.mean if self.is_continuous else torch.argmax(
                    dist.logits, dim=-1)
        else:
            action = dist.sample()

        logp = dist.log_prob(action)
        if logp.dim() > 1 and action.dim() > 1:
            logp = logp.sum(dim=-1)

        # Повертаємо numpy масиви, знімаючи batch-вимір, якщо його не було на вході
        action_np = action.cpu().numpy()
        value_np = value.squeeze(-1).cpu().numpy()
        logp_np = logp.cpu().numpy()

        if not is_batched:
            return action_np[0], value_np[0], logp_np[0]
        return action_np, value_np, logp_np

    @torch.no_grad()
    def value(self, obs: np.ndarray) -> np.ndarray:
        """Розраховує тільки оцінку стану (V-функцію), не змінюючи прихований стан LSTM."""
        self.model.eval()
        x = torch.as_tensor(obs, dtype=torch.float32, device=self.device)
        is_batched = x.dim() > 1
        if not is_batched:
            x = x.unsqueeze(0)

        self._ensure_hidden_shape(x.shape[0])
        _, value, _ = self.model(x, self._hidden)  # _hidden не оновлюється

        value_np = value.squeeze(-1).cpu().numpy()
        return value_np if is_batched else value_np[0]

    def reset_hidden(self, done_mask: np.ndarray | torch.Tensor):
        """Обнуляє прихований стан для середовищ, які завершили епізод."""
        dm = torch.as_tensor(done_mask, dtype=torch.bool,
                             device=self.device).flatten()
        h, c = self._hidden
        h[:, dm, :] = 0.0
        c[:, dm, :] = 0.0
        self._hidden = (h, c)

    def store(self, obs: Tensor, act: Tensor, rew: Tensor, val: Tensor, logp: Tensor, done: Tensor):
        """Зберігає крок досвіду в буфер."""
        self.buffer.store(obs, act, rew, val, logp, done)

    def update(self) -> Dict[str, float]:
        """
        Виконує повний цикл оновлення політики на даних, зібраних у буфері.
        """
        self.model.train()
        batch_data = self.buffer.get()
        metrics = self.updater.update(self.model, self.optimizer, batch_data)

        # Важливо: від'єднуємо hidden state від графу після оновлення,
        # щоб не тягнути градієнти з минулих траєкторій.
        self._hidden = (self._hidden[0].detach(), self._hidden[1].detach())

        return metrics
