# path: ppo_library/ppo_system/learning/buffer.py
from __future__ import annotations
from typing import Dict, Optional
import torch
from torch import Tensor

class TrajectoryBuffer:
    """
    Time-major PPO буфер з GAE, оптимізований для векторизованих середовищ.

    Зберігає дані у форматі [T, N, ...], де T - довжина траєкторії (n_steps),
    а N - кількість паралельних середовищ (num_envs).

    Ключовий потік:
    1. store() - накопичує дані до заповнення (t == T).
    2. finalize(last_values) - явно викликається для розрахунку GAE.
    3. get() - повертає "сплющений" (flattened) батч для оновлення.
    """
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        n_envs: int,
        n_steps: int,
        gamma: float,
        gae_lambda: float,
        device: str | torch.device,
        is_continuous: bool,
    ) -> None:
        self.device = torch.device(device)
        self.T = int(n_steps)
        self.N = int(n_envs)
        self.gamma = float(gamma)
        self.lam = float(gae_lambda)
        self.is_continuous = bool(is_continuous)

        # Ініціалізація буферів у форматі [T, N, ...]
        self.obs = torch.zeros(self.T, self.N, obs_dim, dtype=torch.float32, device=self.device)
        act_shape = (self.T, self.N, action_dim) if is_continuous else (self.T, self.N, 1)
        self.act = torch.zeros(act_shape, dtype=torch.float32, device=self.device)
        self.rew = torch.zeros(self.T, self.N, dtype=torch.float32, device=self.device)
        self.val = torch.zeros(self.T, self.N, dtype=torch.float32, device=self.device)
        self.logp = torch.zeros(self.T, self.N, dtype=torch.float32, device=self.device)
        self.done = torch.zeros(self.T, self.N, dtype=torch.bool, device=self.device)

        # Буфери для GAE, заповнюються в finalize()
        self.adv = torch.zeros(self.T, self.N, dtype=torch.float32, device=self.device)
        self.ret = torch.zeros(self.T, self.N, dtype=torch.float32, device=self.device)

        self.t = 0  # Поточний крок у траєкторії
        self._finalized = False

    @property
    def full(self) -> bool:
        """Перевіряє, чи заповнений буфер."""
        return self.t >= self.T

    def clear(self) -> None:
        """Скидає вказівник, готуючи буфер до нового збору даних."""
        self.t = 0
        self._finalized = False

    def store(
        self,
        obs: Tensor,
        act: Tensor,
        rew: Tensor,
        val: Tensor,
        logp: Tensor,
        done: Tensor,
    ) -> None:
        """Зберігає один крок даних для всіх середовищ."""
        if self.full:
            raise RuntimeError("Buffer is full. Call finalize() and get() before storing more data.")

        # Валідація та збереження
        assert obs.shape[0] == self.N, f"Expected obs batch size {self.N}, got {obs.shape[0]}"

        self.obs[self.t] = obs
        self.act[self.t] = act.view(self.N, -1)
        self.rew[self.t] = rew
        self.val[self.t] = val
        self.logp[self.t] = logp
        self.done[self.t] = done

        self.t += 1
        self._finalized = False

    def finalize(self, last_values: Tensor) -> None:
        """
        Розраховує GAE та Returns для всіх зібраних траєкторій.
        Використовує `last_values` для bootstrap-оцінки в незавершених епізодах.

        Args:
            last_values (Tensor): Оцінка V(s_T) для кожного середовища, форма [N].
        """
        if self.t == 0:
            self._finalized = True
            return

        # Розрахунок GAE для кожного середовища окремо
        gae = torch.zeros(self.N, device=self.device)
        for t in reversed(range(self.t)):
            # Якщо епізод завершився на наступному кроці, next_val = 0
            # інакше, беремо оцінку з буфера.
            # Для останнього кроку (t=T-1), беремо last_values.
            next_non_terminal = 1.0 - self.done[t].float()
            next_values = self.val[t + 1] if t < self.t - 1 else last_values

            delta = self.rew[t] + self.gamma * next_values * next_non_terminal - self.val[t]
            gae = delta + self.gamma * self.lam * next_non_terminal * gae
            self.adv[t] = gae

        self.ret[:self.t] = self.adv[:self.t] + self.val[:self.t]
        self._finalized = True

    def get(self) -> Dict[str, Tensor]:
        """
        Повертає всі дані у вигляді "сплющеного" батча [T*N, ...].
        """
        if not self._finalized:
            raise RuntimeError("Buffer must be finalized with last_values before getting data.")
        if self.t == 0:
            raise RuntimeError("Buffer is empty, cannot get data.")

        # "Сплющуємо" дані з [T, N, ...] в [T*N, ...]
        num_samples = self.t * self.N

        obs = self.obs[:self.t].reshape(num_samples, -1)
        act = self.act[:self.t].reshape(num_samples, -1)
        if not self.is_continuous:
            act = act.squeeze(1).long()

        ret = self.ret[:self.t].reshape(num_samples)
        adv = self.adv[:self.t].reshape(num_samples)
        logp = self.logp[:self.t].reshape(num_samples)

        return {"obs": obs, "act": act, "ret": ret, "adv": adv, "logp": logp}