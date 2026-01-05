# FEATURE INTEGRITY FULL AUDIT 005 (P0 + R1/R2)

**Task ID:** FEATURE-INTEGRITY-FULL-AUDIT-005  
**Date:** 2026-01-05  
**Scope:** Independent runtime audit (P0 + R1 + R2)  
**Result:** **DONE** (P0+R1+R2 PASS; replay sanity G deferred non-blocker; 0 blocker FAIL)

---

## Executive Summary (DONE / NOT DONE)

**DONE ✅**

1) **P0 (Spread Health + Sanity Firewall)** реально інтегрований у **live/runtime path**: перед `EVT:FEATURES_CALCULATED` формується `warmup`, застосовується `sanitize_features_dict()`, робиться `check_book_health()` і в разі проблем виставляється `ready=False` + reason.  
2) **R1 (macro_resid)** реально впливає на **scoring → intents → runtime** (через `signal_weights` + `directional_features` + v2 scoring kernel).  
3) **R2 (absorption)** реалізований як експеримент **default OFF** і **не блокує live readiness**, має dedup guard проти TFI і readiness/reasons.  
4) Тести для таску **синтетичні**, deterministic (без network / зовнішніх даних), перевіряють BUY/SELL reachability і sign/neutral semantics для R1/R2/P0.  
5) Critical path працює **fail-closed**: missing/not_ready не потрапляє в scoring; конфіг валідований через Pydantic, `extra='forbid'`, + SSOT контракт на старті.
6) Replay/backtest sanity (**G**) позначено як **DEFERRED** до першого пост-апдейт запуску (контрольний пункт, не блокер).

---

## PASS/FAIL Table (A–G)

| Section | Check | Status | Evidence |
|---|---|---:|---|
| A | A1 P0-2 Spread Health Gate у live path | **PASS** | `apps/reference/domains/feature_engineering/feature_engineering.py:789`, `reports/artifacts/feature_integrity_full_audit_005/sample_runtime_logs.txt` |
| A | A2 P0-3 Sanity Firewall у live path | **PASS** | `apps/reference/domains/feature_engineering/feature_engineering.py:764`, `reports/artifacts/feature_integrity_full_audit_005/sample_runtime_logs.txt` |
| B | B1 No silent fallbacks (critical scan) | **PASS** | `reports/artifacts/feature_integrity_full_audit_005/rg_outputs.txt`, decision guard `apps/reference/domains/decision_making/decision_making.py:2506` |
| C | C1 YAML → Pydantic (strict) → runtime usage | **PASS** | `reports/artifacts/feature_integrity_full_audit_005/config_validate.txt`, `apps/reference/config_loader.py:1148`, `apps/reference/config_models.py:1822` |
| D | D1 macro_resid math correctness | **PASS** | `apps/reference/domains/feature_engineering/calculation_engine.py:304` |
| D | D2 macro_resid wired into scoring | **PASS** | `apps/reference/domains/decision_making/decision_making.py:2568`, `config/aurora/strategies/aurora.yaml:84` |
| E | E1 absorption default OFF (0 live impact) | **PASS** | `config/aurora/domains.yaml:265`, `apps/reference/domains/feature_engineering/feature_engineering.py:590` |
| E | E2 Proxy≠TFI + dedup guard | **PASS** | `apps/reference/domains/feature_engineering/calculation_engine.py:459`, tests `tests/unit/feature_integrity/test_r1r2_features.py:169` |
| F | F1/F2 Synthetic tests + BUY/SELL reachable | **PASS** | `tests/unit/feature_integrity/test_p0_fixes.py:190`, `tests/unit/feature_integrity/test_r1r2_features.py:291`, `reports/artifacts/feature_integrity_full_audit_005/pytest_full.txt` |
| G | Replay/backtest sanity | **DEFERRED (non-blocker)** | `reports/artifacts/feature_integrity_full_audit_005/replay_summary.json` |

---

## Evidence (Commands + Outputs)

### 1) `rg` scans (silent fallbacks / heuristics)

