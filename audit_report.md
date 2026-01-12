# Audit Report: GSB Target Predictor Candidates

## Executive Summary
The audit of the `apps/reference` codebase confirms, with high confidence, that the **Neocortex** domain contains a fully compatible, pre-existing predictive architecture suitable for replacing the GSB Oracle.

The `WorldModel` class, orchestrated by `BrainCore`, is explicitly designed to model the dynamics of the VAE latent space ($z_t \to z_{t+1}$). This is mathematically equivalent to the requirement for a GSB target predictor.

## Identified Candidates

### Candidate 1: WorldModel (Recommended)
*   **Path:** `apps/reference/domains/neocortex/logic/brain/world_model.py`
*   **Architecture:** GRU-based Recurrent Neural Network.
*   **Inputs:** VAE Latent State $z_t$ (Dimension: `config.vae.latent_dim`, typically 32 or 64) and optional Action $a_t$.
*   **Outputs:** Predicted Next Latent State $\hat{z}_{t+1}$.
*   **Horizon:** Recursive. One-step natively, but designed for multi-step "dreaming" (rollouts).
*   **Type:** Point prediction (can be wrapped as Gaussian mean).
*   **Suitability Score:** **10/10**
    *   **Native Compatibility:** Operates directly on the exact $z$ space used by the VAE.
    *   **Existing Training:** `BrainCore` already trains this model via `wm_loss` (MSE) in `train_batch`.
    *   **Purpose:** Explicitly built for "Simulating futures" (docstring line 9).

### Candidate 2: VariationalAutoencoder (VAE)
*   **Path:** `apps/reference/domains/neocortex/logic/brain/vae.py`
*   **Architecture:** MLP Encoder / Decoder.
*   **Inputs:** Raw market features $x_t$.
*   **Outputs:** Latent distribution parameters $\mu, \log\sigma^2$.
*   **Suitability Score:** **N/A (Prerequisite)**
    *   Does not predict the future. It defines the state space for the World Model. Ideally, GSB should bridge $z_t$ (from VAE) to $z_{t+T}$ (from World Model).

### Candidate 3: ActorCriticLSTM (PPO)
*   **Path:** `apps/reference/domains/neocortex/PPO/.../actor_critic_lstm.py`
*   **Architecture:** LSTM with Policy/Value heads.
*   **Inputs:** Latent state $z_t$.
*   **Outputs:** Action probabilities $\pi(a|s)$ and Value $V(s)$.
*   **Suitability Score:** **3/10**
    *   Predicts rewards/actions, not state transitions. $V(s)$ is a scalar proxy for future success, but GSB requires a high-dimensional state target for the bridge.

## Implementation Recommendation

We do **not** need to build a "Lightweight Latent MLP". We should utilize the existing `WorldModel` within `BrainCore`.

**Proposed Integration Plan:**

1.  **Access:** In the GSB module, obtain a reference to the `BrainCore` instance (or its `world_model`).
2.  **Target Construction ($\pi_T$):**
    *   Get current state $z_0$ from VAE.
    *   Run `world_model` recursively for $T$ steps to get $\hat{z}_T$.
    *   Define target distribution $\pi_T = \mathcal{N}(\hat{z}_T, \Sigma_{fixed})$.
3.  **Bridge:** Solves for the path between Dirac($z_0$) and $\pi_T$.

**Code Snippet (Concept):**
```python
# Inside GSB logic
def get_target_distribution(brain_core, z_current, T=5):
    z_pred = z_current
    h = None
    # "Dream" T steps into the future
    for _ in range(T):
        z_pred, h = brain_core.world_model.forward(z_pred, h=h)
    
    # z_pred is now estimate of z_{t+T}
    return z_pred # Usable as Mean of Target Gaussian
```
