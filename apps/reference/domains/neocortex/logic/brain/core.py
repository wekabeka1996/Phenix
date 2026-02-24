"""
Brain Core

Orchestrator for the Neocortex Neural Architecture.
Unifies VAE (Representation), World Model (Dynamics), and PPO (Decision).

Phase 4: Added checkpointing and PPO integration.
"""

from apps.reference.domains.neocortex.logic.brain.world_model import WorldModel
from apps.reference.domains.neocortex.logic.brain.vae import VariationalAutoencoder
from apps.reference.domains.neocortex.config_models import NeuroConfig
from typing import Dict, Any, Optional
from pathlib import Path
import logging
import numpy as np
import sys
import time

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

    class torch:
        Tensor = object

        class cuda:
            def is_available(): return False

        class optim:
            Adam = object

# Add PPO library to path
PPO_PATH = Path(__file__).parent.parent.parent / "PPO" / "ppo_library_v2"
if PPO_PATH.exists():
    sys.path.insert(0, str(PPO_PATH))
    HAS_PPO = True
else:
    HAS_PPO = False


logger = logging.getLogger(__name__)


class MockSpace:
    """Mock gym space for PPO initialization."""

    def __init__(self, shape):
        self.shape = shape
        self.n = None  # For discrete spaces


class MockDiscreteSpace:
    """Mock discrete action space."""

    def __init__(self, n):
        self.n = n
        self.shape = (n,)


