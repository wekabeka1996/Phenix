# J6-S3 — Shadow LIMIT Plan Ladder Telemetry for Entry-Side Judge

## 0. Execution Status — 2026-04-25

### Completed Stages

| Stage | Status | Code Evidence |
|---|---|---|
| Component 1 — Pydantic Config Models | DONE | Added `ConfidenceLadderTier`, `ShadowPlanConfig`, and `VerdictConfig.shadow_plan` in `judge/config_models.py`; added `shadow_plan` ladder block to `config/alpha_search.yaml`. |
| Component 2 — ShadowEntryPlan Contract | DONE | Added strict `ShadowEntryPlan` contract to `judge/contracts.py` with cycle_key population and fail-closed validators for shadow posture and price constraints. |
| Component 3 — Shadow Plan Derivation Module | DONE | Added `judge/shadow_entry_plan.py` with `derive_shadow_entry_plans()` and `write_jsonl_shadow_entry_plan_log()`. |
| Component 4 — Backtest Plugin Integration | DONE | Threaded `current_price` into `_run_chamber_aggregation()` / `_assemble_and_emit_verdict()` and emit `EVT:JUDGE_SHADOW_ENTRY_PLAN_V1` after entry verdict emission. |
| Component 5 — YAML Config Update | DONE | Repo config now ships explicit low / medium / high ladder tiers under `judge.verdict.shadow_plan`. |
| Component 6 — Verb Registry + JSON Schema | DONE | Added `shadow_entry_plan_v1.json` and registered `EVT:JUDGE_SHADOW_ENTRY_PLAN_V1` in `apps/reference/dictionaries/verb_registry_v1.yaml`. |
| Component 7 — Tests | DONE | Added dedicated `tests/domains/alpha_search/judge/test_shadow_entry_plan.py` and extended existing integration tests for runtime emission + JSONL evidence. |

### Validation Evidence

- `pytest tests/domains/alpha_search/judge/test_config.py` → `86 passed`
- `pytest tests/domains/alpha_search/judge/test_shadow_entry_plan.py` → `21 passed`
- `pytest tests/domains/alpha_search/judge/test_expert_provider_integration.py tests/vfoundation/test_dictionaries_parse_all.py` → `38 passed`
- Regression bundle:

```bash
pytest \
    tests/domains/alpha_search/judge/test_config.py \
    tests/domains/alpha_search/judge/test_contracts.py \
    tests/domains/alpha_search/judge/test_serialization.py \
    tests/domains/alpha_search/judge/test_shadow_entry_plan.py \
    tests/domains/alpha_search/judge/test_expert_provider_integration.py \
    tests/vfoundation/test_dictionaries_parse_all.py
```

Result: `217 passed`

### Implementation Note

- Final implementation keeps the contract fail-closed when `price_ref` is missing or invalid: plans are still emitted for visible telemetry, but `actionable=false` and all derived prices remain `null` even if the confidence tier threshold is met. This resolves the validator invariant that actionable plans must carry a valid `entry_price_ref`.

### Remaining Manual Proof

- Not yet executed in this pass: a live/manual run proving real `logs/judge_experts/shadow_entry_plan_{symbol}_{date}.jsonl` files appear under the repo runtime, outside test harnesses.

## 1. Problem Framing

The entry-side Judge chain now produces semantic verdicts (OPEN_LONG/SHORT/NO_ENTRY/SUPPRESS/UNKNOWN) with confidence, reasoning, admissibility, and cycle_key linkage. However, the operator cannot inspect the **practical shadow trade shape** implied by these verdicts — specifically, the hypothetical LIMIT entry price, TP/SL prices, risk/reward, and how the plan varies across confidence tiers.

## 2. Single-Symbol Row Audit — BTCUSDT (2026-04-25)

**Completed.** All 5 log families (expert ×2, chamber, envelope, verdict) populated correctly with coherent `cycle_key` linkage. Fields missing from the current verdict surface:

| Missing field | Status |
|---|---|
| Entry side (BUY/SELL) | Derivable from entry_verdict but not first-class |
| LIMIT reference price | Not present anywhere in Judge logs |
| LIMIT offset | Not present |
| LIMIT price | Not present |
| TP price | Not present |
| SL price | Not present |
| Risk/reward | Not present |
| Confidence tier / ladder | Not present |

## 3. Duplication Check

No `shadow_order_plan`, `shadow_entry_plan`, `shadow_limit_plan` surface exists anywhere in the codebase. ✅ No duplication risk.

## 4. Key Design Corrections from Prior Plan

