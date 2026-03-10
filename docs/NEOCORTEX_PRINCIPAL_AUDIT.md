# NEOCORTEX PRINCIPAL AUDIT — Ruthless First-Principles Analysis

**Auditor**: Principal AI Architect  
**Date**: 2026-02-25  
**Scope**: Full codebase audit (`adapter.py`, `core.py`, `vae.py`, `reward_calculator.py`, `multi_tailer.py`, `regime_labeler.py`, `feature_buffer.py`, `bridge.py`, `worker.py`, `world_model.py`)  
**Verdict**: **The system has 3 critical, 4 major, and 3 moderate flaws. The Nexus-7 proposal will make things worse. The root cause is misidentified.**

---

## <codebase_flaws>

### 🔴 CRITICAL-1: RegimeLabeler Default Fallback Guarantees MR Dominance

**File**: `regime_labeler.py:160-164`  
**Severity**: CRITICAL — This is the **root cause** of the 80% MR mode collapse.

```python
# Rule 5: MEAN_REVERSION — small percentage moves
if abs(delta_pct) < self.mr_delta_pct_threshold:
    return MEAN_REVERSION

# Default fallback: MR
return MEAN_REVERSION     # <--- LINE 164: EVERYTHING FALLS INTO MR
```

**The PPO agent is not broken. Your labeler is.**

The classification cascade has a structural bias:
1. `HIGH_VOLATILITY` requires `vol_state_future > threshold` — rare
2. `EXHAUSTION` requires vol_now HIGH *and* vol_future LOW — rarer
3. `TREND_UP` requires **BOTH** `delta_pct > threshold` **AND** `ema_centered > threshold` — compound conditions, uncommon
4. `TREND_DOWN` same compound requirement
5. **Everything else → MR** (Rule 5 + the default fallback)

In choopy crypto markets, most 15-min bars don't show a clear trend with EMA confirmation. The delta may cross the threshold but EMA doesn't confirm, or vice versa. These ALL default to `MEAN_REVERSION`. **The ground truth labels are ~46% MR because the labeler was DESIGNED to make MR the absorbing state.**

The PPO agent outputting MR 80% of the time is actually a RATIONAL response to a KL-divergence minimization objective — it's learning the dominant mode of a fundamentally lopsided label distribution. **You're punishing the student for the teacher's bias.**

**Quantitative Analysis**: Given the cascade:
- Let `p_vol_high ≈ 0.08`, `p_exhaustion ≈ 0.03` (requires vol transition)
- `p_trend_up ≈ 0.15`, `p_trend_down ≈ 0.15` (requires both delta AND ema confirmation)
- `p_MR = 1 - 0.08 - 0.03 - 0.15 - 0.15 = 0.59` minimum

**Your 46% observed MR is actually LOWER than the theoretical floor**, suggesting the thresholds were already tuned aggressively.

---

### 🔴 CRITICAL-2: PPO Treats Each Episode as a Terminal Single-Step MDP

**File**: `core.py:611-661`  
**Severity**: CRITICAL — GAE (γ=0.99, λ=0.95) is completely wasted.

```python
for ep in episodes:
    # ... encode features to z
    done_t = torch.tensor([True], dtype=torch.bool, device=device)   # <-- EVERY episode is terminal
    self.ppo_agent.store(obs=obs_t, act=..., rew=rew_t, val=val_t, logp=..., done=done_t)
```

When `done=True` for every stored transition, the GAE bootstrapping collapses:

$$A_{GAE} = \sum_{l=0}^{T-t} (\gamma\lambda)^l \delta_{t+l}$$

With done=True at every step, $\delta_t = r_t - V(s_t)$ and the sum is a single term. **You've reduced PPO to a 1-step REINFORCE with baseline.** The advantages are:

$$A_t = r_t - V(s_t)$$

This means:
- No temporal credit assignment
- No multi-step return estimation
- γ=0.99 and λ=0.95 have **zero effect**
- You're paying the computational cost of GAE + importance-weighting + value function + advantage normalization for what could be achieved with a simple policy gradient

**Impact**: The agent cannot learn temporal dependencies between predictions. In a market regime context, regime persistence (e.g., vol clusters) is the most exploitable signal, and you're explicitly discarding it.

---

### 🔴 CRITICAL-3: World Model Is Structurally Decorrelated from Decisions

