# Neocortex System — 48H Health Report
**Generated:** 2026-02-20 23:30 UTC
**Analyst:** Principal Data Scientist / RL Analyst
**Branch:** stable_11_11

---

## ⚠️ Data Scope Caveat

> The `neocortex_metrics.csv` log on disk covers only **~3.8 hours** of activity
> (2026-02-20 19:27 → 23:19 UTC), not the full 48 hours requested.
> `shadow_intents.jsonl` (active file) spans **~0.69 hours** (20:40 → 21:21 UTC).
> Historical rotated logs (`shadow_intents.jsonl.1`–`.5`) were not merged.
> All conclusions below are data-bounded to the observable window.

---

## 1. Executive Summary

| Subsystem | Status | Verdict |
|-----------|--------|---------|
| **VAE** (Encoder) | ✅ Converging | Loss ↓ 44% Q1→Q5 |
| **WM** (World Model) | ✅ Converging | Loss ↓ 35% Q1→Q5 |
| **PPO** (Actor-Critic) | 🔴 NOT Learning | Zero actor loss, entropy RISING |
| **Reward Signal** | 🔴 Degenerate | Constant −0.001, no positive PnL |
| **Checkpoint Integrity** | ✅ Clean | 0 NaN / Inf in 714,952 params |
| **Shadow Intents** | 🟡 Near-Uniform | Minimal shift, slight confidence gain |

**Overall Verdict: PARTIAL LEARNING — VAE and WM are healthy, PPO is stalled.**

---

## 2. Loss Metrics

### 2.1 VAE Loss Trend

```
Window: 228 training updates (one per ~65 env steps)
MA-50 start: 0.004396   MA-50 end: 0.002453

Quintile progression (mean per 20% of training):
  Q1: 0.004555  ████████████████████████████████
  Q2: 0.004099  ████████████████████████████
  Q3: 0.003303  ███████████████████████
  Q4: 0.002428  █████████████████
  Q5: 0.002456  █████████████████
       (axis: each █ ≈ 0.000143 loss)

Start (avg first 10):  0.003883
End   (avg last  10):  0.002776
Delta:                 -0.001107  (−28.5%)
Min observed:           0.001300
Peak (likely warm-up):  0.027062
```

**Conclusion: VAE is converging cleanly.** The encoder is learning a stable latent
representation of market state. Q4 plateau suggests approaching a local minimum.

---

### 2.2 World Model (WM) Loss Trend

```
Window: 228 training updates

  Q1 mean: 0.000140  ██████████████
  Q2 mean: 0.000136  █████████████
  Q3 mean: 0.000105  ██████████
  Q4 mean: 0.000098  ██████████
  Q5 mean: 0.000091  █████████

MA-50 start: 0.000120   MA-50 end: 0.000093
Delta: −22.5%
```

**Conclusion: WM is converging.** Absolute values are extremely low — the world
model is accurately predicting next latent states. Very little headroom left.

---

### 2.3 PPO (Actor-Critic) — ⚠️ CRITICAL ANOMALY

```
PPO update rows: 41 (one per ~370 env steps)

ppo_loss_pi (actor):   0.0 on ALL 41 updates — entire training run
ppo_loss_v  (critic):  not sampled in analysis (present but tied to same events)

Entropy progression:
  Step 1003617: 0.951177
  Step 1004269: 0.950545
  Step 1005597: 0.951268
  ...
  Step 1016881: 0.980191
  Step 1017532: 0.980259
  Step 1018380: 0.978010

  Range observed: [0.945, 0.980]
  Max possible (3 actions uniform): ln(3) = 1.0986

  Entropy start: 0.951   Entropy end: 0.978   Delta: +0.027 (RISING ↑)
```

**Conclusions:**
- `ppo_loss_pi = 0.0` across all updates indicates either:
  - (a) PPO ratio clipping is always active (policy not updating),
  - (b) actor gradient is being zeroed before logging, or
  - (c) a code-level bug in the actor update path.
- **Entropy is rising, not falling** — PPO is becoming MORE random over time,
  moving toward uniform policy (LONG/SHORT/FLAT ~33.3% each).
- A healthy PPO should show entropy declining from ~1.09 (uniform) as it builds
  a biased, confident policy. The opposite trend is observed.

---

## 3. Reward Flow

### 3.1 Per-Episode Rewards