class BrainCore:
    """
    Main Neural System.
    Phase 4: With PPO decision head and checkpointing.
    """

    def __init__(self, config: NeuroConfig, device: str = None, rng_seed: int = 0):
        self.config = config
        self._torch_available = HAS_TORCH
        self.device = self._resolve_device(device)
        self._train_steps = 0
        self.rng_seed = int(rng_seed)
        self._nonfinite_action_events = 0
        self._last_nonfinite_warn_ts = 0.0
        self._model_corrupted = False

        logger.info(f"Initializing BrainCore on device: {self.device}")

        if not self._torch_available:
            logger.warning(
                "PyTorch not available; BrainCore running in no-torch mock mode (VAE/WM/PPO disabled)")
            self.vae = None
            self.vae_opt = None
            self.world_model = None
            self.wm_opt = None
            self.ppo_agent = None
            return

        # 1. Representation Learning (VAE)
        self.vae = VariationalAutoencoder(config.vae).to(self.device)
        self.vae_opt = torch.optim.Adam(
            self.vae.parameters(),
            lr=config.vae.learning_rate
        )

        # 2. Dynamics Learning (World Model)
        self.world_model = WorldModel(
            config.world_model,
            input_dim=config.vae.latent_dim,
            action_dim=0
        ).to(self.device)

        self.wm_opt = torch.optim.Adam(
            self.world_model.parameters(),
            lr=config.world_model.learning_rate
        )

        # 3. Decision Making (PPO) - Optional
        self.ppo_agent = None
        self._init_ppo()

        self.vae.train()
        self.world_model.train()

    def _warn_nonfinite_action(self, reason: str) -> None:
        """
        Rate-limit repetitive PPO action warnings to avoid log spam under instability.
        """
        self._nonfinite_action_events += 1
        now = time.time()
        if now - self._last_nonfinite_warn_ts < 10.0:
            return
        logger.warning(
            "Non-finite PPO action output detected (%s); returning FLAT fallback [events=%s]",
            reason,
            self._nonfinite_action_events,
        )
        self._last_nonfinite_warn_ts = now
        self._nonfinite_action_events = 0

    def _resolve_device(self, requested_device: Optional[str]) -> str:
        """
        Resolve runtime device with fail-safe CPU fallback.

        Behavior:
        - If torch missing: always CPU (with warning).
        - If CUDA requested but unavailable: fall back to CPU (with warning).
        - If no request: auto-select CUDA when available, else CPU (with warning on CPU).
        """
        if not self._torch_available:
            logger.warning("PyTorch unavailable, forcing CPU mode")
            return "cpu"

        cuda_available = bool(torch.cuda.is_available())
        requested = (requested_device or "").strip().lower()

        if requested:
            if requested.startswith("cuda") and not cuda_available:
                logger.warning(
                    "GPU requested (%s) but CUDA is unavailable; falling back to CPU",
                    requested_device,
                )
                return "cpu"
            if requested in ("cpu", "cuda"):
                if requested == "cpu":
                    logger.warning(
                        "Running Neocortex on CPU (GPU disabled/not requested)")
                return requested
            # Unknown explicit device string: use as-is and let torch validate downstream.
            return requested

        if cuda_available:
            return "cuda"

        logger.warning("GPU not detected; running Neocortex on CPU")
        return "cpu"

    def _init_ppo(self):
        """Initialize PPO Agent if library is available."""
        if not self._torch_available:
            logger.warning(
                "PyTorch not available; skipping PPO initialization")
            return
        if not HAS_PPO:
            logger.warning("PPO library not found, shadow intents disabled")
            return

        try:
            from ppo_system.agent import PPOAgent
            from ppo_system.core.dataclasses import AgentConfig, TrainConfig
            from ppo_system.learning.controllers import EntropyScheduler
            from ppo_system.utils.safety import SafetyConfig

            # Create configs from NeuroConfig.ppo
            ppo_cfg = self.config.ppo
            safety_cfg = getattr(ppo_cfg, "numerical_safety", None)

            def _is_numeric(v: Any) -> bool:
                return isinstance(v, (int, float)) and not isinstance(v, bool)

            def _safe_float(v: Any, default: float) -> float:
                return float(v) if _is_numeric(v) and np.isfinite(v) else default

            def _safe_int(v: Any, default: int) -> int:
                return int(v) if _is_numeric(v) and int(v) > 0 else default

            safety_on_invalid = getattr(safety_cfg, "on_invalid", "sanitize")
            if safety_on_invalid not in {"zero_grads", "skip_step", "sanitize"}:
                safety_on_invalid = "sanitize"

            agent_config = AgentConfig(
                learning_rate=ppo_cfg.learning_rate,
                gamma=ppo_cfg.gamma,
                gae_lambda=ppo_cfg.gae_lambda,
                clip_range=ppo_cfg.clip_epsilon,
                entropy_coef=_safe_float(getattr(ppo_cfg, "entropy_coef", 0.01), 0.01),
                max_grad_norm=_safe_float(getattr(ppo_cfg, "max_grad_norm", 0.5), 0.5),
                hidden_size=ppo_cfg.hidden_dims[0] if ppo_cfg.hidden_dims else 64,
                epochs=ppo_cfg.num_epochs,
                batch_size=ppo_cfg.minibatch_size,
                continuous_head="categorical",  # Force discrete action space
                numerical_safety=SafetyConfig(
                    gradient_clip_threshold=_safe_float(
                        getattr(safety_cfg, "gradient_clip_threshold", 1.0), 1.0
                    ),
                    on_invalid=safety_on_invalid,
                ),
            )

            train_config = TrainConfig(
                n_steps=ppo_cfg.rollout_length,
                device=self.device,
                seed=self.rng_seed,
            )

            # Create mock spaces
            # Input: VAE latent dimension
            # Output: Discrete actions (LONG=0, SHORT=1, FLAT=2)
            obs_space = MockSpace(shape=(self.config.vae.latent_dim,))
            act_space = MockDiscreteSpace(n=ppo_cfg.action_dim)

            self.ppo_agent = PPOAgent(
                agent_config=agent_config,
                train_config=train_config,
                observation_space=obs_space,
                action_space=act_space,
                num_envs=1
            )

            entropy_schedule_cfg = getattr(ppo_cfg, "entropy_schedule", None)
            if entropy_schedule_cfg is not None:
                start = getattr(entropy_schedule_cfg, "start", None)
                end = getattr(entropy_schedule_cfg, "end", None)
                total_steps = getattr(entropy_schedule_cfg, "total_steps", None)

                if _is_numeric(start) and _is_numeric(end) and _is_numeric(total_steps):
                    self.ppo_agent.entropy_scheduler = EntropyScheduler(
                        start=_safe_float(start, 0.20),
                        end=_safe_float(end, 0.01),
                        total_steps=_safe_int(total_steps, 5000),
                    )
                else:
                    logger.warning(
                        "Ignoring invalid entropy_schedule config; expected numeric start/end/total_steps"
                    )

            logger.info(
                f"✓ PPO Agent initialized (Actions: {ppo_cfg.action_dim})")

        except ImportError as e:
            logger.warning(
                f"PPO import failed (likely missing torch deps): {e}")
            self.ppo_agent = None
        except Exception as e:
            logger.warning(f"PPO initialization failed: {e}")
            self.ppo_agent = None

    def train_batch(
        self,
        batch_obs: torch.Tensor,
        regime_targets: Optional[torch.Tensor] = None,
    ) -> Dict[str, float]:
        """
        Perform one training step on a sequential batch of observations.
        """
        if not self._torch_available:
            return {"error": "torch_missing", "vae_loss": float('nan'), "wm_loss": float('nan')}

        if batch_obs.device != self.device:
            batch_obs = batch_obs.to(self.device)

        if batch_obs.dtype != torch.float32:
            batch_obs = batch_obs.float()

        # A. VAE TRAINING
        self.vae_opt.zero_grad()

        recon_x, mu, logvar = self.vae(batch_obs)

        aux_cfg = getattr(self.config.vae, "regime_aux", None)
        aux_enabled = bool(aux_cfg and getattr(aux_cfg, "enabled", False))
        aux_alpha = float(getattr(aux_cfg, "alpha", 0.0)
                          ) if aux_enabled else 0.0
        regime_logits = None
        if aux_enabled and regime_targets is not None and regime_targets.numel() == mu.shape[0]:
            regime_logits = self.vae.predict_regime_logits(mu)
            if regime_targets.device != self.device:
                regime_targets = regime_targets.to(self.device)
            if regime_targets.dtype != torch.long:
                regime_targets = regime_targets.long()

        vae_losses = self.vae.loss_function(
            recon_x, batch_obs, mu, logvar,
            beta=self.config.vae.beta,
            regime_logits=regime_logits,
            regime_targets=regime_targets,
            aux_alpha=aux_alpha,
        )

        vae_loss = vae_losses['loss']
        vae_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.vae.parameters(), max_norm=1.0)
        self.vae_opt.step()

        # B. WORLD MODEL TRAINING
        with torch.no_grad():
            mu_enc, logvar_enc = self.vae.encode(batch_obs)
            z = mu_enc if self.config.vae.use_mean else self.vae.reparameterize(
                mu_enc, logvar_enc)

        if z.shape[0] < 2:
            return {
                "vae_loss": vae_loss.item(),
                "vae_mse": vae_losses['mse'].item(),
                "vae_kld": vae_losses['kld'].item(),
                "vae_regime_ce": vae_losses['regime_ce'].item(),
                "wm_loss": 0.0
            }

        self.wm_opt.zero_grad()

        # Treat the batch as a single sequence: (B, D) -> (1, Seq=B, D)
        z_seq = z.unsqueeze(0)
        z_in_seq = z_seq[:, :-1, :]
        z_target_seq = z_seq[:, 1:, :]

        z_pred_seq, _ = self.world_model(z_in_seq)

        wm_loss = torch.nn.functional.mse_loss(
            z_pred_seq, z_target_seq, reduction="mean")

        wm_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            self.world_model.parameters(), max_norm=1.0)
        self.wm_opt.step()

        self._train_steps += 1

        return {
            "vae_loss": vae_loss.item(),
            "vae_mse": vae_losses['mse'].item(),
            "vae_kld": vae_losses['kld'].item(),
            "vae_regime_ce": vae_losses['regime_ce'].item(),
            "wm_loss": wm_loss.item()
        }

    def _train_vae_aux_from_episodes(self, episodes: list[Dict[str, Any]]) -> Dict[str, float]:
        """
        Optional auxiliary VAE supervision from settled episodes with realized labels.
        """
        if not self._torch_available:
            return {"samples": 0.0, "loss": 0.0, "ce": 0.0}
        aux_cfg = getattr(self.config.vae, "regime_aux", None)
        if not (aux_cfg and bool(getattr(aux_cfg, "enabled", False))):
            return {"samples": 0.0, "loss": 0.0, "ce": 0.0}

        samples_obs = []
        samples_y = []
        input_dim = int(self.config.vae.input_dim)
        for ep in episodes:
            if "realized_regime" not in ep:
                continue
            y_raw = ep.get("realized_regime")
            try:
                y = int(y_raw)
            except (TypeError, ValueError):
                continue
            vec = ep.get("features_vector")
            if not isinstance(vec, (list, tuple, np.ndarray)):
                continue
            arr = np.asarray(vec, dtype=np.float32).reshape(-1)
            if arr.shape[0] != input_dim or not np.isfinite(arr).all():
                continue
            samples_obs.append(arr)
            samples_y.append(y)

        if not samples_obs:
            return {"samples": 0.0, "loss": 0.0, "ce": 0.0}

        x = torch.as_tensor(np.stack(samples_obs), dtype=torch.float32, device=self.device)
        y = torch.as_tensor(np.asarray(samples_y), dtype=torch.long, device=self.device)

        self.vae_opt.zero_grad()
        recon_x, mu, logvar = self.vae(x)
        logits = self.vae.predict_regime_logits(mu)
        losses = self.vae.loss_function(
            recon_x,
            x,
            mu,
            logvar,
            beta=self.config.vae.beta,
            regime_logits=logits,
            regime_targets=y,
            aux_alpha=float(getattr(aux_cfg, "alpha", 0.0)),
        )
        losses["loss"].backward()
        torch.nn.utils.clip_grad_norm_(self.vae.parameters(), max_norm=1.0)
        self.vae_opt.step()

        return {
            "samples": float(len(samples_obs)),
            "loss": float(losses["loss"].item()),
            "ce": float(losses["regime_ce"].item()),
        }

    def encode(self, obs: np.ndarray) -> np.ndarray:
        """Encode numpy observation to numpy latent vector."""
        if not self._torch_available:
            latent_dim = getattr(
                getattr(self.config, "vae", None), "latent_dim", 1)
            return np.zeros(int(latent_dim), dtype=np.float32)

        with torch.no_grad():
            self.vae.eval()

            t_obs = torch.from_numpy(obs).float().to(self.device)

            is_batch = t_obs.dim() > 1
            if not is_batch:
                t_obs = t_obs.unsqueeze(0)

            mu, logvar = self.vae.encode(t_obs)

            z = mu if self.config.vae.use_mean else self.vae.reparameterize(
                mu, logvar)

            self.vae.train()

            z_np = z.cpu().numpy()

            if not is_batch:
                return z_np[0]
            return z_np

    def get_action(self, z: np.ndarray) -> Dict[str, Any]:
        """
        Get action from PPO agent given latent state.

        Args:
            z: Latent vector from VAE

        Returns:
            dict with 'action', 'value', 'confidence' (log_prob)
        """
        _FLAT_FALLBACK = {
            "action": 2,
            "action_name": "MEAN_REVERSION" if self.config.ppo.action_dim == 5 else "FLAT",
            "value": 0.0,
            "confidence": 0.0,
        }

        if self.ppo_agent is None or self._model_corrupted:
            return {**_FLAT_FALLBACK, "corrupted": self._model_corrupted}

        try:
            # Ensure z is float32
            z = np.asarray(z, dtype=np.float32)
            if not np.isfinite(z).all():
                self._warn_nonfinite_action("latent_non_finite")
                z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0).astype(
                    np.float32, copy=False)

            action, value, logp = self.ppo_agent.act(z, deterministic=False)

            action_arr = np.asarray(action)
            value_arr = np.asarray(value, dtype=np.float32)
            logp_arr = np.asarray(logp, dtype=np.float32)
            if (not np.isfinite(action_arr).all()) or (not np.isfinite(value_arr).all()) or (not np.isfinite(logp_arr).all()):
                self._warn_nonfinite_action("act_value_logp_non_finite")

                # If we're seeing repeated NaN outputs, the weights are corrupted.
                if self._nonfinite_action_events >= 3:
                    self._model_corrupted = True
                    logger.critical(
                        "PPO model flagged as CORRUPTED after %d consecutive non-finite outputs; "
                        "returning FLAT indefinitely until checkpoint recovery",
                        self._nonfinite_action_events,
                    )

                if hasattr(self.ppo_agent, "reset_hidden"):
                    try:
                        self.ppo_agent.reset_hidden(
                            np.array([True], dtype=bool))
                    except Exception:
                        pass
                return {**_FLAT_FALLBACK, "corrupted": self._model_corrupted}

            # Map action index to name (dynamic based on action_dim)
            action_dim = self.config.ppo.action_dim
            if action_dim == 5:
                action_names = [
                    "TREND_UP", "TREND_DOWN", "MEAN_REVERSION",
                    "HIGH_VOLATILITY", "EXHAUSTION",
                ]
            else:
                action_names = ["LONG", "SHORT", "FLAT"]
            action_idx = int(action_arr.reshape(-1)[0])
            action_name = action_names[action_idx] if action_idx < len(
                action_names) else "UNKNOWN"

            return {
                "action": action_idx,
                "action_name": action_name,
                "value": float(value_arr.reshape(-1)[0]),
                "confidence": float(logp_arr.reshape(-1)[0]),
                "corrupted": False,
            }

        except Exception as e:
            self._warn_nonfinite_action(f"exception:{type(e).__name__}")
            return {**_FLAT_FALLBACK, "corrupted": self._model_corrupted}

    def train_ppo(self, episodes: list[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train PPO on a batch of completed episodes (offline update).

        Episodes are expected to be dict-like and include at least:
          - features_vector: List[float] (VAE input space)
          - side: str ("LONG"/"SHORT"/"FLAT" or "BUY"/"SELL")
          - reward: float
        """
        if not self._torch_available or self.ppo_agent is None:
            logger.warning("PPO not available; skipping PPO training")
            return {}

        if self._model_corrupted:
            logger.warning(
                "PPO model is CORRUPTED; refusing to train. Load a clean checkpoint first.")
            return {"error": "model_corrupted"}

        if not episodes:
            return {}

        import torch

        aux_metrics = {"samples": 0.0, "loss": 0.0, "ce": 0.0}
        try:
            aux_metrics = self._train_vae_aux_from_episodes(episodes)
        except Exception as e:
            logger.warning("Auxiliary VAE supervision step failed: %s", e)

        # Action mapping depends on mode (pnl vs regime_oracle)
        action_map = {"LONG": 0, "SHORT": 1, "FLAT": 2, "BUY": 0, "SELL": 1}
        # Oracle mode also accepts string names for robustness
        if self.config.ppo.action_dim == 5:
            action_map.update({
                "TREND_UP": 0, "TREND_DOWN": 1, "MEAN_REVERSION": 2,
                "HIGH_VOLATILITY": 3, "EXHAUSTION": 4,
            })
        device = self.ppo_agent.device

        episodes_processed = 0
        episodes_skipped = 0

        # Always start from a clean collection buffer for offline updates.
        self.ppo_agent.buffer.clear()

        for ep in episodes:
            features_vector = ep.get("features_vector")
            if not features_vector:
                episodes_skipped += 1
                continue

            obs_np = np.asarray(features_vector, dtype=np.float32)
            z = self.encode(obs_np).astype(np.float32)

            side = str(ep.get("side") or "FLAT").upper()
            # Oracle episodes pass action index directly; PnL episodes pass string side
            if "action" in ep and isinstance(ep.get("action"), int):
                action_idx = ep["action"]
            else:
                action_idx = action_map.get(side, 2)

            reward = ep.get("reward", 0.0)
            reward_f = 0.0 if reward is None else float(reward)

            with torch.no_grad():
                obs_t = torch.as_tensor(
                    z, dtype=torch.float32, device=device).unsqueeze(0)

                hidden = self.ppo_agent.model.init_hidden(1, device)
                dist, value_t, _ = self.ppo_agent.model(obs_t, hidden)

                act_t_long = torch.tensor(
                    [action_idx], dtype=torch.long, device=device)
                logp_t = dist.log_prob(act_t_long)
                if logp_t.dim() > 1:
                    logp_t = logp_t.sum(dim=-1)

                rew_t = torch.tensor(
                    [reward_f], dtype=torch.float32, device=device)
                done_t = torch.tensor([True], dtype=torch.bool, device=device)
                val_t = value_t.squeeze(-1)

                # PPOAgent.store expects float tensors for act/logp, even in discrete mode.
                self.ppo_agent.store(
                    obs=obs_t,
                    act=act_t_long.float(),
                    rew=rew_t,
                    val=val_t,
                    logp=logp_t.float(),
                    done=done_t,
                )

            episodes_processed += 1

            if self.ppo_agent.buffer.full:
                break

        if episodes_processed == 0:
            return {}

        # Bootstrap value for the last step (terminal in our offline-episode framing).
        last_values = torch.zeros(1, dtype=torch.float32, device=device)
        self.ppo_agent.buffer.finalize(last_values)

        current_coef = None
        if self.ppo_agent.entropy_scheduler:
            current_coef = self.ppo_agent.entropy_scheduler.value(self.train_steps)
            self.ppo_agent.agent_cfg.entropy_coef = current_coef

        metrics = self.ppo_agent.update()
        self.ppo_agent.buffer.clear()
        self._train_steps += 1

        metrics["episodes_processed"] = episodes_processed
        metrics["episodes_skipped"] = episodes_skipped
        metrics["train_step"] = self._train_steps
        metrics["vae_aux_samples"] = float(aux_metrics.get("samples", 0.0))
        metrics["vae_aux_loss"] = float(aux_metrics.get("loss", 0.0))
        metrics["vae_aux_ce"] = float(aux_metrics.get("ce", 0.0))
        if current_coef is not None:
            metrics["entropy_coef"] = float(current_coef)
        return metrics

    def save_checkpoint(self, path: Path) -> bool:
        """
        Save all model weights and optimizer states.
        Prunes old checkpoints to keep only the last N (from config).

        Args:
            path: Directory to save checkpoint

        Returns:
            True if successful
        """
        if not self._torch_available:
            logger.warning("PyTorch not available; cannot save checkpoint")
            return False

        try:
            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)

            checkpoint = {
                "train_steps": self._train_steps,
                "vae_state": self.vae.state_dict(),
                "vae_opt_state": self.vae_opt.state_dict(),
                "wm_state": self.world_model.state_dict(),
                "wm_opt_state": self.wm_opt.state_dict(),
                "checkpoint_metadata": {
                    "version": 1,
                    "neuro": {
                        "vae_input_dim": int(self.config.vae.input_dim),
                        "vae_latent_dim": int(self.config.vae.latent_dim),
                        "regime_aux_enabled": bool(
                            getattr(self.config.vae.regime_aux, "enabled", False)
                        ),
                        "regime_aux_alpha": float(
                            getattr(self.config.vae.regime_aux, "alpha", 0.0)
                        ),
                    },
                },
            }

            # Add PPO if available
            if self.ppo_agent is not None:
                checkpoint["ppo_model_state"] = self.ppo_agent.model.state_dict()
                checkpoint["ppo_opt_state"] = self.ppo_agent.optimizer.state_dict()

            checkpoint_file = path / f"checkpoint_{self._train_steps}.pt"
            torch.save(checkpoint, checkpoint_file)

            # Also save as 'latest' for easy loading
            latest_file = path / "checkpoint_latest.pt"
            torch.save(checkpoint, latest_file)

            logger.info(f"Checkpoint saved: {checkpoint_file}")

            # Prune old checkpoints, keep only last N
            self._prune_old_checkpoints(path)

            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

    def _prune_old_checkpoints(self, checkpoint_dir: Path) -> None:
        """Remove old numbered checkpoints, keeping only the last N."""
        import re
        keep_n = getattr(self.config, 'keep_last_n_checkpoints', 5)
        if keep_n <= 0:
            return

        numbered = []
        for f in checkpoint_dir.glob("checkpoint_*.pt"):
            if f.name == "checkpoint_latest.pt":
                continue
            m = re.match(r"checkpoint_(\d+)\.pt$", f.name)
            if m:
                numbered.append((int(m.group(1)), f))

        numbered.sort(key=lambda x: x[0])

        if len(numbered) <= keep_n:
            return

        to_delete = numbered[:-keep_n]
        for step_num, fpath in to_delete:
            try:
                fpath.unlink()
                logger.debug(f"Pruned old checkpoint: {fpath.name}")
            except OSError as e:
                logger.warning(f"Failed to prune checkpoint {fpath.name}: {e}")

    def load_checkpoint(self, path: Path) -> bool:
        """
        Load model weights and optimizer states.

        Args:
            path: Path to checkpoint file or directory

        Returns:
            True if successful
        """
        if not self._torch_available:
            logger.warning("PyTorch not available; cannot load checkpoint")
            return False

        try:
            path = Path(path)

            # If directory, look for latest
            if path.is_dir():
                checkpoint_file = path / "checkpoint_latest.pt"
            else:
                checkpoint_file = path

            if not checkpoint_file.exists():
                logger.warning(f"Checkpoint not found: {checkpoint_file}")
                return False

            checkpoint = torch.load(checkpoint_file, map_location=self.device)
            metadata = checkpoint.get("checkpoint_metadata", {})
            if metadata:
                neuro_meta = metadata.get("neuro", {})
                expected = {
                    "vae_input_dim": int(self.config.vae.input_dim),
                    "vae_latent_dim": int(self.config.vae.latent_dim),
                    "regime_aux_enabled": bool(getattr(self.config.vae.regime_aux, "enabled", False)),
                    "regime_aux_alpha": float(getattr(self.config.vae.regime_aux, "alpha", 0.0)),
                }
                mismatch = {
                    k: (neuro_meta.get(k), expected[k])
                    for k in expected
                    if neuro_meta.get(k) != expected[k]
                }
                if mismatch:
                    logger.warning(
                        "Checkpoint neuro metadata mismatch: %s",
                        mismatch,
                    )

            self._train_steps = checkpoint.get("train_steps", 0)
            self.vae.load_state_dict(checkpoint["vae_state"])
            self.vae_opt.load_state_dict(checkpoint["vae_opt_state"])
            self.world_model.load_state_dict(checkpoint["wm_state"])
            self.wm_opt.load_state_dict(checkpoint["wm_opt_state"])

            # Load PPO if available
            if self.ppo_agent is not None and "ppo_model_state" in checkpoint:
                self.ppo_agent.model.load_state_dict(
                    checkpoint["ppo_model_state"])
                self.ppo_agent.optimizer.load_state_dict(
                    checkpoint["ppo_opt_state"])

            logger.info(
                f"Checkpoint loaded: {checkpoint_file} (step {self._train_steps})")
            return True

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    @property
    def train_steps(self) -> int:
        return self._train_steps
