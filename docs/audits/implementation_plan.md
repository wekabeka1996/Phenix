# Strategy Scoring Architecture — Audit + Target Design

## Summary

**Key finding:** The feared cross-strategy scoring coupling does not exist in code.
MR and md_amr already have fully isolated scoring implementations.
The remaining work is Aurora-specific cleanup plus one config import tightening.

---

## Current Scoring Map (per strategy)

| Strategy | Scorer Module | Coupling to Aurora Scoring? |
|---|---|---|
| **Aurora** | [quadratic_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py) (Phase 9 live) | n/a — this IS Aurora |
| **mean_reversion** | `mean_reversion_strategy.py` (BB + RSI + ATR) | **NONE** — zero Aurora scoring imports |
| **md_amr** | `md_amr_strategy.py` (OHLC channel + dir_score) | **NONE** — zero Aurora scoring imports |

### Aurora scoring module dependency tree

```
QuadraticScoringKernel          ← LIVE (Phase 9)
  └─ ShieldCascade (DZ/Context/Memory)

AuroraScoringKernel (v2)        ← DEPRECATED scaffold
  └─ scoring_direction_strength_v1
       └─ signal_score_v2
  └─ SignalWeights / FeatureNeutrals / DirectionStrengthScoringConfig
       (in DecisionConfig, aurora.yaml only)
```

**Who touches `scoring_direction_strength_v1`:** only [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py).
**Who touches `signal_score_v2`:** only [scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py).
**MR handler imports:** [MeanReversion1mStrategy](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#556-604), [MRStrategyConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#4360-4403), `MRSignal` — completely own.
**md_amr handler imports:** `MDAMRStrategyV11`, `MDAMRSignal` — completely own.

---

## Critical Problems Found

### ✅ Not a problem: MR/md_amr scoring isolation
Already isolated. No action needed.

### ⚠️ Problem 1: `md_amr_handler.py` imports [AuroraConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#4983-5410)
`from apps.reference.config_models import AuroraConfig, MDAMRStrategyConfig`

This is a **config coupling**, not a scoring coupling. md_amr handler reads its config
through [AuroraConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#4983-5410) as a container. This is an organizational smell, not a scoring
contamination. The md_amr scoring itself is clean.

**Risk:** If [AuroraConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#4983-5410) ever has REQUIRED fields that don't apply to md_amr, this breaks.
**Fix priority:** Low — config refactor is a separate concern.

### ⚠️ Problem 2: Aurora v2 surfaces still alive in code
[scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py) and `signal_score_v2.py` are now dead code for Aurora
(since `scoring_version: "quadratic"` is live). But they exist and create confusion.

**Blocker for removal:** None — confirmed zero MR/md_amr dependency.
**Safe to remove:** Yes, as part of Aurora-only purge (2026-03-27 window).

### ℹ️ Not a problem: `signal_score_v2` "Project-wide scope" claim
The docstring says "Scope: Project-wide (Aurora, MeanReversion if applicable)".
This is a misleading docstring — in practice it is only used by `scoring_direction_strength_v1`.
No MR code actually calls it. The docstring is aspirational, not real.

---

## Per-Strategy Verdict

| Strategy | Has own scorer | Shared legacy dep | Needs new scorer | Needs isolation work |
|---|---|---|---|---|
| **Aurora** | ✅ QuadraticBrain | v2 dead surfaces (safe to remove) | No | No (purge in 2w) |
| **mean_reversion** | ✅ BB/RSI in MR strategy module | None | No | No — already isolated |
| **md_amr** | ✅ OHLC channel/dir_score | AuroraConfig container (config smell) | No | Minor: config import cleanup |

---

## Target Architecture (already mostly achieved)

```
┌──────────────────────────────────────────────────────┐
│                  SHARED INFRASTRUCTURE               │
│  market_data · feature_engineering · regime          │
│  readiness · execution_plumbing · startup_warmup     │
└─────────────────┬────────────────────────────────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
┌──────────┐ ┌──────┐ ┌──────────┐
│  Aurora  │ │  MR  │ │  md_amr  │
│Quadratic │ │  BB  │ │  OHLC    │
│  Brain   │ │ RSI  │ │  dir     │
│ shields  │ │ ATR  │ │  score   │
└──────────┘ └──────┘ └──────────┘
```

**What stays shared:** regime, readiness, feature engineering, warmup, execution plumbing, position sizing, regime allowlist, gap policy, bar identity contracts.

**What is strategy-specific (already isolated):**
- Aurora → QuadraticScoringKernel + ShieldCascade
- MR → MeanReversion1mStrategy (BB bands)
- md_amr → MDAMRStrategyV11 (channel-based scoring)

---

## Proposed Changes

### Package 1 — Aurora-only dead code removal (2026-03-27)
Safe to do now. Zero MR/md_amr impact confirmed.

#### [DELETE] [scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py)
Only consumer was [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py) (deprecated). Zero other callers confirmed.

#### [DELETE] [signal_score_v2.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/signal_score_v2.py)
Only consumer was [scoring_direction_strength_v1.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/scoring_direction_strength_v1.py). Zero other callers confirmed.

#### [DELETE] [aurora_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py)
Deprecated v2 scaffold. Still needed for [ScoringResult](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#43-72) type annotation in [aurora_decision.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_decision.py).
**Pre-condition:** Inline [ScoringResult](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_kernel.py#43-72) into [quadratic_scoring_kernel.py](file:///c:/Users/user/Music/Phenix/tests/test_quadratic_scoring_kernel.py) first.

#### [MODIFY] [aurora.yaml](file:///c:/Users/user/Music/Phenix/config/aurora/strategies/aurora.yaml)
Remove [signal_weights](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py#164-172), [feature_neutrals](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/aurora_scoring_helpers.py#340-348), `direction_strength_scoring` blocks (already annotated DEPRECATED).

#### [MODIFY] [config_models.py](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py)
Remove [SignalWeights](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#183-214), [DirectionStrengthScoringConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#251-277), `DirectionStrengthConfig` models after YAML removal.

### Package 2 — md_amr config import cleanup (low priority, no urgency)
#### [MODIFY] [md_amr_handler.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/decision_making/md_amr_handler.py)
Move [MDAMRStrategyConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#4360-4403) to its own top-level config class, decouple from [AuroraConfig](file:///c:/Users/user/Music/Phenix/apps/reference/config_models.py#4983-5410) container.

---

## Verification Plan

### Automated Tests
```bash
# After Package 1
python -m pytest tests/ -q --ignore=tests/domains/execution_position/test_split_brain_repro.py
# Must: 5213+ pass, 0 new failures
```

### Spot checks
- `grep -r "scoring_direction_strength_v1" apps/` → zero results
- `grep -r "signal_score_v2" apps/` → zero results
- `KERNEL_DIAG: engine=quadratic_v1` still appears in Aurora logs
- MR signals still emit post-purge
- md_amr signals still emit post-purge
