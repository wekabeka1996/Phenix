"""
Brain Core

Orchestrator for the Neocortex Neural Architecture.
Unifies VAE (Representation), World Model (Dynamics), and PPO (Decision).

Phase 4: Added checkpointing and PPO integration.
"""

from typing import Dict, Any, Optional
from pathlib import Path
import logging
import numpy as np
import sys

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    class torch:
        Tensor = object
        class cuda:
            is_available = lambda: False
        class optim:
            Adam = object

# Add PPO library to path
PPO_PATH = Path(__file__).parent.parent.parent / "PPO" / "ppo_library_v2"
if PPO_PATH.exists():
    sys.path.insert(0, str(PPO_PATH))
    HAS_PPO = True
else:
    HAS_PPO = False

from config_models import NeuroConfig
from logic.brain.vae import VariationalAutoencoder
from logic.brain.world_model import WorldModel

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
        self.device = device or ('cuda' if (HAS_TORCH and torch.cuda.is_available()) else 'cpu')
        self._train_steps = 0
        self.rng_seed = int(rng_seed)
        
        logger.info(f"Initializing BrainCore on device: {self.device}")

        if not self._torch_available:
            logger.warning("PyTorch not available; BrainCore running in no-torch mock mode (VAE/WM/PPO disabled)")
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
        
    def _init_ppo(self):
        """Initialize PPO Agent if library is available."""
        if not self._torch_available:
            logger.warning("PyTorch not available; skipping PPO initialization")
            return
        if not HAS_PPO:
            logger.warning("PPO library not found, shadow intents disabled")
            return
            
        try:
            from ppo_system.agent import PPOAgent
            from ppo_system.core.dataclasses import AgentConfig, TrainConfig
            
            # Create configs from NeuroConfig.ppo
            ppo_cfg = self.config.ppo
            
            agent_config = AgentConfig(
                learning_rate=ppo_cfg.learning_rate,
                gamma=ppo_cfg.gamma,
                gae_lambda=ppo_cfg.gae_lambda,
                clip_range=ppo_cfg.clip_epsilon,
                hidden_size=ppo_cfg.hidden_dims[0] if ppo_cfg.hidden_dims else 64,
                epochs=ppo_cfg.num_epochs,
                batch_size=ppo_cfg.minibatch_size,
                continuous_head="categorical"  # Force discrete action space
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
            
            logger.info(f"✓ PPO Agent initialized (Actions: {ppo_cfg.action_dim})")
            
        except ImportError as e:
            logger.warning(f"PPO import failed (likely missing torch deps): {e}")
            self.ppo_agent = None
        except Exception as e:
            logger.warning(f"PPO initialization failed: {e}")
            self.ppo_agent = None

    def train_batch(self, batch_obs: torch.Tensor) -> Dict[str, float]:
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
        
        vae_losses = self.vae.loss_function(
            recon_x, batch_obs, mu, logvar, 
            beta=self.config.vae.beta
        )
        
        vae_loss = vae_losses['loss']
        vae_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.vae.parameters(), max_norm=1.0)
        self.vae_opt.step()
        
        # B. WORLD MODEL TRAINING
        with torch.no_grad():
            mu_enc, logvar_enc = self.vae.encode(batch_obs)
            z = mu_enc if self.config.vae.use_mean else self.vae.reparameterize(mu_enc, logvar_enc)

        if z.shape[0] < 2:
            return {
                "vae_loss": vae_loss.item(),
                "vae_mse": vae_losses['mse'].item(),
                "vae_kld": vae_losses['kld'].item(),
                "wm_loss": 0.0
            }
            
        self.wm_opt.zero_grad()

        # Treat the batch as a single sequence: (B, D) -> (1, Seq=B, D)
        z_seq = z.unsqueeze(0)
        z_in_seq = z_seq[:, :-1, :]
        z_target_seq = z_seq[:, 1:, :]

        z_pred_seq, _ = self.world_model(z_in_seq)

        wm_loss = torch.nn.functional.mse_loss(z_pred_seq, z_target_seq, reduction="mean")
        
        wm_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.world_model.parameters(), max_norm=1.0)
        self.wm_opt.step()
        
        self._train_steps += 1
        
        return {
            "vae_loss": vae_loss.item(),
            "vae_mse": vae_losses['mse'].item(),
            "vae_kld": vae_losses['kld'].item(),
            "wm_loss": wm_loss.item()
        }

    def encode(self, obs: np.ndarray) -> np.ndarray:
        """Encode numpy observation to numpy latent vector."""
        if not self._torch_available:
            latent_dim = getattr(getattr(self.config, "vae", None), "latent_dim", 1)
            return np.zeros(int(latent_dim), dtype=np.float32)

        with torch.no_grad():
            self.vae.eval()
            
            t_obs = torch.from_numpy(obs).float().to(self.device)
            
            is_batch = t_obs.dim() > 1
            if not is_batch:
                t_obs = t_obs.unsqueeze(0)
            
            mu, logvar = self.vae.encode(t_obs)
            
            z = mu if self.config.vae.use_mean else self.vae.reparameterize(mu, logvar)
            
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
        if self.ppo_agent is None:
            # Fallback: random/neutral action
            return {
                "action": 2,  # FLAT
                "action_name": "FLAT",
                "value": 0.0,
                "confidence": 0.0
            }
        
        try:
            # Ensure z is float32
            z = z.astype(np.float32)
            
            action, value, logp = self.ppo_agent.act(z, deterministic=False)
            
            # Map action index to name
            action_names = ["LONG", "SHORT", "FLAT"]
            action_idx = int(np.asarray(action).reshape(-1)[0])
            action_name = action_names[action_idx] if action_idx < len(action_names) else "UNKNOWN"
            
            return {
                "action": action_idx,
                "action_name": action_name,
                "value": float(value),
                "confidence": float(logp)
            }
            
        except Exception as e:
            logger.error(f"PPO action failed: {e}")
            return {
                "action": 2,
                "action_name": "FLAT",
                "value": 0.0,
                "confidence": 0.0
            }

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

        if not episodes:
            return {}

        import torch

        action_map = {"LONG": 0, "SHORT": 1, "FLAT": 2, "BUY": 0, "SELL": 1}
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
            action_idx = action_map.get(side, 2)

            reward = ep.get("reward", 0.0)
            reward_f = 0.0 if reward is None else float(reward)

            with torch.no_grad():
                obs_t = torch.as_tensor(z, dtype=torch.float32, device=device).unsqueeze(0)

                hidden = self.ppo_agent.model.init_hidden(1, device)
                dist, value_t, _ = self.ppo_agent.model(obs_t, hidden)

                act_t_long = torch.tensor([action_idx], dtype=torch.long, device=device)
                logp_t = dist.log_prob(act_t_long)
                if logp_t.dim() > 1:
                    logp_t = logp_t.sum(dim=-1)

                rew_t = torch.tensor([reward_f], dtype=torch.float32, device=device)
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

        metrics = self.ppo_agent.update()
        self.ppo_agent.buffer.clear()

        metrics["episodes_processed"] = episodes_processed
        metrics["episodes_skipped"] = episodes_skipped
        return metrics

    def save_checkpoint(self, path: Path) -> bool:
        """
        Save all model weights and optimizer states.
        
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
            return True
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

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
            
            self._train_steps = checkpoint.get("train_steps", 0)
            self.vae.load_state_dict(checkpoint["vae_state"])
            self.vae_opt.load_state_dict(checkpoint["vae_opt_state"])
            self.world_model.load_state_dict(checkpoint["wm_state"])
            self.wm_opt.load_state_dict(checkpoint["wm_opt_state"])
            
            # Load PPO if available
            if self.ppo_agent is not None and "ppo_model_state" in checkpoint:
                self.ppo_agent.model.load_state_dict(checkpoint["ppo_model_state"])
                self.ppo_agent.optimizer.load_state_dict(checkpoint["ppo_opt_state"])
            
            logger.info(f"Checkpoint loaded: {checkpoint_file} (step {self._train_steps})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    @property
    def train_steps(self) -> int:
        return self._train_steps
