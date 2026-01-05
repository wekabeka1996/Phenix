# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

# FIX: Added missing imports: Optional, scipy.stats

import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import numpy as np
import scipy.stats

# --- Fallback mechanism if torch is not available ---
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.distributions import Normal
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from .config import EFEConfig
from .telemetry import Observation

log = logging.getLogger(__name__)

if not TORCH_AVAILABLE:
    log.critical("PyTorch is not installed. WorldModel will run in a DEGRADED fallback mode using EMA stats.")
    # --- Fallback Classes ---
    class WorldModel: # Mock
        def __init__(self, input_dim=6, latent_dim=6, alpha=0.1):
            self.input_dim = input_dim
            self.mu = np.zeros(latent_dim)
            self.sigma = np.ones(latent_dim)
            self.alpha = alpha # EMA smoothing factor
        
        def _obs_to_vec(self, obs: Observation) -> np.ndarray:
             return np.array([
                obs.gpu_temp_c, obs.gpu_util_pct, obs.gpu_mem_used_gb,
                obs.cpu_load_pct, obs.io_wait_pct, obs.fan_pct
            ])

        def update(self, obs: Observation):
            vec = self._obs_to_vec(obs)
            self.mu = self.alpha * vec + (1 - self.alpha) * self.mu
            # Simplified variance update
            self.sigma = np.sqrt(self.alpha * (vec - self.mu)**2 + (1 - self.alpha) * self.sigma**2)

        def predict(self, obs: Observation) -> Tuple[np.ndarray, np.ndarray]:
            return self.mu, self.sigma
        
        def save(self, path: Path): log.warning("Save is not supported in fallback mode.")
        def load(self, path: Path): log.warning("Load is not supported in fallback mode.")

else: # --- PyTorch Implementation ---
    class WorldModel(nn.Module):
        """A lightweight GRU-based predictive model over telemetry features.

        SPEC/R0-03: Upgrade path for WORLD — maintain an online-capable GRU
        predicting mean & scale (sigma) for next-step distribution. Ensemble
        uncertainty = epistemic (variance of means) + aleatoric (average sigma^2).
        """
        def __init__(self, input_dim: int = 6, latent_dim: int = 6, hidden_dim: int = 64):
            super().__init__()
            self.input_dim = input_dim
            self.latent_dim = latent_dim
            self.rnn = nn.GRU(input_dim, hidden_dim, batch_first=True)
            self.fc_out = nn.Linear(hidden_dim, latent_dim * 2) # For mu and log_sigma
            self.hidden: Optional[torch.Tensor] = None

        def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
            """
            Predicts the parameters of the next latent state distribution.
            Args:
                x: A tensor of shape (batch, seq_len, input_dim)
            Returns:
                A tuple of (mu, sigma) tensors.
            """
            rnn_out, self.hidden = self.rnn(x, self.hidden)
            # We only care about the last output for next-step prediction
            last_out = rnn_out[:, -1, :]
            params = self.fc_out(last_out)
            mu, log_sigma = torch.chunk(params, 2, dim=-1)
            sigma = torch.exp(log_sigma) + 1e-6 # Add epsilon for stability
            return mu, sigma

        def reset_hidden(self):
            self.hidden = None