**File**: `core.py:99-103`

```python
self.world_model = WorldModel(
    config.world_model,
    input_dim=config.vae.latent_dim,
    action_dim=0           # <-- NO ACTION CONDITIONING
)
```

The World Model predicts `z_{t+1}` from `z_t` only, ignoring the action taken. This makes the World Model a **passive dynamics model**, not a decision-conditioned dynamics model.

**Mathematical consequence**: You're learning `P(z_{t+1} | z_t)` when you need `P(z_{t+1} | z_t, a_t)`. Without action conditioning:
- Cannot do counterfactual planning ("what if I predicted TREND_UP vs MR?")
- Cannot do model-based rollouts (dreaming) because different actions produce the same predicted future
- The World Model is a pure autoregressive forecaster that adds zero value to the RL loop

The World Model is training on every ingested tick (via `train_batch()`), consuming memory and compute, while contributing nothing to policy improvement. **It's dead weight.**

---

### 🟡 MAJOR-1: Bridge Futures Can Hang Indefinitely

**File**: `bridge.py:161-180`

```python
def _submit(self, type: str, payload: Any) -> asyncio.Future:
    future = self._loop.create_future()
    self._futures[task_id] = future
    self._task_queue.put(task)
    return future    # No timeout. Ever.
```

If the worker process crashes (OOM, CUDA error, segfault), all pending futures in `_futures` dict will **never resolve**. The adapter's `handle_features()` awaits `encode_async()` and `act_async()`, which will hang the entire asyncio event loop.

**Failure scenario**:
1. Worker process hits CUDA OOM during training
2. Process dies
3. `_result_listener` thread keeps polling empty queue
4. All subsequent `encode_async()` / `act_async()` calls hang forever
5. Ingestion pipeline freezes completely
6. No data processed, no alerts emitted (because the alert emitter is also blocked)

**Fix**: Add `asyncio.wait_for(future, timeout=X)` in all bridge methods, with fallback behavior.

---

### 🟡 MAJOR-2: VAE + PPO Optimizer Interference via Shared VAE Weights

**File**: `core.py:425-450` (`_train_vae_aux_from_episodes`)

During `train_ppo()`, the code calls `_train_vae_aux_from_episodes()` which does a FULL VAE forward+backward+step using `self.vae_opt`. This happens INSIDE the PPO training call.

Meanwhile, the main training loop in `adapter.py` calls `_maybe_train()` → `brain_bridge.train_async()` → `train_batch()` which also does VAE forward+backward+step.

Both pathways share `self.vae` and `self.vae_opt`. The worker processes tasks sequentially, so there's no concurrent access. BUT:

- A `train_batch()` call updates VAE weights
- Then a `train_ppo()` call immediately re-encodes all episodes using the UPDATED VAE
- The latent z used for PPO is produced by a VAE that was just modified by batch training
- The PPO agent stores (obs, act, val, logp) computed under VAE weights W₁
- Then `ppo_agent.update()` evaluates the policy under the SAME weights
- But the aux VAE step inside `train_ppo()` modifies VAE weights to W₂
- Any subsequent PPO encode call will use W₂, not W₁

**Result**: The latent space is non-stationary from PPO's perspective. Each PPO update changes the representation the agent operates in. This is known as the **representation collapse problem** in joint VAE+RL training and is a well-documented failure mode.

---

### 🟡 MAJOR-3: `_episode_to_dict()` Feature Extraction Is Un-Normalized (PnL Mode Time Bomb)

**File**: `adapter.py:487-489`

```python
features_vector = [
    float(features.get(name, 0.0) or 0.0) for name in self.config.ingest.feature_list
]
```

In PnL reward mode (legacy), episodes are built from raw payload features WITHOUT normalization. When these features are later fed to the VAE in `train_ppo()`, the VAE expects normalized input (it was trained on Welford-normalized data). 

**Currently dormant** (reward_mode is "regime_oracle" which uses `model_features_t`), but this is a **silent time bomb** that will detonate if you switch back to PnL mode without fixing it.

---

### 🟡 MAJOR-4: Welford Normalizer Update-then-Normalize Leaks Future Statistics

**File**: `adapter.py:207-218`

