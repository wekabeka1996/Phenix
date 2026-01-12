# Neocortex Deep Audit — R0 Final

**Scope:** `apps/reference/domains/neocortex/` (Python + bundled PPO library)  
**Mode:** Static + logic review only (no code changes in this audit)  
**Context:** Aurora migrating from Ticks → Bars; Neocortex paused; ideal window to burn down risk.

---

## 1) Code Quality Score (A–F)

**Overall:** **D**

**Rationale (high-level):**
- **Strong:** Pydantic config models are strict (`extra='forbid'`, frozen) and the module layout is relatively coherent.
- **Weak:** Multiple ML correctness problems and several production-readiness violations (prints in core worker paths, assert-based runtime checks, logging anti-patterns, and tests not wired into the main pytest suite).

**Sub-scores:**
- **Type Safety:** C-
- **Observability/Logging:** D
- **Runtime Robustness:** D
- **ML Correctness:** D-
- **Test Integration:** D (tests exist, but are not executed by default)

---

## 2) Critical Issues (Must Fix)

### CI-1: PPO update path is structurally broken (buffer `finalize()` never called)

**Evidence**
- `apps/reference/domains/neocortex/logic/brain/core.py:509` calls `self.ppo_agent.update()` once `episodes_stored >= self.ppo_agent.buffer.n_steps`.
- `apps/reference/domains/neocortex/PPO/ppo_library_v2/ppo_system/agent.py:168` calls `batch_data = self.buffer.get()`.
- `apps/reference/domains/neocortex/PPO/ppo_library_v2/ppo_system/learning/buffer.py:121` requires `_finalized == True`, otherwise raises: `"Buffer must be finalized..."`.
- There is **no call** to `TrajectoryBuffer.finalize()` in the Neocortex integration path.

**Impact**
- PPO can appear “wired” and “triggered” but will fail when it actually reaches the update condition.
- If `rollout_length` remains large (default `2048` in `apps/reference/domains/neocortex/config/neuro.yaml:49`), this can hide for a long time.

**Fix direction**
- Decide a real episodic model (single-step episodes vs trajectories).
- Call `buffer.finalize(last_values)` before `update()` (or refactor `PPOAgent.update()` to do it internally).
- Add a failing test that reproduces the current crash.

---

### CI-2: World Model training uses the wrong axis (sequence treated as batch)

**Evidence**
- `apps/reference/domains/neocortex/logic/brain/core.py:189` sets `z_in = z[:-1]` and passes it to `self.world_model(z_in)` at `apps/reference/domains/neocortex/logic/brain/core.py:194`.
- `apps/reference/domains/neocortex/logic/brain/world_model.py:50` configures GRU with `batch_first=True`, expecting `(B, Seq, F)`.
- `apps/reference/domains/neocortex/logic/brain/world_model.py:81` “fixes” 2D input by `unsqueeze(1)`, forcing `Seq=1` always.

**Impact**
- The world model is not learning temporal dynamics across the window; it is effectively trained on independent one-step samples with `Seq=1`.
- Downstream “dreaming” and any planning signals derived from the world model are unreliable.

**Fix direction**
- Represent sequences explicitly: e.g. shape `z_seq` as `(1, T, latent_dim)` and train to predict `z_{t+1}` across `T-1` steps.
- Add tests that assert the GRU sees `Seq > 1` for a training batch.

---

### CI-3: Normalization config exists but is not implemented in the ingestion pipeline

**Evidence**
- Config supports `normalization_method`/`normalization_window` (`apps/reference/domains/neocortex/config_models.py:75`).
- There is no normalization logic in `apps/reference/domains/neocortex/logic/ingest/parser.py` (only basic parsing + NaN handling).

**Impact**
- Raw feature magnitudes (e.g. `price`, `spread_bps`) can dominate MSE and destabilize training.
- This is consistent with observed extreme/unstable `vae_loss` values in telemetry in practice.

**Fix direction**
- Implement a normalization layer (online z-score / robust scaling) in the Neocortex ingestion boundary.
- Add clipping/winsorization for heavy-tailed features.
- Validate normalization against bars (distribution shifts vs ticks).

---

### CI-4: VAE loss scaling is unbounded (sum-reduction without normalization) + no gradient clipping

**Evidence**
- `apps/reference/domains/neocortex/logic/brain/vae.py:152` uses `F.mse_loss(..., reduction='sum')`.
- `apps/reference/domains/neocortex/logic/brain/core.py:173` backprops directly; there is **no** `clip_grad_norm_` for VAE or world model.

**Impact**
- Loss magnitude scales with batch size × feature dim, making telemetry misleading and potentially causing gradient explosion.
- Combined with missing feature normalization, this can produce catastrophic values.

**Fix direction**
- Use `mean` reduction or normalize sums by batch size (and optionally feature dim).
- Add gradient clipping for VAE + world model optimizers.
- Add numeric checks (NaN/Inf) at training-step boundaries.

---

### CI-5: Worker error paths can emit wrong-shaped arrays (latent dim mismatch)