| Prior plan (rejected) | Revised design |
|---|---|
| `HYPOTHETICAL_MARKET` order type | `HYPOTHETICAL_LIMIT` with LIMIT offset |
| Single `min_plan_confidence` threshold | Explicit confidence ladder (low/medium/high tiers) |
| Logic in `expert_output_bridge.py` | Isolated module `judge/shadow_entry_plan.py` |
| One plan per verdict | One plan per verdict × tier (when `emit_all_tiers=true`) |
| Config in `VerdictConfig` directly | Nested `VerdictConfig.shadow_plan` sub-model |

## 5. Proposed Changes

### Architecture

```
verdict (OPEN_LONG, conf=0.42) + price_ref (94350.0) + shadow_plan_config
    → shadow_entry_plan.py::derive_shadow_entry_plans()
    → List[ShadowEntryPlan] (one per qualifying ladder tier)
    → JSONL log + EVT:JUDGE_SHADOW_ENTRY_PLAN_V1
```

---

### Component 1: Pydantic Config Models

#### [MODIFY] [config_models.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/alpha_search/judge/config_models.py)

Add two new models:

```python
class ConfidenceLadderTier(BaseModel):
    """One tier in the shadow plan confidence ladder."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)          # "low", "medium", "high"
    min_confidence: float = Field(..., ge=0.0, le=1.0)
    limit_offset_bps: int = Field(..., ge=0)      # basis points
    tp_offset_pct: float = Field(..., gt=0.0)     # e.g. 0.015 = 1.5%
    sl_offset_pct: float = Field(..., gt=0.0)     # e.g. 0.008 = 0.8%

class ShadowPlanConfig(BaseModel):
    """Config for shadow LIMIT plan telemetry (J6-S3)."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    order_type: Literal["HYPOTHETICAL_LIMIT"] = "HYPOTHETICAL_LIMIT"
    emit_all_tiers: bool = True
    price_ref_source: Literal["verdict_context"] = "verdict_context"
    confidence_ladder: List[ConfidenceLadderTier] = Field(
        default_factory=list, min_length=0
    )
```

With validators:
- Ladder tiers must be sorted ascending by `min_confidence` (fail-closed if not)
- Tier names must be unique
- `enabled=true` requires non-empty `confidence_ladder`

Extend `VerdictConfig` with one new field:

```python
shadow_plan: Optional[ShadowPlanConfig] = None
```

**Invariant**: `VerdictConfig` already has `extra="forbid"`, so this addition is safely additive.

---

### Component 2: ShadowEntryPlan Contract

#### [MODIFY] [contracts.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/alpha_search/judge/contracts.py)

Append `ShadowEntryPlan` Pydantic model at end of file:

| Field | Type | Source |
|---|---|---|
| `plan_id` | str | `f"sep_{tier}_{symbol}_{ts_ms}"` |
| `cycle_key` | str\|null | From verdict |
| `source_verdict_id` | str | From verdict.verdict_id |
| `source_envelope_id` | str | From verdict.envelope_id |
| `symbol` | str | From verdict |
| `tf_sec` | int | From verdict |
| `ts_ms` | int | From verdict |
| `authority_mode` | CortexMode | Always `"shadow"` |
| `applied` | bool | Always `False` |
| `shadow_only` | bool | Always `True` |
| `final_entry_verdict` | EntryVerdict | From verdict |
| `suppressed` | bool | True when verdict is SUPPRESS/NO_ENTRY/UNKNOWN |
| `suppression_reason` | str\|null | Why plan is suppressed |
| `entry_side` | str\|null | `"BUY"`/`"SELL"`/null |
| `confidence` | float | From verdict |
| `confidence_tier` | str | Tier name from ladder |
| `tier_min_confidence` | float | Threshold for this tier |
| `actionable` | bool | confidence >= tier min |
| `entry_price_ref` | float\|null | Bar close price |
| `limit_offset_bps` | int\|null | From tier config |
| `limit_price` | float\|null | Derived: ref ± offset |
| `tp_price` | float\|null | Derived: limit ± tp_pct |
| `sl_price` | float\|null | Derived: limit ± sl_pct |
| `tp_offset_pct` | float\|null | From tier config |
| `sl_offset_pct` | float\|null | From tier config |
| `risk_reward` | float\|null | tp_pct / sl_pct |
| `entry_order_type` | Literal["HYPOTHETICAL_LIMIT"] | Const |
| `plan_reason_codes` | list[str] | Structured reasons |
| `strategy_id` | str | From verdict |
| `schema_version` | Literal["1"] | "1" |

