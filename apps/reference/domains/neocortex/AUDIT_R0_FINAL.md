# Neocortex Deep Audit — R0 Final (2026-01-12)

**Scope:** `apps/reference/domains/neocortex/` (Python domain code + vendored `PPO/ppo_library_v2`)  
**Mode:** Static + logic review (simulated linters via search + manual code reading)  
**Context:** Aurora migrating from Ticks → Bars; Neocortex paused; opportunity to burn down risk.

This report is intentionally ruthless: anything that can cause silent data loss, unstable training, or “it ran but learned nothing” is flagged.

---

## 1) Code Quality Score (A–F)

**Overall:** **D**

### Score breakdown

| Area | Grade | Why |
|---|---:|---|
| Type safety | D+ | High `Any` usage in production paths; weak domain-level contracts for payloads/episodes. |
| Observability / logging | D | Extensive f-string logging + emoji/encoding artifacts; inconsistent severity; `print()` in runtime entrypoints and tools. |
| Runtime robustness | D | Broad exception handling; path resolution depends on CWD; multiprocessing lifecycle warnings. |
| ML correctness | D- | World model sequence bug; VAE loss scaling + no grad clipping; normalization not applied despite config support. |
| Test posture | D | Tests exist but **Neocortex tests are excluded from the default pytest suite** (`pytest.ini`). |

---

## 2) Critical Issues (Must Fix)

### CI-1: Neocortex tests are not executed by default

**Evidence**
- `pytest.ini` → `testpaths` does **not** include `apps/reference/domains/neocortex/tests`.

**Impact**
- CI can go green while Neocortex is broken (shape mismatches, ingest regressions, ML failures).

**Fix direction**
- Add `apps/reference/domains/neocortex/tests` to `pytest.ini:testpaths` (or move tests under `tests/`).
- Run them in the “core” suite, not only manually.

---

### CI-2: Normalization is configured but not applied in the ingest pipeline

**Evidence**
- Config defines normalization knobs (`apps/reference/domains/neocortex/config_models.py` → `normalization_method`, `normalization_window`).
- `FeatureParser.parse()` writes raw floats into `features_vector` (`apps/reference/domains/neocortex/logic/ingest/parser.py`), with only NaN-to-zero handling.
- Online normalizer exists (`apps/reference/domains/neocortex/logic/ingest/normalizer.py`) and is tested, but is **not wired** into the runtime ingest.

**Impact**
- Raw magnitudes (e.g., `price`, `spread_bps`) can dominate MSE; training becomes unstable, sensitive to regime changes, and hard to compare across runs.
- The system can “train” (loss decreases) while learning trivial scale artifacts.

**Fix direction**
- Make normalization part of the ingest boundary:
  - Instantiate `WelfordNormalizer` (or robust alternative) in the ingest parser/adapter layer.
  - Persist/load state using a deterministic path under the domain’s data dir.
  - Add optional winsorization/clipping for heavy-tailed features.

---

### CI-3: World Model is effectively trained with `Seq=1` (temporal learning bug)

**Evidence**
- `BrainCore.train_batch()` builds `z_in = z[:-1]` and calls `world_model(z_in)` (`apps/reference/domains/neocortex/logic/brain/core.py`).
- `WorldModel.forward()` converts 2D to 3D via `unsqueeze(1)` (`apps/reference/domains/neocortex/logic/brain/world_model.py`), forcing `Seq=1`.

**Impact**
- The world model does not learn multi-step dynamics; it becomes a shallow “next-state” mapper with no temporal context.
- Any “dreaming / planning” built on this is unreliable.

**Fix direction**
- Represent sequences explicitly: feed `(B=1, Seq=T, latent_dim)` and train across `T-1` transitions.
- Add a test that asserts `Seq > 1` reaches the GRU in training.

---

### CI-4: VAE loss scaling is unbounded + no gradient clipping in BrainCore

**Evidence**
- VAE uses `mse_loss(..., reduction='sum')` and sums KLD (`apps/reference/domains/neocortex/logic/brain/vae.py`), so loss scales with `batch_size * dim`.
- `BrainCore.train_batch()` does `zero_grad()`, `backward()`, `step()`, but never clips gradients (`apps/reference/domains/neocortex/logic/brain/core.py`).
- PPO library *does* clip gradients during update, but VAE/WM do not.