- Artifacts: `reports/artifacts/feature_integrity_full_audit_005/rg_outputs.txt`
- Висновок: **не знайдено** decision-impacting `.get(key, literal)` які б дозволяли trading/score без явного fail-closed; є defensive/telemetry `.get(..., 0)` для payload/state (перелік у artifacts).
- Важливий guard (fail-closed, no silent default): `apps/reference/domains/decision_making/decision_making.py:2506` (missing `liquidity_kappa` → DEFER + NRR).

### 2) Config validation

- Command + output: `reports/artifacts/feature_integrity_full_audit_005/config_validate.txt`
- SSOT contract: `apps/reference/config_loader.py:1148` (essential ⊆ declared ready keys).

### 3) Tests (тільки по таску)

- Output: `reports/artifacts/feature_integrity_full_audit_005/pytest_full.txt`
- Covered:
  - P0: readiness contract, spread health gate, sanity firewall, BUY/SELL reachability
  - R1: macro_resid math + integration into v2 score
  - R2: default OFF + dedup guard

### 4) Synthetic “runtime-like” payload logs

- Output: `reports/artifacts/feature_integrity_full_audit_005/sample_runtime_logs.txt`
- Демонструє:
  - Sanity firewall: NaN/Inf/out-of-range → `ready=false` + reasons
  - Book health: stale/no updates → unhealthy reason
  - R2 default OFF semantics: `absorption.mode=disabled` не блокує `warmup.full_ready`

### 5) Multi-strategy proof (Aurora + MeanReversion + arbitration)

- Artifact: `reports/artifacts/feature_integrity_full_audit_005/multi_strategy_proof.txt`
- Висновок: **warmup gate застосовується до всіх стратегій**, а не лише до Aurora:
  - MeanReversion генерує `EVT:STRATEGY_SIGNAL_PRODUCED` і проходить через `DecisionMaking._on_strategy_signal_gateway()` (universal gates) → `apps/reference/domains/decision_making/decision_making.py:302`.
  - У gateway є `GATE 6: WARMUP / READINESS` і він викликає `_warmup_gate_before_trade_intent(...)` → `apps/reference/domains/decision_making/decision_making.py:768`.
  - MR handler активується лише через SSOT assignments + typed Pydantic config → `apps/reference/domains/decision_making/mean_reversion_handler.py:166`.

---

## Detailed Findings (A–F)

### A1) P0-2 Spread Health Gate — live path proof

- Before emit: `apps/reference/domains/feature_engineering/feature_engineering.py:789` (`update_book_health()` + `check_book_health()`).
- If unhealthy: `spread_bps` forced `ready=False` + `warmup.reasons += "spread_bps:<reason>"` before `EVT:FEATURES_CALCULATED` (`apps/reference/domains/feature_engineering/feature_engineering.py:802`).

### A2) P0-3 Sanity Firewall — live path proof

- Applied to **all features** pre-emit: `apps/reference/domains/feature_engineering/feature_engineering.py:764` (`sanitize_features_dict(features)`).
- Readiness merged into warmup + `full_ready` recomputed fail-closed: `apps/reference/domains/feature_engineering/feature_engineering.py:784`.
- Scoring excludes not-ready: readiness lookup is fail-closed (`apps/reference/domains/decision_making/signal_score_v2.py:128`).

### B1) No silent fallbacks (critical path)

- Primary evidence: `reports/artifacts/feature_integrity_full_audit_005/rg_outputs.txt`.
- Decision-making hard guard example: missing `liquidity_kappa` does **not** default → explicit DEFER + NRR (`apps/reference/domains/decision_making/decision_making.py:2506`).

### C1) Config discipline (YAML → Pydantic → runtime)

- Strict Pydantic: `apps/reference/config_models.py:1822` (`extra='forbid'` for per-instrument weights; canonical keys include `macro_resid`).
- Startup SSOT validation: `apps/reference/config_loader.py:1148`.
- Config validate is green: `reports/artifacts/feature_integrity_full_audit_005/config_validate.txt`.

### D1) R1 macro_resid math correctness