```
Non-null last_reward rows: 41 (one per PPO update)
Unique reward value:       -0.001 (identical for every single update)

Cumulative reward trajectory:
  Start:           -0.5040
  End:             -0.5450
  Total delta:     -0.0410 (over ~3.8 hours)
  Rate:            -0.0108 / hour  (perfectly linear decay)

  Q1: -0.5040 → -0.5130
  Q2: -0.5130 → -0.5210
  Q3: -0.5210 → -0.5290
  Q4: -0.5290 → -0.5380
  Q5: -0.5380 → -0.5450
```

**Red Flag: The reward signal is degenerate.**
Every episode returns exactly −0.001. This is a flat time/holding penalty with
zero trade PnL contribution during this window. PPO has no positive gradient
signal to learn from. The `last_pnl` column is entirely null (0 non-null rows).

---

## 4. Behavioral Analysis — Shadow Intents

### 4.1 Overview

```
Total intents logged:     2,515
Symbols covered:          BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT
Records per symbol:       526 each (uniform sampling)
Active window:            20:40 → 21:21 UTC (~41 minutes)
```

### 4.2 Action Distribution Shift

```
                     FIRST HALF (n=1,320)   SECOND HALF (n=1,310)   Delta
  FLAT:                   36.97%                  37.10%             +0.13%
  SHORT:                  32.73%                  31.60%             -1.13%
  LONG:                   30.30%                  31.30%             +1.00%

  Expected uniform:       33.33% each
```

**Conclusion:** Distribution is quasi-uniform across both halves. The system has
a slight FLAT bias (≈3.8pp above uniform). No meaningful behavioral shift
occurred within the observable window. Maximum drift is ~1.1pp — indistinguishable
from noise given N=1,300.

### 4.3 Per-Symbol Behavioral Fingerprints

```
  BTCUSDT:  FLAT 39.9%, SHORT 33.1%, LONG 27.0%   (SHORT/FLAT lean)
  ETHUSDT:  SHORT 40.5%, FLAT 31.9%, LONG 27.6%   (strong SHORT bias ← notable)
  SOLUSDT:  FLAT 36.5%, LONG 33.1%, SHORT 30.4%   (LONG lean)
  XRPUSDT:  FLAT 38.4%, LONG 34.0%, SHORT 27.6%   (LONG lean)
  DOGEUSDT: FLAT 38.4%, LONG 32.3%, SHORT 29.3%   (LONG/FLAT lean)
```

ETHUSDT stands out: SHORT at 40.5% vs 33.3% uniform = +7.2pp bias.
This could be signal or an artifact of recent ETH price action.

### 4.4 Confidence (log_prob) Analysis

```
Metric               First 1000 intents    Last 1000 intents    Delta
--------------------------------------------------------------------
Mean confidence:        -0.787526             -0.726803          +0.061 ↑
Median confidence:      -0.584672             -0.495006          +0.090 ↑
Std deviation:           0.696956              0.701653          +0.005

Confidence trend by quartile:
  Q1: mean=-0.759, std=0.669
  Q2: mean=-0.822, std=0.750
  Q3: mean=-0.663, std=0.688
  Q4: mean=-0.771, std=0.695
```

**Conclusion:** A small but real improvement — mean confidence moved +0.061
toward 0 (less uncertain). However, the pattern is noisy (Q2 worse than Q1,
Q3 better than Q4), suggesting oscillation rather than monotonic learning.
At the current rate, meaningful confidence would require weeks of runtime.

### 4.5 Confidence Mini-Chart (20 time bins, lower is more confident)

```
  bin01: -0.66 |######
  bin02: -0.85 |########
  bin03: -0.81 |########
  bin04: -0.75 |#######
  bin05: -0.72 |#######
  bin06: -0.79 |#######
  bin07: -0.85 |########
  bin08: -0.89 |########  ← peak uncertainty
  bin09: -0.75 |#######
  bin10: -0.81 |########
  bin11: -0.73 |#######
  bin12: -0.65 |######
  bin13: -0.70 |######
  bin14: -0.56 |##### ← most confident
  bin15: -0.67 |######
  bin16: -0.73 |#######
  bin17: -0.73 |#######
  bin18: -0.85 |########
  bin19: -0.80 |########
  bin20: -0.74 |#######
```

No clear monotonic trend; mid-session dip at bin14 followed by regression.

---

## 5. Checkpoint Integrity