**Impact**
- Risk of exploding gradients / NaN loss in volatile regimes, especially pre-normalization.
- Telemetry of loss magnitude is misleading (depends on batch size and feature dim).

**Fix direction**
- Use `reduction='mean'` or normalize sum by batch size (and optionally feature dim).
- Add gradient clipping (`clip_grad_norm_`) for VAE/WM optimizers.
- Add NaN/Inf checks on losses and gradients.

---

### CI-5: MultiTailer offsets are rotation-safe for core log only (silent data loss risk)

**Evidence**
- `_process_core()` checks truncation/rotation and resets offset when `offset > file_size` (`apps/reference/domains/neocortex/logic/ingest/multi_tailer.py`).
- `_process_features()` and `_process_orders()` do **not** apply equivalent truncation/rotation handling.

**Impact**
- Feature/order streams can silently stall or skip data after rotation/truncation, producing “no training triggered” symptoms while trading continues.

**Fix direction**
- Implement the same truncation/rotation guard for all tailed sources.
- Add tests simulating file truncation for each stream (features/orders/core).

---

### CI-6: Path resolution depends on process CWD (checkpoint/log locations can silently move)

**Evidence**
- `SystemConfig.resolve_paths` uses `Path(v).resolve()` (`apps/reference/domains/neocortex/config_models.py`).
- YAML uses relative `data_dir: "./data"` and `checkpoint_dir: "./data/checkpoints"` (`apps/reference/domains/neocortex/config/system.yaml`).

**Impact**
- Running Neocortex from different working directories yields different resolved paths.
- This causes confusion when “wiping checkpoints” (you delete the wrong directory), and can split telemetry across multiple locations.

**Fix direction**
- Resolve paths relative to a known anchor:
  - the domain root (`apps/reference/domains/neocortex/`), or
  - the config directory (`apps/reference/domains/neocortex/config/`), or
  - an explicit `project_root`.

---

### CI-7: Logging anti-patterns at scale (f-string logging, emoji/encoding artifacts)

**Evidence (counts, `.py` only)**
- f-string logging calls: **124** occurrences (`logger.(debug|info|warning|error)(f"...")`).
- `print()` calls: **85** occurrences across domain + living_latent.
- There are encoding artifacts (`�`) visible in log strings (e.g. governor log lines).

**Impact**
- f-strings compute eagerly even when the log level is disabled (avoidable overhead).
- Emoji/log encoding issues can break log parsers and file tailers.
- Mixing `print()` with logging breaks observability consistency.

**Fix direction**
- Replace f-string logger calls with parameterized logging:
  - `logger.info("x=%s y=%s", x, y)`
- Remove or quarantine `print()` blocks behind `if __name__ == "__main__"` or a dedicated CLI tool.
- Standardize UTF-8 end-to-end (files, handlers, console).

---

### CI-8: Hardcoded values exist in production logic (must be config-driven)

**High-risk examples**
- `ValuationEngine` uses `trace_decay=0.95`, `deque(maxlen=100)`, and epsilon `1e-5` (`apps/reference/domains/neocortex/logic/amygdala/valuation.py`).
- Reward normalization uses `tanh(raw_pnl / 10.0)` (`apps/reference/domains/neocortex/logic/ingest/multi_tailer.py`).
- PPO seed is hardcoded to `42` (`apps/reference/domains/neocortex/logic/brain/core.py`).
- “Dream trigger threshold” is hardcoded (debug value) in the adapter (`apps/reference/domains/neocortex/transport/adapter.py`).

**Impact**
- Behavior changes require code deploys instead of config changes.
- Debug constants can accidentally ship to production.

**Fix direction**
- Put all training thresholds, epsilons, scaling factors, and decay constants into config models.
- Add validation + telemetry output for all active values at startup.

---

## 3) ML Best Practices Gaps (Should Fix)

### BP-1: PPO state dimension config is not enforced by the runtime integration

**Evidence**
- Config: `ppo.state_dim: 20` (`apps/reference/domains/neocortex/config/neuro.yaml`).
- PPO initialization uses observation space shape `(vae.latent_dim,)` (`apps/reference/domains/neocortex/logic/brain/core.py`), ignoring `ppo.state_dim`.

**Impact**
- Config suggests PPO uses latent+context, but actual PPO sees only the latent vector.
- “State dim” drift will be invisible until a downstream failure.

