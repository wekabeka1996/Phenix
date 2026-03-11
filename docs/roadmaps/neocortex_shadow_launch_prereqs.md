# Neocortex Shadow Launch Prerequisites

**Package:** NEO-INTEGRATION-DATA-CONTRACT-AUDIT
**Date:** 2026-03-11

---

## Minimum Data/Event Contract for Neocortex Launch

### What neocortex REQUIRES from Aurora for each mode

| Contract Item | Offline Replay | Shadow Runtime | Acceptance Campaign |
|---|---|---|---|
| `EVT:FEATURES_CALCULATED` | ✅ From logs | ✅ Live bus | ✅ Live bus |
| `event_ts_ms` (canonical time) | ✅ In feature logs | ✅ In events | ✅ |
| `EVT:TRADE_INTENT_PROPOSED` | ✅ From WAL | ✅ Live bus | ✅ |
| `EVT:REGIME_DETECTED` | ✅ From logs | ✅ Live bus | ✅ |
| `lifecycle_id` | ❌ Not needed for repr/regime | ⚠️ REQUIRED | ✅ REQUIRED |
| `EVT:POSITION_CLOSED` (structured) | ❌ Not needed for repr/regime | ⚠️ REQUIRED | ✅ REQUIRED |
| `EpisodeReward` (structured) | ❌ Not needed for repr/regime | ⚠️ REQUIRED | ✅ REQUIRED |
| `reward_complete=true` validation | ❌ N/A | ⚠️ REQUIRED | ✅ REQUIRED |
| Stable Aurora execution contract | ❌ Not needed | ⚠️ REQUIRED | ✅ REQUIRED + frozen |

---

## Phased Launch Readiness

### Phase 1: Offline Replay Only ✅ READY NOW

**What can run:**
- Representation embedding training from feature log replay
- Regime oracle self-supervised training (no execution dependency)
- VAE latent space exploration and quality metrics
- Shadow intent generation for building comparison corpus
- Dataset provenance / hygiene validation

**What cannot run:**
- Execution-quality episode training (no reward truth)
- Calibration reports with `reward_complete=true`
- Full disagreement analysis (decisions available, outcomes not)

**Launch config:**
```yaml
system:
  run_mode: backtest
neuro:
  performance:
    operating_mode: offline_replay
    shadow_intent_emit_policy: decimate_observational
  ppo:
    policy_training_mode: disabled
    objective_split_enforced: true
  shadow_gates:
    startup_enforcement: strict
    allow_advisory_influence: false
    allow_live_authority: false
    allow_policy_training_reenable: false
```

**Risk:** NONE — fully self-contained, no execution dependency.

---

### Phase 2: Offline + Shadow Analysis ⚠️ BLOCKED

**Prerequisites (must be completed in Aurora):**

1. **Structured `EVT:POSITION_CLOSED`** emitted with:
   - `trade_id` (from fill data)
   - `close_ts_ms` (canonical epoch_ms)
   - `realized_pnl_net` (authoritative, not cached)
   - `fees` (accumulated from fill commissions)
   - `symbol`, `side`, `entry_price`, `close_price`, `quantity`

2. **Lifecycle identity binding:**
   - Either introduce `lifecycle_id` in Aurora's execution path
   - Or document deterministic mapping: `rid → lifecycle_id`
   - Neocortex adapter can then bind episodes to lifecycle identities

3. **EpisodeReward construction:**
   - Option A: Aurora emits structured reward event
   - Option B: Bridge adapter in neocortex translates close event → EpisodeReward
   - Either way, `reward_complete=true` must be achievable

4. **Event timestamp causal ordering for execution events**

**Estimated work:** 3-5 coding tasks in Aurora execution_position domain.

---

### Phase 3: Full Shadow Acceptance Campaign ⚠️ BLOCKED

**All Phase 2 prerequisites plus:**

1. Aurora execution contract fully stable (no in-flight refactoring)
2. At least 100 episodes with `reward_complete=true` verified
3. ShadowOfflineEvaluator producing valid:
   - CalibrationReport
   - DisagreementReport
   - AdvisoryReadinessPrereqReport (will remain `not_ready` per P9)
4. All SSOT configs frozen for evaluation window duration
5. Shadow gate evaluator passing all gates in `strict` mode

**Estimated timeline:** After Phase 2 + 1-2 weeks of data collection.

---

## What Remains Forbidden

| Item | Status | Reason |
|---|---|---|
| Advisory influence | FORBIDDEN | P9 hard gate |
| Policy training re-enable | FORBIDDEN | No clean PolicySample producer |
| Live trading authority | FORBIDDEN | P9 hard gate |
| Live acceptance campaign | FORBIDDEN | Execution contract unstable |
| Testnet acceptance campaign | FORBIDDEN | Execution contract unstable |
| Broad neocortex refactor | FORBIDDEN | Audit-only package |
| Broad Aurora execution refactor (from this package) | FORBIDDEN | Audit-only package |
