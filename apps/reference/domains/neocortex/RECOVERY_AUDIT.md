# Neocortex Recovery Audit (Post-Rollback Snapshot)

**Scope:** `apps/reference/domains/neocortex/`  
**Goal:** Confirm whether critical ML stability fixes and safety guards are present after rollback, and identify what must be re-applied.  
**Method:** Static inspection + targeted greps. No fixes applied in this document.

## Executive Summary

**Verdict:** **R0-Alpha (partially stabilized, still high-risk)**  
Core stability work appears present (VAE loss scaling, grad clipping, PPO finalize, normalizer wiring, worker fallback shapes). However, there are still structural risks (world model “compat unsqueeze”, config mismatch vs implementation, blocking file I/O in async tailers, and many broad exception handlers).

**Working tree note:** `git status` shows a **dirty** tree on `stable_11_11` with multiple modified files, so the “effective version” is not a clean commit baseline.

---

## 1) The Lost Fixes (Regression Checklist)

| Fix / Regression | Evidence | Status | Notes |
|---|---|---:|---|
| **VAE Loss bounded** (no `reduction='sum'`) | `apps/reference/domains/neocortex/logic/brain/vae.py:145` uses `reduction="mean"` | PASS | Loss is now scale-invariant to batch size. |
| **World Model sequence learning** (no forced `Seq=1`) | `apps/reference/domains/neocortex/logic/brain/world_model.py:81` still has `z = z.unsqueeze(1)` | FAIL (strict) | Unsqueeze is present as “compat” for 2D inputs. Mitigation exists: `BrainCore.train_batch` feeds 3D sequences (see below), but any other 2D caller will still run `Seq=1`. |
| **BrainCore trains WorldModel on sequences** | `apps/reference/domains/neocortex/logic/brain/core.py:203` builds `z_seq = z.unsqueeze(0)` and trains on `[:, :-1, :]` | PASS | This fixes CI-3 for the BrainCore training path specifically. |
| **Gradient clipping for VAE/WM** | `apps/reference/domains/neocortex/logic/brain/core.py:185` and `apps/reference/domains/neocortex/logic/brain/core.py:213` | PASS | Uses `clip_grad_norm_(..., max_norm=1.0)`. |
| **PPO finalize before update** | `apps/reference/domains/neocortex/logic/brain/core.py:375` calls `self.ppo_agent.buffer.finalize(...)` | PASS | PPO update path is structurally viable. |
| **Online normalization exists** | `apps/reference/domains/neocortex/logic/ingest/normalizer.py` | PASS | Has persistence and locking. |
| **Online normalization wired into adapter** | `apps/reference/domains/neocortex/transport/adapter.py:64` init + `apps/reference/domains/neocortex/transport/adapter.py:103` update/normalize | PASS | Normalizes `MarketObservation.features_vector` prior to importance/BrainBridge. |
| **Worker encode fallback returns correct shape** | `apps/reference/domains/neocortex/logic/brain/worker.py:131` returns `(latent_dim,)` or `(B, latent_dim)` | PASS | Prevents downstream shape crashes on encode exceptions. |
| **Reward derived from PnL** (not hardcoded 0) | `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:411` → `raw_pnl` → `tanh(raw_pnl / 10.0)` | PASS (with caveat) | Reward is equity-delta proxy; not symbol-isolated. |

---

## 2) Component Status Table

| Component | Status | Critical Issues Identified |
|-----------|--------|----------------------------|
| Ingestion | PARTIAL | MultiTailer uses synchronous `open()` inside async loop (`apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:239` etc); feature/order rotation handling still uneven (core has truncation guard, others may not). |
| Brain (ML) | PARTIAL | VAE loss + clipping appear fixed; WorldModel forward still accepts 2D and converts to `Seq=1` (`apps/reference/domains/neocortex/logic/brain/world_model.py:81`), so behavior depends on caller shape discipline. |
| PPO (RL) | PARTIAL | `buffer.finalize()` exists (`apps/reference/domains/neocortex/logic/brain/core.py:375`), but rollout semantics are still “trade-close episodes as steps” and default rollout length is large (see config). |
| Config | RISKY | `ppo.state_dim` is **20** while runtime PPO observes **latent_dim only** (16) (`apps/reference/domains/neocortex/logic/brain/core.py:140`); mismatch risk and misleading config. |