Validators:
- `authority_mode` must be `"shadow"` (fail if not)
- `applied` must be `False` (fail if not)
- `shadow_only` must be `True` (fail if not)
- When `suppressed=True`, prices must be null
- When `suppressed=False` and `actionable=True`, `entry_price_ref` must be set

---

### Component 3: Shadow Plan Derivation Module

#### [NEW] [shadow_entry_plan.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/alpha_search/judge/shadow_entry_plan.py)

Isolated module with:

```python
def derive_shadow_entry_plans(
    verdict: JudgeVerdict,
    *,
    price_ref: Optional[float],
    shadow_plan_config: ShadowPlanConfig,
) -> List[ShadowEntryPlan]:
    """Derive shadow LIMIT plan(s) from a final entry verdict.

    Returns one ShadowEntryPlan per qualifying ladder tier.
    If emit_all_tiers=True, all tiers are emitted (with actionable flag).
    If emit_all_tiers=False, only tiers where confidence >= min_confidence.
    """
```

LIMIT price derivation logic:
- For BUY (OPEN_LONG): `limit_price = price_ref * (1 - offset_bps / 10_000)` — below market
- For SELL (OPEN_SHORT): `limit_price = price_ref * (1 + offset_bps / 10_000)` — above market
- TP for BUY: `limit_price * (1 + tp_offset_pct)`
- TP for SELL: `limit_price * (1 - tp_offset_pct)`
- SL for BUY: `limit_price * (1 - sl_offset_pct)`
- SL for SELL: `limit_price * (1 + sl_offset_pct)`
- `risk_reward = tp_offset_pct / sl_offset_pct`

Suppression rules:
- `entry_verdict` in `{NO_ENTRY, SUPPRESS, UNKNOWN}` → `suppressed=True`, all prices null
- `price_ref` is None or ≤ 0 → all prices null, reason `"no_valid_price_ref"`
- `actionable = confidence >= tier.min_confidence`

Also includes:

```python
def write_jsonl_shadow_entry_plan_log(
    plan: ShadowEntryPlan,
    log_dir: str,
) -> None:
```

---

### Component 4: Backtest Plugin Integration

#### [MODIFY] [backtest_plugin.py](file:///c:/Users/user/Music/Phenix/apps/reference/domains/alpha_search/backtest_plugin.py)

Two changes:

**4a.** Thread `current_price` through to verdict emission:

In `_run_chamber_aggregation()` signature: add `current_price: float = 0.0` parameter.

In `_on_decision_score()` at the call site (line 721): pass `current_price=current_price`.

In `_assemble_and_emit_verdict()` signature: add `current_price: float = 0.0` parameter.

**4b.** After verdict JSONL log write in `_assemble_and_emit_verdict()`, when `verdict_scope == "ENTRY"`:

```python
# J6-S3: Shadow LIMIT plan telemetry
shadow_plan_cfg = getattr(judge_cfg.verdict, 'shadow_plan', None)
if shadow_plan_cfg and shadow_plan_cfg.enabled:
    plans = derive_shadow_entry_plans(
        verdict, price_ref=current_price, shadow_plan_config=shadow_plan_cfg,
    )
    for plan in plans:
        self.event_bus.emit(
            event_name="EVT:JUDGE_SHADOW_ENTRY_PLAN_V1",
            payload=plan.model_dump(),
            why=f"judge_shadow_plan_{plan.confidence_tier}_{symbol}",
        )
        if judge_cfg.shadow_log and judge_cfg.shadow_log.enabled:
            write_jsonl_shadow_entry_plan_log(plan, log_dir=judge_cfg.shadow_log.log_dir)
```

---

### Component 5: YAML Config Update

#### [MODIFY] [alpha_search.yaml](file:///c:/Users/user/Music/Phenix/config/alpha_search.yaml)

Add `shadow_plan` block under `judge.verdict` (after line 265):

```yaml
    verdict:
      entry_enabled: true
      lifecycle_enabled: false
      strategy_id: "aurora"
      cortex_version: "phase4_shadow_v1"
      split_confidence_discount: 0.5
      shadow_plan:
        enabled: true
        order_type: HYPOTHETICAL_LIMIT
        emit_all_tiers: true
        price_ref_source: verdict_context
        confidence_ladder:
          - name: low
            min_confidence: 0.20
            limit_offset_bps: 0
            tp_offset_pct: 0.010
            sl_offset_pct: 0.006
          - name: medium
            min_confidence: 0.35
            limit_offset_bps: 3
            tp_offset_pct: 0.015
            sl_offset_pct: 0.008
          - name: high
            min_confidence: 0.50
            limit_offset_bps: 5
            tp_offset_pct: 0.020
            sl_offset_pct: 0.010
```