- Implementation: `apps/reference/domains/feature_engineering/calculation_engine.py:304`
  - `resid = r_asset - beta * r_btc` (signed)
  - `beta = cov/var` + `var_floor`
  - robust scaling via MAD + `scale_floor`
  - clip bound applied (`clip`)

### D2) R1 wired into scoring → intents

- Feature emitted + readiness tracked: `apps/reference/domains/feature_engineering/feature_engineering.py:565`.
- Scoring consumes weights and `directional_features`: `apps/reference/domains/decision_making/decision_making.py:2568`.
- Config proof (directional_features + neutrals + weights): `config/aurora/strategies/aurora.yaml:84`.
- Per-asset proof (all Aurora assets have `macro_resid` in weights): `reports/artifacts/feature_integrity_full_audit_005/multi_strategy_proof.txt`.

### Multi-strategy proof (globality across strategies/symbols)

**SSOT assignments**
- Strategy assignments are SSOT in `config/aurora/strategies.yaml:1` (includes `aurora`, `mean_reversion`, and hybrid `BTCUSDT`).

**Aurora (tick-based scoring kernel)**
- Aurora v2 scoring uses `direction_strength_scoring.directional_features` + `signal_weights` + `feature_neutrals` from `config/aurora/strategies/aurora.yaml:84`.
- Therefore **macro_resid affects Aurora** decisions only when present in both:
  - `signal_weights.macro_resid` (weights)
  - `direction_strength_scoring.directional_features` (kernel include list)

**MeanReversion (bar-based strategy)**
- MeanReversion has its own profile SSOT `config/aurora/strategies/mean_reversion.yaml:1` and does **not** use `SignalScoreV2` weights kernel.
- It emits `EVT:STRATEGY_SIGNAL_PRODUCED` and **DecisionMaking applies the same universal gates** (risk/QoS/exposure/TTL + warmup) before emitting `EVT:TRADE_INTENT_PROPOSED`:
  - Gateway: `apps/reference/domains/decision_making/decision_making.py:302`
  - Warmup gate applied: `apps/reference/domains/decision_making/decision_making.py:768`

### E1/E2) R2 absorption experimental default OFF + dedup

- Default OFF in YAML: `config/aurora/domains.yaml:265`.
- Runtime computes only if enabled; otherwise `ready=false` (and excluded from scoring): `apps/reference/domains/feature_engineering/feature_engineering.py:590`.
- Dedup guard vs TFI: `apps/reference/domains/feature_engineering/calculation_engine.py:508`.

### F) Synthetic tests (no external dependencies) + BUY/SELL reachability

- BUY/SELL reachability: `tests/unit/feature_integrity/test_p0_fixes.py:190`, `tests/unit/feature_integrity/test_r1r2_features.py:291`.
- No network/external datasets used in these tests (MagicMock + deterministic data).

---

## Risks / Tech Debt (P0/P1/P2)

- **P0 (fixed):** R2 absorption default OFF was blocking `warmup.full_ready` (would freeze trading) → fixed by config-aware `full_ready`.
- **P0 (fixed):** `macro_resid` was present in weights but missing from `directional_features` (no scoring impact) → fixed in `config/aurora/strategies/aurora.yaml:84`.
- **P1:** Critical-path codebase still contains many defensive `.get(..., <literal>)` uses (mostly payload/state); evidence in `reports/artifacts/feature_integrity_full_audit_005/rg_outputs.txt`. Recommend follow-up hardening sweep with explicit “telemetry-only” markers + strict contracts where feasible.

---

## Code Changes (Audit+Fix, minimal)

**Why:** Found BLOCKER mismatches vs requirements (R2 default OFF must be zero-impact; R1 must affect scoring; YAML must be strict).