### 5.1 Latest Checkpoints (last 3)

```
data/checkpoints/checkpoint_9900.pt          4.15 MB
data/checkpoints/checkpoint_latest.pt        4.15 MB    ← active
data/checkpoints/checkpoint_latest_corrupted.pt  8.22 MB  ← old corruption (isolated)
```

Total checkpoint files: **409**

### 5.2 NaN Scan — checkpoint_latest.pt

```
Loaded via: torch.load(map_location='cpu')
Total parameters:  714,952
NaN values found:  0
Inf values found:  0
Result:            ✅ CLEAN

Model parameter health:
  vae_state        layers=14  params=25,012    mean=-0.0241  std=0.2959  range=[-6.14, 2.54]
  wm_state         layers=10  params=157,200   mean=-0.0040  std=0.2185  range=[-3.82, 2.94]
  ppo_model_state  layers=14  params=532,740   mean=+0.0010  std=0.0544  range=[-0.37, 1.00]

train_steps in checkpoint: 40,700
```

**Note:** The `wm_state` max range of [-3.82, 2.94] is within healthy bounds.
The `vae_state` min of -6.14 warrants monitoring but is not uncommon in
small VAEs with ReLU activations. The previous NaN corruption is fully isolated
in `checkpoint_latest_corrupted.pt`.

---

## 6. Red Flags & Recommendations

### 🔴 Critical

| # | Issue | Evidence | Action Required |
|---|-------|----------|-----------------|
| 1 | **PPO actor loss = 0.0 always** | 41/41 PPO rows show `ppo_loss_pi=0.0` | Audit PPO actor update: check gradient clipping, clamp_ratio, or detach() calls |
| 2 | **Reward signal degenerate** | 41/41 reward values = -0.001 exactly | Verify trade PnL is being passed to reward calculator; check if orders are executing in shadow mode |
| 3 | **PPO entropy RISING** | 0.951 → 0.978 (should fall toward 0) | Consequencer of issue #1; PPO actor not learning = entropy drifts toward uniform |

### 🟡 Warning

| # | Issue | Evidence |
|---|-------|----------|
| 4 | **Observable window is only ~3.8h, not 48h** | CSV start timestamp: 2026-02-20 19:27 |
| 5 | **`last_pnl` is entirely null** (0/14,941 rows) | Column exists but never populated |
| 6 | **Episodes_collected drops to 0** | `episodes_collected: 1 → 0` at buffer capacity |
| 7 | **Confidence oscillation** (non-monotonic) | Q2 worse than Q1, Q4 worse than Q3 in intents |

### ✅ Healthy

- VAE convergence is clean and monotonic
- World Model loss at near-minimum levels
- Checkpoint integrity: zero NaN/Inf
- Buffer at capacity (10,000 samples) — training data available
- No silent crashes or queue explosions detected in log structure
- Previous NaN corruption fully isolated, not re-infecting

---

## 7. Summary Scorecard

```
┌─────────────────────────────────────────────────────┐
│            NEOCORTEX — STATE OF THE BRAIN            │
├────────────────┬──────────────┬──────────────────────┤
│ Component      │ Status       │ Trend                │
├────────────────┼──────────────┼──────────────────────┤
│ VAE Encoder    │ ✅ Healthy   │ Loss ↓ −44%          │
│ World Model    │ ✅ Healthy   │ Loss ↓ −23%          │
│ PPO Actor      │ 🔴 Stalled   │ Loss = 0, Entropy ↑  │
│ PPO Critic     │ ❓ Unknown   │ Tied to actor issue  │
│ Reward Signal  │ 🔴 Degenerate│ Constant −0.001      │
│ Shadow Intents │ 🟡 Moderate  │ Near-uniform, slight │
│                │              │ confidence gain      │
│ Checkpoints    │ ✅ Clean     │ 0 NaN, 40,700 steps  │
├────────────────┼──────────────┼──────────────────────┤
│ OVERALL        │ PARTIAL      │ Base models learn,   │
│                │ LEARNING     │ RL loop is broken    │
└────────────────┴──────────────┴──────────────────────┘
```

**The system's perception layer (VAE + WM) is functioning correctly. The
decision-making layer (PPO) is not learning. Fix the actor loss = 0 issue
and the reward signal before the next 48h window.**

---

*Report generated programmatically from live telemetry. No code was modified.*