---

### Component 6: Verb Registry + JSON Schema

#### [MODIFY] [verb_registry_v1.yaml](file:///c:/Users/user/Music/Phenix/apps/reference/dictionaries/verb_registry_v1.yaml)

Add entry for the new event:

```yaml
- op: EVT
  verb: JUDGE_SHADOW_ENTRY_PLAN_V1
  owner: alpha_search
  status: experimental
  schema: apps/reference/domains/alpha_search/judge/schemas/shadow_entry_plan_v1.json
  since: '2026-04-25'
  note: "J6-S3 shadow LIMIT plan ladder telemetry — hypothetical order shape, never executed"
```

#### [NEW] [shadow_entry_plan_v1.json](file:///c:/Users/user/Music/Phenix/apps/reference/domains/alpha_search/judge/schemas/shadow_entry_plan_v1.json)

JSON Schema matching `ShadowEntryPlan` Pydantic model. `additionalProperties: false`.

---

### Component 7: Tests

#### [NEW] [test_shadow_entry_plan.py](file:///c:/Users/user/Music/Phenix/tests/domains/alpha_search/judge/test_shadow_entry_plan.py)

**Contract tests** (ShadowEntryPlan model):
1. Valid BUY plan passes validation
2. Valid SELL plan passes validation
3. `shadow_only=False` rejected by validator
4. `applied=True` rejected by validator
5. `authority_mode != "shadow"` rejected
6. Suppressed plan with non-null prices rejected

**Derivation tests** (derive_shadow_entry_plans):
7. OPEN_LONG → BUY side, correct LIMIT/TP/SL for each ladder tier
8. OPEN_SHORT → SELL side, inverted LIMIT/TP/SL for each tier
9. NO_ENTRY → suppressed=true, null prices, all tiers
10. SUPPRESS → suppressed=true with suppression_reason
11. UNKNOWN → suppressed=true
12. emit_all_tiers=false → only qualifying tiers emitted
13. emit_all_tiers=true → all tiers emitted, non-qualifying tagged `actionable=false`
14. price_ref=None → all prices null with reason `"no_valid_price_ref"`
15. price_ref=0 → all prices null
16. Confidence exactly at tier boundary → actionable=true
17. `cycle_key` propagated from verdict
18. `risk_reward` = tp_offset_pct / sl_offset_pct

**Config tests**:
19. Ladder sorted ascending validation
20. Duplicate tier names rejected
21. Enabled with empty ladder rejected
22. Full YAML round-trip via AlphaSearchConfig

**Schema cross-validation**:
23. `ShadowEntryPlan.model_dump()` passes JSON Schema validation
24. Extra field rejected by JSON Schema

**JSONL tests**:
25. Write + read roundtrip

## Files Changed Summary

| File | Action | Component |
|---|---|---|
| `judge/config_models.py` | MODIFY | ConfidenceLadderTier, ShadowPlanConfig, VerdictConfig.shadow_plan |
| `judge/contracts.py` | MODIFY | ShadowEntryPlan model |
| `judge/shadow_entry_plan.py` | NEW | Derivation + JSONL writer |
| `backtest_plugin.py` | MODIFY | Price threading + plan emission |
| `config/alpha_search.yaml` | MODIFY | shadow_plan config block |
| `verb_registry_v1.yaml` | MODIFY | EVT:JUDGE_SHADOW_ENTRY_PLAN_V1 |
| `judge/schemas/shadow_entry_plan_v1.json` | NEW | JSON Schema |
| `tests/.../test_shadow_entry_plan.py` | NEW | 25 test cases |

## Verification Plan

### Automated Tests
```bash
# New tests
pytest tests/domains/alpha_search/judge/test_shadow_entry_plan.py -v

# Regression
pytest tests/domains/alpha_search/judge/test_contracts.py -v
pytest tests/domains/alpha_search/judge/test_serialization.py -v
pytest tests/domains/alpha_search/judge/test_config.py -v
pytest tests/domains/alpha_search/judge/test_expert_provider_integration.py -v
pytest tests/domains/alpha_search/judge/test_schemas.py -v
```

### Manual Verification
- Run system and verify `shadow_entry_plan_BTCUSDT_*.jsonl` files appear in `logs/judge_experts/`
- Inspect row: confirm cycle_key matches verdict, per-tier plans with correct LIMIT offsets, shadow_only=true
