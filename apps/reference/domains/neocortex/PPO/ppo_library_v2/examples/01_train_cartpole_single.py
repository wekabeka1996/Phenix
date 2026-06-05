# path: ppo_library/examples/01_train_cartpole_single.py
"""
Приклад 1: Тренування PPO-агента на простому середовищі CartPole-v1.
Демонструє базове використання бібліотеки з одним середовищем.
"""
try:
    import gymnasium as gym
except ImportError:
    import gym

from ppo_system import PPOAgent, train, AgentConfig, TrainConfig, SafetyConfig

def main():
    env = gym.make("CartPole-v1")
    
    # 1. Конфігурація агента
    agent_cfg = AgentConfig(
        learning_rate=3e-4,
        clip_range=0.2,
        entropy_coef=0.01,
        value_loss_coef=0.5,
        max_grad_norm=0.5,
        epochs=10,
        batch_size=64,
        target_kl=0.02,
        hidden_size=128,
        lstm_layers=1,
        numerical_safety=SafetyConfig(on_invalid="sanitize")
    )
    
    # 2. Конфігурація тренування
    train_cfg = TrainConfig(
        total_timesteps=50_000,
        n_steps=1024,
        device="cpu",
        seed=42
    )

    # 3. Створення та тренування агента
    agent = PPOAgent.from_env(agent_cfg, train_cfg, env)
    train(agent, env, train_cfg)
    
    env.close()

if __name__ == "__main__":
    main()