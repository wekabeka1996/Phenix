# AUDIT_R0_FINAL: Neocortex Codebase Deep Audit

**Date:** 2026-01-14  
**Auditor:** Antigravity (Principal Engineer & QA Lead)  
**Scope:** `apps/reference/domains/neocortex/`

---

## Section 1: Code Quality Score

| Category | Score | Notes |
|----------|-------|-------|
| Type Safety | **B** | 20+ `Any` types, but mostly in interface boundaries |
| Error Handling | **A** | No naked `except:` blocks found |
| Logging | **C** | 137 f-string logger calls (bad practice) |
| Code Hygiene | **C** | 20+ `print()` statements in living_latent |
| Config Hygiene | **B-** | 30+ hardcoded values (eps, gamma, max_norm) |
| **Overall** | **B-** | Solid foundation, needs hygiene pass |

---

## Section 2: Critical Issues (Must Fix)

### 2.1 ❌ Hardcoded `max_norm=1.0` in BrainCore
**File:** `logic/brain/core.py:186, 214`
```python
torch.nn.utils.clip_grad_norm_(self.vae.parameters(), max_norm=1.0)  # HARDCODED
```
**Impact:** Cannot tune gradient clipping without code change.  
**Fix:** Add `config.training.max_grad_norm` to config.

---

### 2.2 ❌ Print Statements in Production Code
**Files:** `living_latent/core/*.py`
```
20+ print() statements found
```
**Impact:** Pollutes stdout, no log level control.  
**Fix:** Replace with `logger.info()` or `logger.debug()`.

---

### 2.3 ⚠️ F-String Logging (137 instances)
**Example:**
```python
logger.info(f"Training step {step}: VAE={loss:.4f}")  # BAD
logger.info("Training step %s: VAE=%s", step, loss)   # GOOD
```
**Impact:** Strings evaluated even when log level disabled (perf hit).  
**Fix:** Migrate to `%s` formatting.

---

## Section 3: ML Best Practices Gaps (Should Fix)

### 3.1 ✅ Gradient Zeroing - PASS
```python
self.vae_opt.zero_grad()  # Line 175
self.wm_opt.zero_grad()   # Line 202
```

### 3.2 ✅ Gradient Clipping - PASS (but hardcoded)
```python
torch.nn.utils.clip_grad_norm_(self.vae.parameters(), max_norm=1.0)
```

### 3.3 ✅ Hidden State Detach - PASS
**File:** `PPO/ppo_library_v2/ppo_system/agent.py:173`
```python
self._hidden = (self._hidden[0].detach(), self._hidden[1].detach())
```

### 3.4 ⚠️ No Beta Annealing for VAE
**Current:** `beta=self.config.vae.beta` (static)  
**Recommendation:** Implement cyclical annealing or linear warmup.

### 3.5 ⚠️ Normalization Robustness
**File:** `logic/ingest/normalizer.py`
- Uses Welford's algorithm ✅
- `eps=1e-8` prevents div-by-zero ✅
- **Gap:** No outlier clipping (z > 5 sigma)

---

## Section 4: Test Coverage Analysis

| Component | Test File | Coverage |
|-----------|-----------|----------|
| VAE Loss NaN | `test_brain.py:87` | ✅ |
| Empty Buffer | `test_multi_ingest.py:46` | ✅ |
| Config Validation | `test_config.py` | ✅ |
| PPO Telemetry | `test_ppo_telemetry.py` | ✅ |
| Checkpoint Save | `test_checkpoint_persistence.py` | ✅ |

**Test Files:** 22 total

### Gaps Identified:
1. **No test for NaN input propagation through VAE encode**
2. **No test for extreme outlier normalization**
3. **No integration test for full training loop with real data**

---

## Section 5: Refactoring Plan

### P0 (Critical - This Sprint)
- [ ] Move `max_norm=1.0` to config
- [ ] Replace all `print()` with `logger`

### P1 (High - Next Sprint)
- [ ] Migrate 137 f-string logs to `%s` format
- [ ] Add outlier clipping to normalizer

### P2 (Medium - Backlog)
- [ ] Implement beta annealing for VAE
- [ ] Add integration test for full training loop
- [ ] Document all `Any` type hints with comments

---

## Appendix: Hardcoded Values Found

| Value | File | Line | Purpose |
|-------|------|------|---------|
| `1e-8` | normalizer.py | 32 | Division epsilon |
| `1e-8` | adapter.py | 78 | Normalizer init |
| `0.95` | valuation.py | 16 | Trace decay |
| `1.0` | core.py | 186 | Max grad norm |
| `0.001` | multi_tailer.py | 318 | Async sleep |
| `0.99` | dataclasses.py | 45 | PPO gamma |
| `0.95` | dataclasses.py | 46 | PPO lambda |

---

**Conclusion:** Neocortex codebase is **production-ready with caveats**. Core ML logic is sound. Needs hygiene pass for logging/config.