---

## 3) General Code Quality & Safety Audit (Findings)

### 3.1 Hardcoded constants (magic numbers)

High-impact examples (non-exhaustive):
- `seed=42` hardcoded for PPO (`apps/reference/domains/neocortex/logic/brain/core.py:134`).
- Reward scaling `tanh(raw_pnl / 10.0)` (`apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:416`).
- Amygdala epsilon `1e-5` and trace buffer `maxlen=100` (`apps/reference/domains/neocortex/logic/amygdala/valuation.py:57`).
- Normalizer epsilon hardcoded `1e-8` in adapter construction (`apps/reference/domains/neocortex/transport/adapter.py:66`).

Risk: tuning and behavior changes require code changes; debug constants can leak into production.

### 3.2 Fallbacks & error hiding

- Broad `except Exception as e` appears frequently in logic/transport (≈42 occurrences in these folders). Many log `exc_info=True`, but some helper/fallback blocks catch exceptions without logging (e.g. `apps/reference/domains/neocortex/logic/brain/worker.py:136` inner fallback).
- f-string logging is still common in runtime code (≈91 occurrences in logic/transport), which is both noisy and inefficient.

Risk: silent degradation paths, plus log volume overhead.

### 3.3 Blocking I/O in async code paths

- `MultiTailer` performs synchronous file reads (`with open(...):`) inside async methods (`apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:239`, `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:292`, `apps/reference/domains/neocortex/logic/ingest/multi_tailer.py:371`).
- `WalTailer` similarly uses sync `open()` in async tailing (`apps/reference/domains/neocortex/logic/ingest/tailer.py:198`, `apps/reference/domains/neocortex/logic/ingest/tailer.py:244`).
- `wal_replayer.py` uses `aiofiles.open` for one path but still has a sync `open()` path (`apps/reference/domains/neocortex/logic/ingest/wal_replayer.py:144`).

Risk: event loop stalls under heavy log volume or slow disks.

### 3.4 Concurrency safety (shared mutable state)

- `NeocortexAdapter` stores mutable episode buffer `_completed_episodes` and uses `asyncio.create_task` for background runs (`apps/reference/domains/neocortex/transport/adapter.py:228`), guarded by `_dream_in_progress`. This is likely safe under a single-threaded event loop, but it is not lock-protected and relies on careful await boundaries.
- `WelfordNormalizer` has an internal `threading.Lock` and is safe for concurrent callers, but it is invoked inside the async loop (lock contention should be minimal).

Risk: subtle interleavings if new awaits are added later or if handlers are called from multiple tasks concurrently.

---

## 4) Config Integrity Check

### PPO `state_dim` vs VAE `latent_dim`

- Config: `vae.latent_dim: 16`, `ppo.state_dim: 20` (`apps/reference/domains/neocortex/config/neuro.yaml:10`, `apps/reference/domains/neocortex/config/neuro.yaml:38`).
- Runtime PPO observation space: `(vae.latent_dim,)`, not `ppo.state_dim` (`apps/reference/domains/neocortex/logic/brain/core.py:140`).
- Model validation only enforces `ppo.state_dim >= vae.latent_dim` (not equality) (`apps/reference/domains/neocortex/config_models.py:328`).

**Status:** **Mismatch risk present** (config implies extra context that is not actually provided).

---

## 5) Recommended Re-Apply List (If Missing on Your Server)

If any of these are absent on the actual deployed host, re-apply immediately:
1. VAE loss mean scaling (no sum reduction).
2. Grad clipping in VAE + world model.
3. World model training on real sequences (3D tensors) in `BrainCore.train_batch`.
4. PPO `buffer.finalize()` call before `update()`.
5. `WelfordNormalizer` persistence + adapter wiring.
6. Worker encode fallback returning correct latent shape.

