# path: ppo_library/tests/test_agent_integration.py
import pytest
try:
    import gymnasium as gym
except ImportError:
    import gym

from ppo_system import PPOAgent, train, AgentConfig, TrainConfig

def test_agent_runs_single_env_short_training():
    """
    Інтеграційний тест: перевіряє, що агент може провести короткий
    цикл навчання на простому середовищі (CartPole) без помилок.
    """
    env = gym.make("CartPole-v1")

    agent_cfg = AgentConfig(hidden_size=64, lstm_layers=1)
    train_cfg = TrainConfig(total_timesteps=256, n_steps=64, seed=42)

    agent = PPOAgent.from_env(agent_cfg, train_cfg, env)

    metrics = train(agent, env, train_cfg)

    assert "loss" in metrics
    assert metrics["loss"] > 0, "Loss should be positive"

def test_agent_runs_vectorized_env_short_training():
    """
    Інтеграційний тест: перевіряє коректну роботу агента з векторизованим
    середовищем, включаючи керування hidden states.
    """
    num_envs = 4
    env = gym.vector.SyncVectorEnv([lambda: gym.make("CartPole-v1") for _ in range(num_envs)])

    agent_cfg = AgentConfig(hidden_size=64, lstm_layers=1)
    train_cfg = TrainConfig(total_timesteps=512, n_steps=128, seed=42)

    agent = PPOAgent.from_env(agent_cfg, train_cfg, env)

    # Перевірка, що hidden state має правильний розмір
    assert agent._hidden[0].shape[1] == num_envs, "Hidden state batch size should match num_envs"

    metrics = train(agent, env, train_cfg)

    assert "loss" in metrics
    assert metrics["loss"] > 0, "Loss should be positive"