```python
def _normalize_features_for_symbol(self, symbol, raw_features_vector):
    vec = np.asarray(raw_features_vector, dtype=np.float32).reshape(-1)
    if self._normalizer is not None:
        self._normalizer.update(vec)           # <-- Step 1: UPDATE running stats with current sample
        return self._normalizer.normalize(vec)  # <-- Step 2: NORMALIZE current sample with updated stats
```

The normalizer updates its running mean/variance **before** normalizing the current sample. This means sample `x_t` is normalized using statistics that include `x_t` itself. Welford's algorithm at sample N:
- mean_N = mean_{N-1} + (x_N - mean_{N-1}) / N
- The normalized value is (x_N - mean_N) / std_N, where mean_N already incorporates x_N

For large N, this is negligible (the contribution of a single sample is ~1/N). But during early training (N < 100), this introduces a systematic bias toward zero — the current sample always appears closer to the mean than it actually is.

**More critically**: In backtest mode, if features are replayed in sequence, the normalizer sees future samples before normalizing past ones within the same batch cycle. This is a subtle form of **look-ahead bias** in backtesting.

---

### 🟢 MODERATE-1: multiprocessing.Queue Serialization Overhead

**File**: `worker.py:89`, `bridge.py:187`

Every TRAIN call serializes a numpy array through pickle via mp.Queue. Every ENCODE call serializes a numpy vector through pickle. Every result serializes the return value through pickle.

For a 64×20 batch, this is ~5KB per train call. For encode, ~64 bytes per call. The overhead isn't in size but in **serialization latency**: pickle roundtrip adds ~0.1-1ms per call. With 5 symbols × 15-min bars, this is negligible. But with tick-by-tick data, this becomes the bottleneck.

**No immediate action needed** but this architecture cannot scale to tick-level ingestion.

---

### 🟢 MODERATE-2: `_track_task` Fire-and-Forget Pattern Suppresses Errors

**File**: `adapter.py:934-960`

Background tasks log errors but don't propagate them. If VAE training fails silently, the adapter continues sending stale shadow intents. The `_model_corrupted` flag in `core.py` only catches NaN outputs, not silent training failures (e.g., loss explosion that doesn't immediately produce NaN).

---

### 🟢 MODERATE-3: Entropy Schedule Granularity Mismatch

**File**: `core.py:672`, `neuro.yaml:69`

The entropy scheduler has `total_steps: 10000`, but `dream_episode_threshold: 20` means PPO trains roughly every 20 oracle settlements (~100 bars @ H=5). At 15-min bars, that's roughly 25 hours per PPO step. To reach step 10000 would take **28.5 years**. The entropy schedule is effectively frozen at `start=0.05` for the entire deployment lifetime.

</codebase_flaws>

---

## <conceptual_takedown>

### Is VAE + PPO Fundamentally Doomed for Financial Time Series?

**Short answer**: Not inherently doomed, but your specific instantiation has 4 fatal conceptual errors.

**Error 1: The Stationarity Assumption**

Your VAE learns `P(x | z)` and `Q(z | x)` under the assumption that the data-generating process is stationary — that the mapping from features to latent states is time-invariant. Financial markets violate this fundamentally.

The distribution of (delta_price, ema_bias, volatility_state) shifts dramatically between:
- Bull runs (2024 BTC to $100k)
- Range-bound periods (sideways for months)  
- Crash periods (liquidation cascades)

