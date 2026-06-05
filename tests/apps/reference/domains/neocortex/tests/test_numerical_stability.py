"""
Tests for Numerical Stability: Zero-Reward Episode Survival

Reproduces the "Brain Death" scenario:
  1. Feed the PPO updater with batches where all advantages are zero/identical.
  2. Feed BrainCore.train_ppo() with 5 identical zero-reward cancelled-style episodes.
  3. Verify no NaN/Inf in model weights after training.
  4. Verify the model still produces finite actions after training.

These are regression tests for the advantage-normalization NaN bug
(Bessel's correction on single-element batches → adv.std() = NaN).
"""

import pytest
import numpy as np
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure PPO library is importable
PPO_PATH = Path(__file__).parent.parent / "PPO" / "ppo_library_v2"
if PPO_PATH.exists() and str(PPO_PATH) not in sys.path:
    sys.path.insert(0, str(PPO_PATH))

torch = pytest.importorskip("torch")


# ---------------------------------------------------------------------------
# 1. Low-level: PolicyUpdater survives degenerate advantage batches
# ---------------------------------------------------------------------------

class TestPolicyUpdaterNumericalSafety:
    """Unit tests for the numerical firebreaks in PolicyUpdater."""

    @pytest.fixture
    def make_updater(self):
        """Create a minimal PolicyUpdater + model + optimizer."""
        from ppo_system.core.dataclasses import AgentConfig
        from ppo_system.learning.updater import PolicyUpdater
        from ppo_system.utils.safety import SafetyConfig, NumericalSafetyManager
        from ppo_system.models.actor_critic_lstm import ActorCriticLSTM

        def _factory(with_safety: bool = True):
            safety_cfg = SafetyConfig() if with_safety else None
            cfg = AgentConfig(
                epochs=2,
                batch_size=4,
                numerical_safety=safety_cfg,
            )
            safety = NumericalSafetyManager(safety_cfg) if safety_cfg else None
            updater = PolicyUpdater(config=cfg, safety=safety)

            obs_dim = 8
            action_dim = 3
            model = ActorCriticLSTM(
                obs_dim=obs_dim,
                action_dim=action_dim,
                hidden_size=32,
                lstm_layers=1,
                continuous_head="categorical",
                log_std_init=-0.5,
                temperature=1.0,
                sigma_min=0.05,
            )
            optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
            return updater, model, optimizer, obs_dim, action_dim

        return _factory

    def _make_batch(self, model, obs_dim, n_samples, reward_val=0.0):
        """Create a synthetic batch_data dict like buffer.get() would return."""
        obs = torch.randn(n_samples, obs_dim)
        # Discrete actions
        act = torch.randint(0, 3, (n_samples,))
        ret = torch.full((n_samples,), reward_val)
        adv = torch.full((n_samples,), reward_val)  # All identical → std=0
        logp = torch.zeros(n_samples)

        # Fill logp from model to be realistic
        with torch.no_grad():
            hidden = model.init_hidden(n_samples, "cpu")
            dist, value, _ = model(obs, hidden)
            logp = dist.log_prob(act)

        return {"obs": obs, "act": act, "ret": ret, "adv": adv, "logp": logp}

    def test_single_element_batch_no_nan(self, make_updater):
        """
        Regression: n=1 batch → adv.std(unbiased=True) = NaN.
        With the fix (correction=0 + degenerate-check), this must survive.
        """
        updater, model, optimizer, obs_dim, action_dim = make_updater(
            with_safety=True)

        batch = self._make_batch(model, obs_dim, n_samples=1, reward_val=0.0)
        metrics = updater.update(model, optimizer, batch)

        # Metrics must be finite
        for k, v in metrics.items():
            assert np.isfinite(v), f"metric '{k}' is not finite: {v}"

        # Weights must be finite
        for name, param in model.named_parameters():
            assert torch.isfinite(param).all(
            ), f"NaN/Inf in param '{name}' after single-element batch"

    def test_all_zero_advantages_no_nan(self, make_updater):
        """All-zero advantages (e.g. 5 identical zero-reward episodes)."""
        updater, model, optimizer, obs_dim, action_dim = make_updater(
            with_safety=True)

        batch = self._make_batch(model, obs_dim, n_samples=5, reward_val=0.0)
        metrics = updater.update(model, optimizer, batch)

        for k, v in metrics.items():
            assert np.isfinite(v), f"metric '{k}' is not finite: {v}"

        for name, param in model.named_parameters():
            assert torch.isfinite(param).all(), f"NaN/Inf in param '{name}'"

    def test_all_zero_advantages_without_safety_manager(self, make_updater):
        """
        Even without NumericalSafetyManager, the unconditional NaN firebreak
        in the updater must prevent weight corruption.
        """
        updater, model, optimizer, obs_dim, action_dim = make_updater(
            with_safety=False)

        batch = self._make_batch(model, obs_dim, n_samples=1, reward_val=0.0)
        metrics = updater.update(model, optimizer, batch)

        for name, param in model.named_parameters():
            assert torch.isfinite(param).all(
            ), f"NaN/Inf in param '{name}' (no safety manager)"

    def test_repeated_zero_reward_batches(self, make_updater):
        """Simulate 10 consecutive zero-reward update rounds."""
        updater, model, optimizer, obs_dim, action_dim = make_updater(
            with_safety=True)

        for i in range(10):
            batch = self._make_batch(
                model, obs_dim, n_samples=3, reward_val=0.0)
            metrics = updater.update(model, optimizer, batch)

        # After 10 rounds, model must still be healthy
        for name, param in model.named_parameters():
            assert torch.isfinite(param).all(
            ), f"NaN/Inf in param '{name}' after 10 zero-reward rounds"


