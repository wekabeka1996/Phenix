# path: ppo_library/examples/02_train_cartpole_vectorized.py
"""
Приклад 2: Тренування PPO-агента з використанням векторизованого середовища.
Демонструє ефективне паралельне збирання даних.
"""
try:
    import gymnasium as gym
except ImportError:
    import gym

from ppo_system import PPOAgent, train, AgentConfig, TrainConfig, SafetyConfig

def main():
    num_envs = 8
    env = gym.vector.SyncVectorEnv([lambda: gym.make("CartPole-v1") for _ in range(num_envs)])
    
    # 1. Конфігурація агента (може бути та сама)
    agent_cfg = AgentConfig(
        learning_rate=3e-4,
        clip_range=0.2,
        entropy_coef=0.01,
        value_loss_coef=0.5,
        max_grad_norm=0.5,
        epochs=4,
        batch_size=256,
        target_kl=0.02,
        hidden_size=128,
        lstm_layers=1,
        numerical_safety=SafetyConfig(on_invalid="skip_step")
    )
    
    # 2. Конфігурація тренування (n_steps можна зменшити, бо є num_envs)
    train_cfg = TrainConfig(
        total_timesteps=100_000,
        n_steps=256,
        device="cpu",
        seed=123
    )

    # 3. Створення та тренування агента
    agent = PPOAgent.from_env(agent_cfg, train_cfg, env)
    train(agent, env, train_cfg)
    
    env.close()

if __name__ == "__main__":
    main()