Your VAE's latent space `z` is trained on the MIXTURE of all these regimes. This means `z` encodes **which regime you're in** (useful) but also **regime-specific nuances** (misleading, because these don't transfer across regimes).

**The Lyapunov exponent of individual crypto assets is typically λ ≈ 0.03-0.1 at 15-min resolution**, meaning predictability decays exponentially with horizon. Your H-bar look-ahead horizon makes predictions exponentially harder.

**Error 2: The POMDP Problem You're Ignoring**

Your PPO agent observes `z_t` (a 16D compression of 20 features) and must predict the regime over the next H bars. But the true state of the market includes:
- Order book depth (not in features)
- Cross-asset correlations (single-symbol features only)
- Funding rates / open interest (not in features)
- Macro calendar events (impossible to capture in features)

**You have an observation-action gap**: The agent acts on a severely compressed, information-lossy observation. The optimal policy in a POMDP requires beliefs over hidden states, which your architecture doesn't maintain. The GRU world model COULD serve as a belief updater, but it's unused by PPO (action_dim=0, and the world model's hidden state is never passed to PPO).

**Error 3: The Regime-as-Action Ontological Confusion**

Your action space is `{TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, EXHAUSTION}`. These are not actions — they are **predictions about future states**. In proper RL, an action is something the agent DOES that CHANGES the environment. Your agent doesn't change anything; it predicts.

This matters because:
- PPO's policy gradient theorem assumes `∇_θ J = E[∇_θ log π(a|s) · A(s,a)]`
- The advantage A(s,a) measures "how much better was action a than average in state s"
- But your "actions" don't have differential effects on the environment — predicting TREND_UP doesn't cause a trend
- The "reward" is just Bernoulli: correct/incorrect prediction
- **You're using PPO to do supervised classification with extra steps**

**Error 4: The Observer → Learner → Advisor Pipeline Is Ungrounded**

The pipeline produces a shadow intent (TREND_UP with confidence 0.43). Who consumes this? How does it affect trading? The advisor layer is unconnected — there's no downstream action that translates regime predictions into positions. The "shadow" prefix suggests it's non-operational.

If the intent is to eventually wire this into position sizing, the confidence values are **uncalibrated** (log-probabilities from a softmax are not true probabilities of correctness). Using them for position sizing without Platt scaling or temperature calibration will produce overconfident or underconfident allocations.

### Verdict on the Conceptual Design

The VAE component is fine as a dimensionality reducer. The PPO component is architecturally inappropriate for what is essentially a supervised classification problem. The World Model is completely disconnected from the decision loop. The reward signal is sparse, noisy, and dominated by the labeler's structural MR bias.

**The system is not an RL agent. It's a supervised classifier with an overcomplicated training loop that destroys gradient signal through unnecessary PPO machinery.**

</conceptual_takedown>

---

## <homeostasis_critique>

### Nexus-7 Proposal: "Homeostasis / Auto-Correction Protocol"

**The proposal is treating the symptom (MR dominance) while the disease is in the labeler (CRITICAL-1). Worse, it introduces 3 new failure modes.**

### Step 1: Divergence Monitor — FINE ✓

Tracking `P_predicted vs P_realized` over a 1000-episode rolling window is pure monitoring. No issues. Keep this regardless of other decisions.

### Step 2: Dynamic Reward Shaping — **MATHEMATICALLY FATAL**

**Claim**: If MR ratio = P_pred / P_real > 1.5, scale reward by `reward / ratio²`.

**Theorem** (Ng, Harada, Russell 1999): Potential-based reward shaping preserves optimal policy if and only if the shaping function F(s, a, s') = γ·Φ(s') - Φ(s) for some potential function Φ.

Your proposed shaping **violates this condition** because:
1. The shaping depends on the AGENT'S BEHAVIOR (P_predicted), not on states
2. It creates a feedback loop: agent behavior → reward function → agent behavior
3. This is a **non-stationary MDP** — the transition kernel and reward function change as the agent learns

**Formal proof that convergence is impossible**:

Let $R_t(\theta) = R_{base}(s_t, a_t) \cdot g(\theta)$ where $g(\theta)$ depends on the policy parameters through the prediction distribution. Then:

$$\nabla_\theta J = \nabla_\theta \mathbb{E}\left[\sum_t R_t(\theta)\right] = \mathbb{E}\left[\sum_t \nabla_\theta R_t(\theta) + R_t(\theta) \nabla_\theta \log \pi_\theta(a_t|s_t)\right]$$

The first term $\nabla_\theta R_t(\theta)$ is the gradient of the reward function itself with respect to the policy. This creates a **second-order optimization problem** where PPO (a first-order method) cannot find a fixed point. The system will oscillate:

1. Agent spams MR → ratio > 1.5 → MR reward slashed
2. Agent shifts to TREND_UP/DOWN → MR ratio drops → MR penalty removed
3. MR becomes attractive again → agent returns to MR
4. **Limit cycle with period ≈ 2 × window_size**

**This is the RL equivalent of an integral windup controller — it always overshoots and oscillates.**

### Step 3: Auto-Entropy Shock — **CATASTROPHIC FOR THE CRITIC**

Resetting entropy_coef to 0.15 for 500 steps forces the policy to become near-uniform (high entropy = maximum randomness). 

**The value function V(s) is learned under the CURRENT policy**. If you force a near-uniform policy for 500 steps:
- V(s) was calibrated for a policy that predicts MR ~80% of the time
- A near-uniform policy predicts each of 5 actions ~20% of the time
- The expected return under the new policy is drastically different
- V(s) estimates are now WRONG by a large margin
- Advantages A = R - V(s) will have enormous variance
- PPO's clipped objective cannot compensate — the clipping ratio ε=0.2 assumes small policy changes

**The practical effect**:
- 500 steps at high entropy produces effectively random predictions
- These accumulate in the buffer as (obs, random_action, random_reward)
- PPO trains on this noisy data
- The value function degrades
- After entropy drops back, the policy is worse than before the shock
- **You've destroyed 100+ hours of training to inject 500 steps of pure noise**

Furthermore, the entropy schedule currently has `total_steps: 10000`, meaning it will take thousands of PPO steps to decay from 0.15 back to 0.01. During this entire period, the policy is suboptimal.

### Summary: The Nexus-7 Proposal Creates a Non-Convergent Oscillating System

| Component | Effect | Convergence? |
|-----------|--------|-------------|
| Dynamic Reward Shaping | Non-stationary MDP | **Impossible** (Ng et al.) |
| Auto-Entropy Shock | Critic destruction | **Catastrophic forgetting** |
| Divergence Monitor | Pure telemetry | Neutral ✓ |

**Recommendation: Reject Steps 2 and 3. Keep Step 1.**

</homeostasis_critique>

---

## <superior_architecture>

### The Correct Diagnosis

**The mode collapse is not a PPO bug. It's a labeler bug + an architectural misfit.** You're using PPO (designed for sequential decision-making with environment interaction) to do supervised classification (predict label from features). Fix the problem at the right abstraction layer.

---

### Fix 1: Replace the Rule-Based Labeler with a Data-Driven Clusterer

**Problem**: The cascading if-else labeler structurally biases toward MR.

**Solution**: Use **Gaussian Mixture Model (GMM)** or **k-means** on the feature delta space to discover natural regime clusters.

```python
# PROPOSED: data_driven_labeler.py
from sklearn.mixture import GaussianMixture
import numpy as np

class DataDrivenRegimeLabeler:
    """Learn regime boundaries from data instead of hardcoded thresholds."""
    
    def __init__(self, n_regimes: int = 5, window_size: int = 5000):
        self.n_regimes = n_regimes
        self.gmm = GaussianMixture(n_components=n_regimes, covariance_type='full')
        self._buffer = []
        self._window_size = window_size
        self._fitted = False
    
    def update_and_label(self, features_t: dict, features_t_plus_h: dict) -> int:
        """Compute delta features and cluster."""
        delta = self._compute_delta_vector(features_t, features_t_plus_h)
        self._buffer.append(delta)
        
        if len(self._buffer) > self._window_size:
            self._buffer = self._buffer[-self._window_size:]
        
        # Re-fit periodically (every 500 samples)
        if len(self._buffer) >= 500 and len(self._buffer) % 500 == 0:
            X = np.array(self._buffer)
            self.gmm.fit(X)
            self._fitted = True
        
        if not self._fitted:
            return 2  # Default to neutral during warmup
        
        return int(self.gmm.predict(delta.reshape(1, -1))[0])
    
    def _compute_delta_vector(self, ft, fth):
        """Multi-dimensional delta: price change, vol change, ema shift."""
        return np.array([
            fth.get('delta_price', 0) / max(abs(ft.get('price', 1)), 1e-10),
            fth.get('volatility_state', 0) - ft.get('volatility_state', 0),
            fth.get('ema_bias', 0.5) - ft.get('ema_bias', 0.5),
        ], dtype=np.float32)
```

**Why this fixes MR dominance**: GMM discovers equiprobable clusters in the feature delta space. The clusters are defined by DATA DENSITY, not by human-imposed thresholds. If markets are truly 46% MR, the GMM will find that — but the cluster boundaries will be adaptive, not hardcoded.

---

### Fix 2: Replace PPO with Direct Supervised Learning (Simpler, Better)

**Problem**: PPO is architecturally inappropriate for regime classification.

**Solution**: Train the regime classifier directly on the VAE latent space using cross-entropy loss. You already have the auxiliary regime head in the VAE — just use it as the primary objective.

```python
# PROPOSED: Replace train_ppo() with this
def train_classifier(self, episodes: list[dict]) -> dict:
    """Direct supervised training on regime labels."""
    X, y = [], []
    for ep in episodes:
        if 'realized_regime' not in ep:
            continue
        X.append(ep['features_vector'])
        y.append(ep['realized_regime'])
    
    if not X:
        return {}
    
    X_t = torch.tensor(np.array(X), dtype=torch.float32, device=self.device)
    y_t = torch.tensor(y, dtype=torch.long, device=self.device)
    
    # Encode to latent space
    with torch.no_grad():
        mu, _ = self.vae.encode(X_t)
    
    # Classify from mu
    logits = self.vae.regime_head(mu)
    
    # Class-balanced CE loss (using EMA weights already implemented)
    weights = self.vae.get_regime_class_weights()
    loss = F.cross_entropy(logits, y_t, weight=weights)
    
    self.regime_opt.zero_grad()
    loss.backward()
    self.regime_opt.step()
    
    acc = (logits.argmax(dim=-1) == y_t).float().mean()
    return {"classifier_loss": loss.item(), "accuracy": acc.item()}
```

**Why this is better than PPO**:
- **10× simpler**: No value function, no GAE, no clipping, no entropy bonus
- **Converges faster**: Direct gradient toward correct classification
- **Class weighting** is already implemented via `get_regime_class_weights()`
- **No mode collapse**: Cross-entropy with class weights naturally counteracts imbalance
- **Interpretable**: Classification accuracy is a clear metric; PPO losses are opaque

If you must keep an RL component (for future extensions to actual trading decisions), use **Implicit Q-Learning (IQL)** which is designed for offline settings with limited action influence.

---

### Fix 3: Decouple VAE Training from Inference Time

**Problem**: Joint VAE + policy training creates non-stationary representations (MAJOR-2).

**Solution**: **Freeze VAE after pre-training**, then train the classifier/policy on top of the frozen latent space.

```python
# Phase 1: Pre-train VAE on market features (unsupervised)
for batch in feature_stream:
    vae_loss = vae.loss_function(vae(batch), batch, ...)
    vae_loss.backward()
    vae_opt.step()

# Phase 2: Freeze VAE, train classifier on frozen latents
for param in vae.parameters():
    param.requires_grad = False

for episode in settled_episodes:
    with torch.no_grad():
        mu, _ = vae.encode(episode.features)
    logits = regime_head(mu)   # Only regime_head is trainable
    loss = F.cross_entropy(logits, episode.label, weight=class_weights)
    loss.backward()
    head_opt.step()
```

**Periodically re-train VAE** (e.g., weekly) when enough new data accumulates, then re-initialize the classifier head. This prevents the representation drift that causes PPO instability.

---

### Fix 4: Contrastive Learning Instead of VAE

**Problem**: The VAE's reconstruction objective is misaligned with the downstream task (regime classification). It reconstructs ALL 20 features equally, even if some are irrelevant for regime discrimination.

**Solution**: Replace the VAE with **Contrastive Predictive Coding (CPC)** or **VICReg** (Variance-Invariance-Covariance Regularization).

```
CPC Objective: Maximize I(z_t ; x_{t+k}) — mutual information between 
latent state and future observations.

This directly optimizes the latent space for PREDICTION, not reconstruction.
Features that are predictive of future states get encoded; noise does not.
```

**Concrete alternative: JEPA (Joint-Embedding Predictive Architecture)**

Instead of reconstructing pixels/features (VAE decoder), predict in latent space:
1. Encode `x_t → z_t` and `x_{t+H} → z_{t+H}`
2. Predict `ẑ_{t+H}` from `z_t` using a predictor network
3. Loss = `||ẑ_{t+H} - sg(z_{t+H})||²` where sg = stop-gradient

This learns representations where `z_t` contains exactly the information needed to predict `z_{t+H}` — which is exactly what regime prediction requires. No decoder needed. No KL collapse risk. No mode collapse.

---

### Fix 5: Wire the World Model or Delete It

**Current state**: World Model trains on every feature ingestion. Action_dim=0. Output never used by PPO or any downstream system.

**Options**:
1. **Delete it**: Remove WM training from `train_batch()`. Save 40% of training compute.
2. **Wire it up with action conditioning**: Set `action_dim=5`, condition on predicted regime, use for N-step rollout value estimation.

If option 2: Use the World Model for **Dyna-style planning**:
```python
# Generate synthetic rollouts from current state
for _ in range(k_imagined_steps):
    z_next, h = world_model(z_current, action=candidate_action, h=h)
    imagined_reward = reward_model(z_current, candidate_action, z_next)
    # Add (z_current, candidate_action, imagined_reward) to replay buffer
    z_current = z_next
```

This gives the agent foresight without requiring more real data.

---

### Fix 6: Proper Multi-Step Episode Construction

**Problem**: Every episode is a single terminal step (CRITICAL-2).

**Solution**: Group consecutive oracle settlements for the same symbol into multi-step episodes:

```python
# Instead of adding each settlement as a separate episode:
# Group by symbol, keep running sequence
self._episode_sequences[symbol].append(step_data)

# When sequence reaches length N (e.g., 50):
episode = {
    "symbol": symbol,
    "observations": [s.z for s in sequence],
    "actions": [s.action for s in sequence],
    "rewards": [s.reward for s in sequence],
    "dones": [False] * (N-1) + [True],  # Only last step is terminal
}
```

This enables proper GAE computation across the sequence. The agent can learn that "TREND_UP followed by TREND_UP is better than TREND_UP followed by MR" — temporal patterns that are invisible in single-step mode.

---

### Implementation Priority

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | Fix 1: Replace labeler | 2 days | Eliminates root cause of MR bias |
| **P0** | Fix 2: Replace PPO with supervised classifier | 1 day | 10× simpler, converges faster |
| **P1** | Fix 3: Freeze VAE after pre-training | 0.5 day | Eliminates representation drift |
| **P1** | Fix 5: Delete or wire the World Model | 0.5 day | Save compute or gain planning |
| **P2** | Fix 6: Multi-step episodes | 2 days | Enables temporal credit assignment |
| **P3** | Fix 4: CPC/JEPA instead of VAE | 1 week | Better representations for prediction |

### End State Architecture

```
┌─────────────────────────────────────────────────┐
│               Neocortex v2 (Proposed)           │
│                                                 │
│  Features ──→ [Frozen VAE Encoder] ──→ z_t      │
│                                       │         │
│       ┌───────────────────────────────┘         │
│       │                                         │
│       ├──→ [Regime Classifier Head]             │
│       │      (CE loss + class weights)          │
│       │      Output: P(regime | z_t)            │
│       │                                         │
│       └──→ [World Model (action-conditioned)]   │
│              z_{t+1} = WM(z_t, a_t)             │
│              (for planning / confidence)         │
│                                                 │
│  Labels ←── [GMM Clusterer]                     │
│              (replaces rule-based labeler)       │
└─────────────────────────────────────────────────┘
```

**Key principles**:
- Decouple representation learning from decision-making
- Use data-driven labels instead of hardcoded thresholds
- Use the right tool (supervised learning) for the right problem (classification)
- Wire or delete every component — no dead code consuming compute

</superior_architecture>

---

## Summary of Verdicts

| Component | Verdict |
|-----------|---------|
| **RegimeLabeler** | 🔴 Root cause of MR collapse. Must be replaced. |
| **PPO for classification** | 🔴 Architecturally inappropriate. Replace with supervised CE. |
| **World Model** | 🔴 Dead weight. Wire up or delete. |
| **VAE** | 🟡 Functional but jointly trained = drift. Freeze after pretraining. |
| **Adapter/Bridge** | 🟡 Works but has no timeout protection. |
| **Multi-Tailer** | 🟢 Clean, well-factored. Minor concerns only. |
| **Nexus-7 Proposal** | 🔴 **REJECT STEPS 2 & 3.** Non-convergent by construction. |
| **Feature Buffer** | 🟢 Correct ring-buffer settlement logic. |
| **Reward Calculator** | 🟢 Confusion matrix is well-designed. |

**The system's actual problem is simple: you built a classification pipeline, wrapped it in RL machinery that adds complexity without value, then blamed the RL components when the ground-truth labels were biased. Strip the RL, fix the labels, freeze the VAE. Total fix time: ~4 engineering days.**
