# Phase R2: PPO Training Loop

**Date:** 2026-01-11
**Author:** Antigravity AI
**Phase:** R2 (Reinforcement Learning Training Loop)

---

## Overview

Implemented the PPO training loop that enables the neural network to learn
from episode experience. Shadow intents are now generated from a **trained**
network instead of random noise.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PPO Training Flow                            │
│                                                                 │
│   Episodes      ┌─────────────┐    ┌─────────────┐             │
│   (with reward) │   Adapter   │───▶│   Bridge    │             │
│        │        └─────────────┘    └──────┬──────┘             │
│        ▼                                  │                    │
│   ┌─────────────────────────────────────────────────┐          │
│   │              Worker Process                     │          │
│   │                                                 │          │
│   │   ┌─────────────────────────────────────────┐  │          │
│   │   │           BrainCore.train_ppo()         │  │          │
│   │   │                                         │  │          │
│   │   │  1. Encode features → z (latent)        │  │          │
│   │   │  2. Calculate log_prob from policy      │  │          │
│   │   │  3. Store in PPO buffer                 │  │          │
│   │   │  4. If buffer full → update()           │  │          │
│   │   └─────────────────────────────────────────┘  │          │
│   │                  ▲                             │          │
│   │                  │                             │          │
│   │            PPOAgent.update()                   │          │
│   │            (policy gradient descent)           │          │
│   └─────────────────────────────────────────────────┘          │
│                                                                 │
│   Output: Updated policy weights → Better shadow intents        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Files Modified

| File | Changes |
|------|---------|
| `logic/brain/core.py` | Added `train_ppo()` method |
| `logic/brain/worker.py` | Added `_brain_train_ppo_task()` |
| `logic/brain/bridge.py` | Added `train_ppo_async()` |
| `transport/adapter.py` | Added `_trigger_ppo_training()`, `train_ppo_now()` |

## Files Created

| File | Purpose |
|------|---------|
| `tests/test_ppo_loop.py` | 14 tests for PPO training flow |

---

## Key Implementation Details

### 1. BrainCore.train_ppo()

Processes episodes and trains PPO:

```python
def train_ppo(self, episodes: list) -> Dict[str, Any]:
    for ep in episodes:
        # 1. Encode features → z
        z = self.encode(feature_values)
        
        # 2. Get action/reward
        action_idx = action_map[ep["side"]]
        reward = ep["reward"]
        
        # 3. Calculate log_prob from current policy
        dist, _, _ = self.ppo_agent.model(z_tensor, hidden)
        logp = dist.log_prob(action)
        
        # 4. Store in PPO buffer
        self.ppo_agent.store(obs, act, rew, val, logp, done)
    
    # 5. Update if buffer full
    if episodes_stored >= buffer.n_steps:
        metrics = self.ppo_agent.update()
```

### 2. Training Trigger

PPO training is automatically triggered after dream consolidation:

```python
async def _maybe_dream(self):
    # ... dream consolidation ...
    
    # Phase R2: Trigger PPO training on consolidated episodes
    await self._trigger_ppo_training(episodes_to_process)
```

### 3. Action Mapping

```python
action_map = {"LONG": 0, "SHORT": 1, "FLAT": 2, "BUY": 0, "SELL": 1}
```

---

## GPU Utilization (RTX 4070 8GB)

- PPO model runs on CUDA if available
- Tensor operations moved to GPU: `z.to(self.device)`
- LSTM hidden states on device: `self.ppo_agent._hidden`

---

## Logging

New log messages:

```
INFO: PPO Training triggered on 100 episodes
INFO: PPO update complete: loss_pi=0.0123 loss_v=0.0456 entropy=0.789
DEBUG [BrainCore]: train_ppo stored 100 episodes
```

---

## Test Results

```
tests/test_ppo_loop.py: 14 passed ✅

- TestPPOTrainingCore (4 tests)
- TestPPOWorkerTask (2 tests)
- TestPPOBridgeAsync (2 tests)
- TestAdapterPPOIntegration (2 tests)
- TestPPOFlowIntegration (2 tests)
- TestShadowIntentOutput (2 tests)
```

---

## Definition of Done ✅

- [x] PPO weights are updated periodically
- [x] `SHADOW_INTENT` events contain output from trained network
- [x] No crashes during RL update
- [x] Tensor shapes match (Input z: [B, 16], Output Action: [B, 1])
- [x] Device (CUDA) used correctly

---

## Expected Behavior in Production

With PPO training active:

1. **Initial Phase (Steps 0-100):** Random-ish actions as buffer fills
2. **First Update (~100 episodes):** PPO.update() runs, policy improves
3. **Ongoing:** Shadow intents become more meaningful based on learned value function

Monitor logs for:
```
INFO: PPO update complete: loss_pi=... loss_v=... entropy=...
```

Lower `loss_v` = better value function
Higher `entropy` = more exploration (not yet converged)

---

## Next Steps

1. **Phase R3:** Integrate curiosity bonus from CausalGraph into reward
2. **Phase R4:** MCTS planning using graph structure
3. **Hyperparameter tuning:** Adjust learning rate, clip_epsilon, etc.
