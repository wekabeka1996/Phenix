# path: ppo_library/ppo_system/training_loop.py
from __future__ import annotations
from typing import Any, Optional, Dict
import time
import numpy as np
import logging

from .agent import PPOAgent
from .core.dataclasses import StepResult, TrainConfig
from .utils.seed import set_global_seed

def _unify_step(step_output: tuple) -> StepResult:
    """Приводить вихід step() до єдиного формату StepResult."""
    if len(step_output) == 5:  # Gymnasium new API
        obs, reward, terminated, truncated, info = step_output
        return StepResult(obs=obs, reward=float(reward), done=bool(terminated or truncated), info=info or {})
    elif len(step_output) == 4:  # Gym old API
        obs, reward, done, info = step_output
        return StepResult(obs=obs, reward=float(reward), done=bool(done), info=info or {})
    else:
        raise ValueError(f"Unsupported step output format with {len(step_output)} elements.")

def _unify_reset(reset_output: Any) -> Any:
    """Приводить вихід reset() до єдиного формату (повертає тільки obs)."""
    return reset_output[0] if isinstance(reset_output, tuple) else reset_output

def _is_batched(obs: np.ndarray) -> bool:
    """Перевіряє, чи є спостереження батчем (для векторизованих середовищ)."""
    return hasattr(obs, "shape") and len(obs.shape) > 1

def train(
    agent: PPOAgent,
    env: Any,
    train_config: TrainConfig,
    eval_env: Optional[Any] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, float]:
    """
    Універсальний тренувальний цикл для PPO-агента.
    - Сумісний з Gym, Gymnasium та векторизованими середовищами.
    - Реалізує потік `store -> finalize -> get -> update`.
    - Інтегрує FallbackController для стабілізації.
    """
    set_global_seed(train_config.seed)
    logger = logger or logging.getLogger("ppo_system.train")

    obs = _unify_reset(env.reset())
    num_envs = agent.num_envs

    # Статистика по епізодах
    episode_returns = np.zeros(num_envs, dtype=np.float32)
    episode_lengths = np.zeros(num_envs, dtype=np.int32)

    start_time = time.time()
    total_steps = 0

    # Головний цикл тренування
    while total_steps < train_config.total_timesteps:
        # --- Фаза збору даних (Rollout) ---
        for step in range(train_config.n_steps):
            total_steps += 1

            # 1. Отримати дію від агента
            action, value, logp = agent.act(obs)

            # 2. Виконати крок у середовищі
            step_output = env.step(action)

            # 3. Уніфікувати та обробити результат
            if num_envs > 1:
                # Векторизоване середовище
                next_obs, reward, done, info = step_output[0], step_output[1], (step_output[2] | step_output[3]), step_output[4]
            else:
                # Одиночне середовище
                sr = _unify_step(step_output)
                next_obs, reward, done, info = sr.obs, np.array([sr.reward]), np.array([sr.done]), sr.info

            # 4. Зберегти досвід
            agent.store(obs, action, reward, value, logp, done)
            obs = next_obs

            # 5. Оновити статистику епізодів
            episode_returns += reward
            episode_lengths += 1

            # Якщо будь-яке середовище завершило епізод
            if np.any(done):
                agent.reset_hidden(done)
                for i, d in enumerate(done):
                    if d:
                        logger.info(
                            f"Step={total_steps}, Env={i}, "
                            f"Episode finished. Return={episode_returns[i]:.2f}, Length={episode_lengths[i]}"
                        )
                        episode_returns[i] = 0.0
                        episode_lengths[i] = 0

        # --- Фаза оновлення політики ---

        # 1. Отримати bootstrap-оцінку для незавершених епізодів
        last_values = agent.value(obs)

        # 2. Фіналізувати буфер (розрахувати GAE)
        agent.buffer.finalize(last_values)

        # 3. Виконати оновлення політики
        metrics = agent.update()

        # 4. Застосувати FallbackController
        current_lr = agent.optimizer.param_groups[0]["lr"]
        current_clip = agent.agent_cfg.clip_range

        suggestions = agent.fallback_controller.after_update(
            metrics,
            base_lr=agent.base_lr,
            base_clip=agent.base_clip,
            current_lr=current_lr,
            current_clip=current_clip,
        )

        if suggestions:
            if "learning_rate" in suggestions:
                for g in agent.optimizer.param_groups:
                    g["lr"] = float(suggestions["learning_rate"])
            if "clip_range" in suggestions:
                agent.agent_cfg.clip_range = float(suggestions["clip_range"])
            logger.warning(f"FallbackController triggered: {suggestions}")

        # Логування
        fps = int(train_config.n_steps * num_envs / (time.time() - start_time))
        logger.info(f"Update @ Step={total_steps} | FPS: {fps} | Metrics: { {k: f'{v:.4f}' for k, v in metrics.items()} }")
        start_time = time.time()

    return metrics