**Fix direction**
- Either:
  - enforce `ppo.state_dim == vae.latent_dim` (and remove misleading config), or
  - implement context concatenation and validate dimensions strictly.

---

### BP-2: PPO training semantics are mismatched to “trade-close episodes”

**Evidence**
- PPO library is trajectory-based (`n_steps`, GAE); Neocortex ingestion produces sparse, terminal episodes (often one per trade close).
- Default `rollout_length: 2048` is inconsistent with “episode-per-close” cadence.

**Impact**
- PPO updates can be extremely delayed or statistically meaningless.

**Fix direction**
- Define the environment contract:
  - Are we doing step-wise actions per bar, or episodic actions per trade?
- If episodic-per-trade, consider a simpler policy gradient update or reduce `rollout_length` drastically and treat each close as a step.

---

### BP-3: No KL/beta annealing for VAE

**Evidence**
- `beta` is static in config; no annealing schedule exists (`apps/reference/domains/neocortex/logic/brain/vae.py` + config).

**Impact**
- Early training can collapse (posterior collapse or overly-strong KL), especially when features are not normalized.

**Fix direction**
- Implement a warmup schedule: `beta(t)` ramp over N steps.
- Log both MSE and KLD (already available) and alert on collapse patterns.

---

### BP-4: Determinism and reproducibility are incomplete

**Evidence**
- PPO seed is hardcoded to `42`; no consistent seeding across numpy/python/torch in Neocortex runtime.

**Impact**
- Debugging becomes guesswork; “works on my machine” issues multiply.

**Fix direction**
- Add one `system.seed` config.
- Seed python `random`, `numpy`, `torch`, and PPO library (once, early).

---

### BP-5: Outlier robustness is not addressed

**Evidence**
- Welford z-score is sensitive to heavy tails and non-stationarity; no robust scaler or clipping.

**Impact**
- Bars migration will shift distributions; model can destabilize or relearn scale instead of signal.

**Fix direction**
- Add per-feature clipping ranges or robust scaling (median/MAD, quantile clipping).
- Add “feature drift” telemetry (rolling quantiles, z-score saturation rate).

---

## 4) Refactoring Plan (Action Items)

### P0 (must do before re-enabling Neocortex)
1. **Enable Neocortex tests in CI** by adding `apps/reference/domains/neocortex/tests` to `pytest.ini`.
2. **Wire normalization** at ingest boundary and persist its state deterministically.
3. **Fix world model training** to use real sequences (`Seq > 1`) and add regression tests.
4. **Stabilize VAE/WM training**:
   - loss scaling (mean/normalized sum)
   - gradient clipping
   - NaN/Inf guards
5. **Make paths deterministic** (resolve relative to domain root/config dir, not CWD).
6. **Kill f-string logging in hot paths** and remove `print()` from runtime entrypoints.

### P1 (high leverage)
1. **Config-ify all constants** (epsilons, decays, reward scaling, debug thresholds, seed).
2. **Define strict domain contracts**:
   - typed feature payload (`TypedDict`/dataclass)
   - typed episode schema
3. **MultiTailer rotation safety** for all streams + tests.
4. **Tighten exception handling**:
   - replace broad `except Exception:` with narrower exceptions where possible
   - always log with context and `exc_info=True` at appropriate severity

### P2 (quality / performance)
1. **Clarify PPO semantics** (step-wise per bar vs episodic per trade) and align rollout logic accordingly.
2. **Implement beta annealing** and optional LR schedules.
3. **Add drift telemetry** and alerting thresholds (bar regime shifts).

---

## Appendix A: Static scan summary (simulated linters)

**Counts (`.py` only; excludes markdown/docs)**
- f-string logging calls: **124**
- `print()` calls: **85**
- `Any` occurrences: **153**
- `Dict[str, Any]` / `dict[str, Any]` occurrences: **72**
- `except Exception` occurrences: **147** (of which `except Exception:` without binding: **90**)
- Bare `except:` occurrences: **0** (good)
- `import *` occurrences: **0** (good)

**Notes**
- Some broad `except Exception:` blocks are acceptable in “fail-open” guards, but the current volume suggests missing invariants and missing typed boundaries.
- Emoji/logging encoding should be treated as a production compatibility issue (parsers/tailers/JSON logs).