**Evidence**
- `apps/reference/domains/neocortex/logic/brain/worker.py:111` returns `np.zeros(1, dtype=np.float32)` on encode failure.

**Impact**
- Downstream code expects `latent_dim` vectors; returning shape `(1,)` can cause new shape-mismatch crashes far from root cause.

**Fix direction**
- Return `np.zeros(config.vae.latent_dim)` or propagate errors explicitly.
- Add a test that forces `_brain_encode_task()` failure and asserts output shape.

---

### CI-6: Production code contains `print()` and “debug prints” in core execution paths

**Evidence (examples)**
- `apps/reference/domains/neocortex/logic/brain/core.py:327` / `apps/reference/domains/neocortex/logic/brain/core.py:526`
- `apps/reference/domains/neocortex/logic/brain/worker.py:268`
- `apps/reference/domains/neocortex/main.py:205`

**Impact**
- Breaks structured logging pipelines; increases noise; makes debugging nondeterministic under multiprocessing.

**Fix direction**
- Replace `print()` with logger calls.
- Ensure worker process logging is configured to emit to the same sink as the parent (or a dedicated worker log).

---

## 3) ML Best Practices Gaps (Should Fix)

### BP-1: No KL annealing / scheduling for VAE
- VAE uses constant `beta` (`apps/reference/domains/neocortex/logic/brain/vae.py:129`).
- Add a schedule (warm-up steps) or cyclical annealing; log the effective beta.

### BP-2: Reward modeling is weak and likely wrong for multi-asset trading
- `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:403` uses equity delta as PnL proxy; it is not symbol-isolated.
- If equity updates are sparse/missing, reward collapses toward zero.

### BP-3: PPO rollout length is mismatched to “trade-close episodes”
- Default `rollout_length: 2048` (`apps/reference/domains/neocortex/config/neuro.yaml:49`) is too large if episodes only occur on trade close.
- Consider a smaller rollout length, or define trajectories at bar/tick granularity rather than at close-only.

### BP-4: Reproducibility is partial
- PPO library seeds itself, but Neocortex training paths are not consistently seeded (torch, numpy, python random).

---

## 4) Refactoring Plan (Action Items)

### R0-A: Make training deterministic and safe
- Add unified seeding (python/numpy/torch) and record it in telemetry.
- Add gradient clipping for VAE + world model, plus NaN/Inf guards.

### R0-B: Fix PPO integration end-to-end
- Decide “episode” semantics (single-step vs multi-step).
- Ensure `TrajectoryBuffer.finalize()` is executed correctly (with correct `last_values`).
- Add an integration test that reaches a real PPO update without mocks.

### R0-C: Fix world model sequence handling
- Reshape training to feed `(B, Seq, F)` with `Seq > 1`.
- Add unit tests to lock the expected tensor shapes.

### R0-D: Implement normalization (or explicitly document external normalization contract)
- If FeatureEngineering guarantees normalized output, encode that as an interface contract and assert it.
- Otherwise, implement online normalization in Neocortex ingestion.

### R0-E: Clean up observability
- Replace f-string logging with lazy formatting (`logger.info("x=%s", x)`), especially in hot loops.
  - Current f-string logging occurrences in `.py`: **116**.
- Remove/replace `print()` in runtime code.
  - Current `print()` occurrences in `.py`: **16**.

### R0-F: Make tests real
- Add `apps/reference/domains/neocortex/tests` to `pytest.ini:testpaths` or create a dedicated CI job.
- Ensure tests run under the same interpreter/env that has torch available (e.g. `.venv/bin/python`).
- Add missing tests:
  - PPO finalize/update path (real crash reproduction)
  - MultiTailer log rotation/truncation offsets
  - Feature-dimension contract (feature_list ↔ vae.input_dim) to prevent regression

---

## Appendix A — Simulated Linter Findings (Selected)

### Logging anti-pattern: f-strings in logger calls
- Example: `apps/reference/domains/neocortex/logic/brain/vae.py:76`
- Example: `apps/reference/domains/neocortex/logic/brain/bridge.py:92`
- Recommendation: replace with `%s` formatting or `extra={...}`.

### Assert in production runtime
- `apps/reference/domains/neocortex/PPO/ppo_library_v2/ppo_system/learning/buffer.py:77` uses `assert` for runtime validation.
- Recommendation: raise `ValueError`/`RuntimeError` explicitly (asserts can be stripped with `-O`).

### Type-hint debt hotspots
- Total `Any` occurrences in `.py`: **65**
- Total `Dict[str, Any]` occurrences in `.py`: **28**
- Recommendation: introduce `TypedDict` / Pydantic event models for:
  - Feature payloads
  - Order events
  - Core events
  - Episode dict schema passed into dream/PPO

### No naked `except:`
- Bare `except:` occurrences: **0** (good)

---

## Appendix B — Notes for Bars Migration

- Neocortex currently assumes a “feature vector per event” pipeline and treats the buffer batch as temporal sequence, but the world model implementation does not actually see `Seq>1` (CI-2).
- Bar aggregation changes feature distributions dramatically; normalization and explicit schema contracts become mandatory.