class WorldEnsemble:
    """Manages an ensemble of WorldModels to estimate epistemic & aleatoric uncertainty.

    Added in R0-03 hardening:
    - predictive_stats(): aggregated mean, epistemic variance, aleatoric variance, total variance
    - mixture_nll(): log-prob under equally weighted mixture of ensemble components
    - save()/load() now persist optimizer state (where torch available)
    - reset(): clears hidden states for all members
    Design keeps a graceful fallback when torch not installed.
    """
    def __init__(self, config: EFEConfig, device: str = 'cpu'):
        self.k = config.ensemble_size
        self.device = torch.device(device) if TORCH_AVAILABLE else None
        self.input_dim = 6 # From telemetry features

        if not TORCH_AVAILABLE:
            self.models = [WorldModel() for _ in range(self.k)]
        else:
            self.models = [WorldModel(input_dim=self.input_dim).to(self.device) for _ in range(self.k)]
            self.optimizers = [optim.Adam(m.parameters(), lr=1e-4) for m in self.models]

    @staticmethod
    def _obs_to_tensor(obs: Observation, device: torch.device) -> torch.Tensor:
        features = torch.tensor([
            obs.gpu_temp_c, obs.gpu_util_pct, obs.gpu_mem_used_gb,
            obs.cpu_load_pct, obs.io_wait_pct, obs.fan_pct
        ], dtype=torch.float32, device=device)
        return features.view(1, 1, -1) # (batch=1, seq_len=1, features)

    def update(self, obs: Observation):
        """Performs a single online update step for each model in the ensemble."""
        if not TORCH_AVAILABLE:
            for model in self.models: model.update(obs)
            return

        x = self._obs_to_tensor(obs, self.device)
        for i, model in enumerate(self.models):
            model.train()
            self.optimizers[i].zero_grad()
            
            # Predict based on the previous state, then compute loss on the new one
            mu, sigma = model(x)
            dist = Normal(mu, sigma)
            
            # For online learning, the target is the observation itself.
            # The loss encourages the model to predict a distribution where the
            # current observation is likely.
            # This is a simplification; a better approach uses sequences.
            target = x.squeeze(1)
            loss = -dist.log_prob(target).mean()
            
            loss.backward()
            self.optimizers[i].step()

    def _predict(self, obs: Observation) -> List[Tuple[torch.Tensor, torch.Tensor]]:
        """Gets predictions from all models in the ensemble."""
        if not TORCH_AVAILABLE:
            return [m.predict(obs) for m in self.models]

        x = self._obs_to_tensor(obs, self.device)
        predictions = []
        with torch.no_grad():
            for model in self.models:
                model.eval()
                mu, sigma = model(x)
                predictions.append((mu.squeeze(), sigma.squeeze()))
        return predictions

    def nll(self, obs: Observation) -> float:
        """Calculates the average negative log-likelihood (surprisal)."""
        predictions = self._predict(obs)
        if not TORCH_AVAILABLE:
            # Fallback NLL calculation
            x = self.models[0]._obs_to_vec(obs)
            nlls = [-np.sum(scipy.stats.norm.logpdf(x, loc=mu, scale=sigma)) for mu, sigma in predictions]
            return float(np.mean(nlls))
            
        x_target = self._obs_to_tensor(obs, self.device).squeeze()
        nlls = []
        for mu, sigma in predictions:
            dist = Normal(mu, sigma)
            nll = -dist.log_prob(x_target).sum().item()
            nlls.append(nll)
        return float(np.mean(nlls))

    def mixture_nll(self, obs: Observation) -> float:
        """Negative log-likelihood under mixture of ensemble components.

        For torch path: mixture log p(x) = log(1/K * sum_i exp(log p_i(x))).
        Returns: scalar NLL. Falls back to average NLL if numerical underflow or fallback mode.
        """
        if not TORCH_AVAILABLE:
            return self.nll(obs)
        predictions = self._predict(obs)
        x_target = self._obs_to_tensor(obs, self.device).squeeze()
        logps = []
        for mu, sigma in predictions:
            dist = Normal(mu, sigma)
            logp = dist.log_prob(x_target).sum().item()
            logps.append(logp)
        logps_arr = np.array(logps, dtype=np.float64)
        # logsumexp
        m = logps_arr.max()
        mixture_logp = m + np.log(np.mean(np.exp(logps_arr - m)))
        if not np.isfinite(mixture_logp):
            return self.nll(obs)
        return float(-mixture_logp)

    def predictive_stats(self, obs: Observation) -> Dict[str, Any]:
        """Aggregated predictive statistics over ensemble.

        Returns dict with keys:
          mu_mean: np.ndarray (D,)
          epistemic_var: np.ndarray (D,) variance of means
          aleatoric_var: np.ndarray (D,) mean of sigma^2
          total_var: np.ndarray (D,) sum
          avg_sigma: np.ndarray (D,) mean sigma
          avg_nll: float average member NLL
          mixture_nll: float mixture model NLL
        Fallback mode: approximated using simple EMA stats.
        """
        if not TORCH_AVAILABLE:
            # Derive simple stats from fallback models
            mus = [m.mu for m in self.models]
            sigmas = [m.sigma for m in self.models]
            mus_stack = np.stack(mus)
            sig_stack = np.stack(sigmas)
            mu_mean = mus_stack.mean(axis=0)
            epistemic_var = mus_stack.var(axis=0)
            aleatoric_var = (sig_stack ** 2).mean(axis=0)
            total_var = epistemic_var + aleatoric_var
            return {
                "mu_mean": mu_mean,
                "epistemic_var": epistemic_var,
                "aleatoric_var": aleatoric_var,
                "total_var": total_var,
                "avg_sigma": sig_stack.mean(axis=0),
                "avg_nll": self.nll(obs),
                "mixture_nll": self.nll(obs)
            }
        # Torch path
        preds = self._predict(obs)
        mus = torch.stack([p[0] for p in preds])  # (K,D)
        sigmas = torch.stack([p[1] for p in preds])  # (K,D)
        mu_mean = mus.mean(dim=0)
        epistemic_var = mus.var(dim=0, unbiased=False)
        aleatoric_var = (sigmas ** 2).mean(dim=0)
        total_var = epistemic_var + aleatoric_var
        stats = {
            "mu_mean": mu_mean.detach().cpu().numpy(),
            "epistemic_var": epistemic_var.detach().cpu().numpy(),
            "aleatoric_var": aleatoric_var.detach().cpu().numpy(),
            "total_var": total_var.detach().cpu().numpy(),
            "avg_sigma": sigmas.mean(dim=0).detach().cpu().numpy(),
            "avg_nll": self.nll(obs),
            "mixture_nll": self.mixture_nll(obs)
        }
        return stats

    def disagreement(self, obs: Observation) -> float:
        """Calculates the disagreement among the ensemble (variance of means)."""
        predictions = self._predict(obs)
        mus = [p[0] for p in predictions]
        
        if not TORCH_AVAILABLE:
            mus_stack = np.stack(mus)
        else:
            mus_stack = torch.stack(mus).detach().cpu().numpy()
            
        # Variance of the predicted means across the ensemble
        disagreement = mus_stack.var(axis=0).mean().item()
        return float(disagreement)

    def save(self, log_dir: Path):
        """Saves the state of all models in the ensemble."""
        if not TORCH_AVAILABLE:
            return
        log_dir.mkdir(parents=True, exist_ok=True)
        for i, model in enumerate(self.models):
            torch.save({
                "model": model.state_dict(),
                "optimizer": self.optimizers[i].state_dict()
            }, log_dir / f"world_{i}.pt")
        log.info(f"World ensemble saved to {log_dir}")

    def load(self, log_dir: Path):
        """Loads the state for all models from a directory."""
        if not TORCH_AVAILABLE:
            return
        log.info(f"Attempting to load world ensemble from {log_dir}")
        for i, model in enumerate(self.models):
            path = log_dir / f"world_{i}.pt"
            if path.exists():
                ckpt = torch.load(path, map_location=self.device)
                if isinstance(ckpt, dict) and "model" in ckpt:
                    model.load_state_dict(ckpt["model"])
                    if "optimizer" in ckpt:
                        try:
                            self.optimizers[i].load_state_dict(ckpt["optimizer"])
                        except Exception:  # pragma: no cover
                            log.warning(f"Optimizer state load failed for model {i}")
                else:  # legacy plain state_dict
                    model.load_state_dict(ckpt)
                log.info(f"Loaded world model {i} from {path}")
            else:
                log.warning(f"World model {i} not found at {path}, using random initialization.")

    def reset(self):
        """Reset hidden state for all ensemble members."""
        if not TORCH_AVAILABLE:
            return
        for m in self.models:
            m.reset_hidden()

