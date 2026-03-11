# path: ppo_library/tests/test_buffer.py
import torch
import pytest
from ppo_system.learning.buffer import TrajectoryBuffer

def test_gae_calculation_with_bootstrap():
    """
    Unit-тест: перевіряє, що GAE коректно розраховується з урахуванням
    bootstrap-оцінки для незавершених епізодів.
    """
    T, N = 4, 3  # 4 кроки, 3 середовища
    buf = TrajectoryBuffer(
        obs_dim=2, action_dim=1, n_envs=N, n_steps=T,
        gamma=0.99, gae_lambda=0.95, device="cpu", is_continuous=False
    )

    # Симулюємо 4 кроки. Env 0 завершується на останньому кроці.
    for t in range(T):
        done = torch.tensor([t == T - 1, False, False], dtype=torch.bool)
        buf.store(
            obs=torch.ones(N, 2) * t,
            act=torch.zeros(N, 1),
            rew=torch.ones(N),
            val=torch.zeros(N),
            logp=torch.zeros(N),
            done=done
        )
    
    assert buf.full
    
    # Bootstrap-оцінки для незавершених середовищ 1 та 2
    last_values = torch.tensor([0.0, 10.0, 20.0])
    buf.finalize(last_values)
    
    batch = buf.get()
    
    # Перевірки
    assert batch["adv"].numel() == T * N
    assert torch.isfinite(batch["adv"]).all()
    
    # Перевіряємо, що returns для останнього кроку незавершених епізодів
    # враховують bootstrap value.
    # ret = adv + val. val=0, тому ret=adv.
    # adv для env 1 (індекс -2) та env 2 (індекс -1) мають бути > 0.
    # adv[-3] -> env 0, t=3 (done), adv = rew - val = 1 - 0 = 1
    # adv[-2] -> env 1, t=3 (not done), adv = rew + gamma*last_val - val = 1 + 0.99*10 - 0 = 10.9
    # adv[-1] -> env 2, t=3 (not done), adv = rew + gamma*last_val - val = 1 + 0.99*20 - 0 = 20.8
    
    adv_flat = buf.adv.view(-1)
    assert adv_flat[-3].item() == pytest.approx(1.0)
    assert adv_flat[-2].item() > 10.0
    assert adv_flat[-1].item() > 20.0