# path: ppo_library/ppo_system/models/actor_critic_lstm.py
from __future__ import annotations
import math
from typing import Tuple, Union, Optional
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical, Normal, TransformedDistribution
from torch.distributions.transforms import TanhTransform, AffineTransform
from .base_model import BaseActorCritic

class ActorCriticLSTM(BaseActorCritic):
    """
    Конкретна реалізація моделі з LSTM-бекбоном.
    - Повертає готовий об'єкт розподілу.
    - Підтримує дискретні, Gaussian та Squashed Gaussian (для дій в [-1, 1]) розподіли.
    """
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_size: int,
        lstm_layers: int,
        continuous_head: str,
        log_std_init: float,
        temperature: float,
        sigma_min: float,
    ) -> None:
        super().__init__()
        self.is_continuous = continuous_head in ("gaussian", "squashed_gaussian")
        self.squash_output = continuous_head == "squashed_gaussian"

        self.lstm_layers = lstm_layers
        self.hidden_size = hidden_size

        # Feature extractor
        self.fc_in = nn.Linear(obs_dim, hidden_size)
        self.layer_norm_in = nn.LayerNorm(hidden_size)

        # Recurrent core
        self.lstm = nn.LSTM(hidden_size, hidden_size, num_layers=lstm_layers, batch_first=True)
        self.layer_norm_lstm = nn.LayerNorm(hidden_size)

        # Heads
        if self.is_continuous:
            self.mu_head = nn.Linear(hidden_size, action_dim)
            self.log_std = nn.Parameter(torch.full((action_dim,), log_std_init))
            self.sigma_min = sigma_min
        else:
            self.logits_head = nn.Linear(hidden_size, action_dim)
            self.temperature = temperature

        self.value_head = nn.Linear(hidden_size, 1)
        self._orthogonal_init()

    def _orthogonal_init(self):
        for name, p in self.named_parameters():
            if "weight" in name and p.dim() >= 2:
                nn.init.orthogonal_(p, gain=math.sqrt(2))
            elif "bias" in name:
                nn.init.constant_(p, 0)

    def init_hidden(
        self, batch_size: int, device: Union[str, torch.device]
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        h = torch.zeros(self.lstm_layers, batch_size, self.hidden_size, device=device)
        c = torch.zeros_like(h)
        return h, c

    def _get_dist(self, latent_features: torch.Tensor) -> Distribution:
        """Створює об'єкт розподілу на основі латентних фіч."""
        if self.is_continuous:
            mu = self.mu_head(latent_features)
            log_std = torch.clamp(self.log_std, min=math.log(self.sigma_min))
            std = log_std.exp()
            base_dist = Normal(mu, std)

            if self.squash_output:
                # TanhTransform перетворює вихід Normal(μ, σ) в діапазон [-1, 1]
                return TransformedDistribution(base_dist, [TanhTransform(cache_size=1)])
            return base_dist
        else:
            logits = self.logits_head(latent_features) / max(1e-8, self.temperature)
            return Categorical(logits=logits)

    def forward(
        self,
        x: torch.Tensor,
        hidden: Optional[Tuple[torch.Tensor, torch.Tensor]] = None
    ) -> Tuple[Distribution, torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:

        # Вхідний x може бути [Batch, Obs] або [Batch, Seq, Obs]
        # Для LSTM нам потрібен [Batch, Seq, Obs]
        if x.dim() == 2:
            x = x.unsqueeze(1) # [B, O] -> [B, 1, O]

        # Feature extraction
        z = self.layer_norm_in(F.relu(self.fc_in(x)))

        # LSTM core
        if hidden is None:
            hidden = self.init_hidden(x.size(0), x.device)

        # Detach hidden state to prevent gradients from flowing through entire history
        detached_hidden = (hidden[0].detach(), hidden[1].detach())
        z, new_hidden = self.lstm(z, detached_hidden)

        z = self.layer_norm_lstm(z)

        # Використовуємо вихід останнього кроку послідовності
        last_step_features = z[:, -1]

        # Створюємо розподіл та оцінку
        action_dist = self._get_dist(last_step_features)
        value = self.value_head(last_step_features)

        return action_dist, value, new_hidden