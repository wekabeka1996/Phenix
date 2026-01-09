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
    
    def __init__(self, config: NeuroConfig, device: str = None):
        if not HAS_TORCH:
            raise ImportError("PyTorch required for BrainCore")
            
        self.config = config
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self._train_steps = 0
        
        logger.info(f"Initializing BrainCore on device: {self.device}")
        
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
                batch_size=ppo_cfg.minibatch_size
            )
            
            train_config = TrainConfig(
                n_steps=ppo_cfg.rollout_length,
                device=self.device,
                seed=42
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
            
        except Exception as e:
            logger.warning(f"PPO initialization failed: {e}")
            self.ppo_agent = None

    def train_batch(self, batch_obs: torch.Tensor) -> Dict[str, float]:
        """
        Perform one training step on a sequential batch of observations.
        """
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
            
        z_in = z[:-1]
        z_target = z[1:]
        
        self.wm_opt.zero_grad()
        
        z_pred_seq, _ = self.world_model(z_in)
        
        if z_pred_seq.dim() == 3:
            z_pred = z_pred_seq.squeeze(1)
        else:
            z_pred = z_pred_seq
            
        wm_loss = torch.nn.functional.mse_loss(z_pred, z_target)
        
        wm_loss.backward()
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
            action_idx = int(action) if isinstance(action, (int, np.integer)) else int(action.item())
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

    def save_checkpoint(self, path: Path) -> bool:
        """
        Save all model weights and optimizer states.
        
        Args:
            path: Directory to save checkpoint
            
        Returns:
            True if successful
        """
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