# ---------------------------------------------------------------------------
# 2. Integration: BrainCore.train_ppo survives zero-reward episodes
# ---------------------------------------------------------------------------

class TestBrainCoreZeroRewardSurvival:
    """Integration test: full BrainCore.train_ppo with zero-reward episodes."""

    @pytest.fixture
    def brain(self):
        """Create a real BrainCore with small dimensions."""
        from apps.reference.domains.neocortex.logic.brain.core import BrainCore

        # Minimal config using MagicMock
        config = MagicMock()
        config.vae.input_dim = 9
        config.vae.latent_dim = 4
        config.vae.hidden_dims = [16]
        config.vae.learning_rate = 1e-3
        config.vae.beta = 1.0
        config.vae.use_mean = True

        config.world_model.hidden_dim = 16
        config.world_model.num_layers = 1
        config.world_model.learning_rate = 1e-3

        config.ppo.learning_rate = 1e-3
        config.ppo.gamma = 0.99
        config.ppo.gae_lambda = 0.95
        config.ppo.clip_epsilon = 0.2
        config.ppo.hidden_dims = [32]
        config.ppo.num_epochs = 2
        config.ppo.minibatch_size = 4
        config.ppo.rollout_length = 8
        config.ppo.action_dim = 3

        try:
            brain = BrainCore(config, device="cpu", rng_seed=42)
        except Exception as e:
            pytest.skip(f"BrainCore init failed (likely missing deps): {e}")

        if brain.ppo_agent is None:
            pytest.skip("PPO agent not available")

        return brain

    def _make_zero_reward_episodes(self, n: int = 5, feature_dim: int = 9):
        """Create n identical zero-reward episodes mimicking ORDER_CANCELLED."""
        return [
            {
                "features_vector": [0.1] * feature_dim,
                "side": "FLAT",
                "reward": 0.0,
            }
            for _ in range(n)
        ]

    def test_5_zero_reward_episodes_survive(self, brain):
        """
        THE MAIN REGRESSION TEST.
        Feed 5 identical zero-reward episodes. System must NOT produce NaN.
        """
        episodes = self._make_zero_reward_episodes(5)
        metrics = brain.train_ppo(episodes)

        # train_ppo must return something (not empty — that would mean no episodes processed)
        assert metrics, "train_ppo returned empty metrics"

        # Check metrics are finite
        for k, v in metrics.items():
            if isinstance(v, (int, float)):
                assert np.isfinite(v), f"metric '{k}' is not finite: {v}"

        # Weights must be finite
        for name, param in brain.ppo_agent.model.named_parameters():
            assert torch.isfinite(param).all(
            ), f"NaN/Inf in PPO param '{name}'"

    def test_action_still_works_after_zero_reward_training(self, brain):
        """After training on zero-reward episodes, get_action must still work."""
        episodes = self._make_zero_reward_episodes(5)
        brain.train_ppo(episodes)

        z = np.random.randn(brain.config.vae.latent_dim).astype(np.float32)
        result = brain.get_action(z)

        assert result["action"] in [0, 1, 2]
        assert result["action_name"] in ["LONG", "SHORT", "FLAT"]
        assert np.isfinite(
            result["value"]), f"value is not finite: {result['value']}"
        assert np.isfinite(
            result["confidence"]), f"confidence is not finite: {result['confidence']}"
        assert result.get("corrupted") is False

    def test_corruption_flag_not_set_after_clean_training(self, brain):
        """After clean training, model_corrupted flag should be False."""
        episodes = self._make_zero_reward_episodes(5)
        brain.train_ppo(episodes)

        assert brain._model_corrupted is False


# ---------------------------------------------------------------------------
# 3. Regression: rescue_brain.py scan_state_dict
# ---------------------------------------------------------------------------

class TestRescueBrainScanner:
    """Tests for the checkpoint scanner utility."""

    _TOOLS_PATH = str(Path(__file__).resolve().parents[6] / "tools")

    def test_clean_state_dict(self):
        sys.path.insert(0, self._TOOLS_PATH)
        from rescue_brain import scan_state_dict

        sd = {"weight": torch.randn(10, 10), "bias": torch.randn(10)}
        result = scan_state_dict(sd)
        assert result["clean"] is True
        assert result["nan_params"] == []
        assert result["inf_params"] == []

    def test_nan_state_dict(self):
        sys.path.insert(0, self._TOOLS_PATH)
        from rescue_brain import scan_state_dict

        w = torch.randn(10, 10)
        w[0, 0] = float("nan")
        sd = {"weight": w, "bias": torch.randn(10)}
        result = scan_state_dict(sd)
        assert result["clean"] is False
        assert "weight" in result["nan_params"]

    def test_inf_state_dict(self):
        sys.path.insert(0, self._TOOLS_PATH)
        from rescue_brain import scan_state_dict

        w = torch.randn(10, 10)
        w[5, 5] = float("inf")
        sd = {"weight": w, "bias": torch.randn(10)}
        result = scan_state_dict(sd)
        assert result["clean"] is False
        assert "weight" in result["inf_params"]