- `apps/reference/domains/feature_engineering/types.py`: add `compute_warmup_full_ready()` to make `full_ready` config-aware (absorption disabled не блокує readiness).
- `apps/reference/domains/feature_engineering/feature_engineering.py`: recompute `full_ready` через `compute_warmup_full_ready()` after sanity + after book health.
- `config/aurora/strategies/aurora.yaml`: add `macro_resid` to `directional_features` + add neutral `macro_resid: 0.0`.
- `config/aurora/domains.yaml`: remove duplicate YAML key (`volatility_state`) to satisfy strict loader.
- Tests updated only to reflect above contracts:  
  `tests/unit/feature_integrity/test_p0_fixes.py`, `tests/unit/feature_integrity/test_r1r2_features.py`, `tests/config/test_task54_weight_key_validation.py`, `tests/config/test_toplevel_forbid_enforcement.py`.

### Change Log (what changed → why it was required)

| File | Change | Justification (requirement / defect) | Live impact |
|---|---|---|---|
| `apps/reference/domains/feature_engineering/types.py` | Added `compute_warmup_full_ready()` and made `full_ready` **exclude** `absorption` when `mode=disabled` | **E1 Default OFF** must mean *zero influence on live*; previously `absorption` (disabled) forced `full_ready=false` → trading freeze (BLOCKER) | Removes unintended global block; does not enable absorption |
| `apps/reference/domains/feature_engineering/feature_engineering.py` | Recompute `warmup.full_ready` via `compute_warmup_full_ready()` after sanity + book health | Ensures **A1/A2** gates affect readiness consistently and **E1** doesn’t block live | Only affects readiness semantics; fail-closed preserved |
| `config/aurora/strategies/aurora.yaml` | Added `macro_resid` to `directional_features`; added neutral `macro_resid: 0.0` | **D2** required: macro_resid must affect scoring; weights existed but if not in `directional_features` it had **no scoring impact** (BLOCKER) | Makes macro_resid contribute to score as intended by R1 |
| `config/aurora/domains.yaml` | Removed duplicate key `volatility_state` | Strict YAML loader rejects duplicates → config validation/test failure | No semantic change; unblocks strict validation |
| `tests/unit/feature_integrity/test_p0_fixes.py` | Added test that absorption disabled **does not block** `full_ready` | Regression guard for **E1** | No runtime impact |
| `tests/unit/feature_integrity/test_r1r2_features.py` | Strengthened integration tests to use real v2 scoring wrapper + config | Regression guard for **D2** (wiring into scoring) | No runtime impact |
| `tests/config/test_task54_weight_key_validation.py` | Updated expected canonical keys to include `macro_resid` | Align test with `CANONICAL_WEIGHT_KEYS` including R1 | No runtime impact |
| `tests/config/test_toplevel_forbid_enforcement.py` | Updated minimal DecisionConfig fixture to include `macro_resid` | Pydantic now requires `macro_resid` field; keep strict forbid tests valid | No runtime impact |
| `tools/feature_integrity_replay_check.py` | Added post-run replay sanity checker (WAL intents + macro_resid distribution from features logs) | Addresses **G** as a persistent “run after deploy” control (non-blocker, but closes future surprises) | No runtime impact (tooling only) |

### Tests executed (task-only)

- Command: `PYTHONPATH=. python3 -m pytest -q tests/config/test_config_forensics.py tests/config/test_task54_weight_key_validation.py tests/config/test_toplevel_forbid_enforcement.py tests/unit/feature_integrity/test_p0_fixes.py tests/unit/feature_integrity/test_r1r2_features.py`
- Output: `reports/artifacts/feature_integrity_full_audit_005/pytest_full.txt`

---

## G) Replay/backtest sanity (post-update)

**Status: DEFERRED (non-blocker)** — система ще не запускалась після апдейту, тому runtime/WAL/log artifacts після змін ще не існують (старі логи ігноруємо).

**Що додано для “закрити питання назавжди”**
- Мінімальний чекер: `tools/feature_integrity_replay_check.py:1`
- Очікуваний артефакт після першого запуску: `reports/artifacts/feature_integrity_full_audit_005/replay_summary.json`

**Команда для 1–3 днів даних (після запуску)**
- `python3 tools/feature_integrity_replay_check.py --wal ops/wal/2026-01-*.jsonl --features logs/features/*.log --out reports/artifacts/feature_integrity_full_audit_005/replay_summary.json`