# Example Usage
if __name__ == '__main__':
    if not TORCH_AVAILABLE:
        print("Running WorldModel in FALLBACK mode.")
    
    from .telemetry import Telemetry
    from .config import EFEConfig
    
    cfg = EFEConfig()
    world = WorldEnsemble(cfg)
    telemetry = Telemetry(mock_mode=True)
    
    print("\n--- Updating World Ensemble for 10 steps ---")
    for i in range(10):
        obs = telemetry.poll()
        world.update(obs)
        if i % 2 == 0:
            nll_val = world.nll(obs)
            dis_val = world.disagreement(obs)
            print(f"Step {i}: NLL={nll_val:.2f}, Disagreement={dis_val:.4f}")

    print("\n--- Final prediction ---")
    final_obs = telemetry.poll()
    nll_val = world.nll(final_obs)
    dis_val = world.disagreement(final_obs)
    print(f"NLL={nll_val:.2f}, Disagreement={dis_val:.4f}")
    
    world.save(Path("logs"))
    
    new_world = WorldEnsemble(cfg)
    new_world.load(Path("logs"))
    print("\n--- Loaded World prediction ---")
    nll_val = new_world.nll(final_obs)
    dis_val = new_world.disagreement(final_obs)
    print(f"NLL={nll_val:.2f}, Disagreement={dis_val:.4f} (should be same as above)")