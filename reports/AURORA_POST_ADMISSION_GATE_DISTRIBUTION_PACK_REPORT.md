# AURORA_POST_ADMISSION_GATE_DISTRIBUTION_PACK — REPORT

Date: 2026-03-21
Branch: Phenix_v2
Status: bounded live-runtime forensic audit

## 1. Executive Verdict

### FACTS

- The audited post-repair live evidence window is bounded to the repaired runtime currently present in `logs/aurora_core.log` and `logs/order_log_v1.jsonl`.
- The observable repaired window spans 2026-03-21 21:35:00.637 through 2026-03-21 21:50:01.777 for BTCUSDT, ETHUSDT, and SOLUSDT.
- Within that window there are 11 repaired Aurora kernel evaluations for the requested symbols.
- 6/11 evaluations die at admission with `admission_shield_mult=0.000` and `decision_score=0.000000`.
- 5/11 evaluations survive admission with `admission_shield_mult=0.750`.
- Of those 5 admission survivors:
  - 3/5 become side-bearing or score-bearing but never emit `SIGNAL` and never reach gateway.
  - 2/5 emit `SIGNAL`, both on ETHUSDT in `LOW_VOLATILITY`.
  - 2/5 reach `TRADE_INTENT_PROPOSED`.
  - 2/5 are rejected downstream with `NRR-027`.
  - 0/5 reach `ORDER_PLACED`.
- The 3 non-emitting admission survivors are all in regime `UNCERTAIN`.
- BTCUSDT and SOLUSDT `allowed_regimes` exclude `UNCERTAIN`, and the live code has a strict fail-closed regime allowlist gate between kernel output and signal emission.
- Both ETHUSDT emitted signals are `SELL` in `LOW_VOLATILITY`, pass gateway sizing and intent proposal, then die in safety gates with `why="SAFETY_GATES:uptrend blocks short"` and `nrr_code="NRR-027"`.
- The repaired geometry therefore did improve path depth for ETHUSDT: the system now traverses kernel -> signal emission -> gateway -> trade intent, which did not occur in the prior blocker report for ETH/SOL.
- The repaired geometry did not yet improve the full execution path to placed orders in the bounded live window: `ORDER_PLACED=0`.

### INFERENCE

- Death did not primarily migrate into gateway risk or exchange execution in the current bounded runtime.
- Death redistributed into two downstream fail-closed families:
  1. strict regime allowlist on `UNCERTAIN` before signal emission;
  2. directional sanity `NRR-027` after signal emission and trade-intent proposal.

### VERDICT

- The repair improved more than admission math alone. It produced real ETH signal emission and real `TRADE_INTENT_PROPOSED` events.
- The repair did not yet improve the end-to-end trade path to placements.
- The dominant downstream choke after neutral-starvation relief is:
  - globally across admission survivors: `UNCERTAIN` strict regime allowlist, 3/5 survivors, 60.0%;
  - among cases that actually emit signals: directional sanity `NRR-027`, 2/2 emitted signals, 100%.
- No garbage-signal flood is present in the bounded live window.
- The exact next justified package is: `AURORA_DIRECTIONAL_SANITY_REDESIGN_PACK`.

## 2. Evidence Boundary

### FACTS

- Used runtime evidence:
  - `logs/aurora_core.log`
  - `logs/domain_decision_making.log`
  - `logs/order_log_v1.jsonl`
- Used code evidence:
  - `apps/reference/domains/decision_making/aurora_decision.py`
  - `apps/reference/domains/decision_making/decision_making.py`
  - `apps/reference/domains/decision_making/safety_gates.py`
  - `apps/reference/domains/regime_allowlist/contract.py`
  - `config/aurora/strategies/aurora.yaml`
  - `config/aurora/domains.yaml`
  - `apps/reference/config_models.py`
- Used baseline comparison context:
  - `reports/AURORA_BLOCKER_ATTRIBUTION_FORENSIC.md`
  - `reports/AURORA_DECISION_GEOMETRY_REPAIR_PACK_REPORT.md`
- Missing requested artifact remains missing: `Вставленная ​​уценка.md` was not present in the workspace during this audit.

### UNPROVEN

- This report does not claim a multi-day repaired-runtime distribution.
- This report does not claim that the bounded live window is statistically stable.
- This report does not claim that BTCUSDT or SOLUSDT would never emit outside the captured window.

## 3. Canonical Repaired Downstream Path

### FACTS

The current live code path is:

1. Aurora kernel computes `decision_score`, `sizing_score`, `admission_shield_mult`.
2. Strict regime allowlist runs after kernel and before signal emission.
3. Aurora emits `EVT:STRATEGY_SIGNAL_PRODUCED` only after surviving post-kernel gates.
4. `DecisionMaking` hands the signal to `StrategyGateway.process_signal()`.
5. `DecisionMaking._propose_trade_intent()` applies `SafetyGates` before building the intent.
6. Safety deny is recorded to `order_log_v1.jsonl` as `ORDER_REJECTED` from `DecisionMaking`.

### Important non-choke fact

- ETHUSDT logs show `TPSL_GUARDRAIL` warning and `TPSL_GUARDRAIL_FAIL` error immediately before `SIGNAL: SELL`, but signal emission still occurs. In the bounded live window this is observable noise, not the terminal choke.

## 4. Bounded After Distribution

### 4.1 Global counts

| Stage bucket | Count | Ratio of 11 evals |
|---|---:|---:|
| Admission blocked (`admission_shield_mult=0`) | 6 | 54.5% |
| Admission survived | 5 | 45.5% |
| Post-admission no signal, regime `UNCERTAIN` | 3 | 27.3% |
| Signal emitted | 2 | 18.2% |
| Gateway processed | 2 | 18.2% |
| Trade intent proposed | 2 | 18.2% |
| Order rejected | 2 | 18.2% |
| Order placed | 0 | 0.0% |

### 4.2 Per-symbol counts

| Symbol | Kernel evals | Admission blocked | Admission survived | No signal after admission | Signal emitted | Trade intent proposed | Order rejected | Order placed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 4 | 2 | 2 | 2 | 0 | 0 | 0 | 0 |
| ETHUSDT | 4 | 2 | 2 | 0 | 2 | 2 | 2 | 0 |
| SOLUSDT | 3 | 2 | 1 | 1 | 0 | 0 | 0 | 0 |

### 4.3 Concrete live chains

#### ETHUSDT, 2026-03-21 21:45:01

- Kernel: `decision_score=-0.169676`, `sizing_score=-0.026103`, `admission_shield_mult=0.750`, regime `LOW_VOLATILITY`, side `sell`.
- Signal: emitted.
- Gateway: processed.
- Intent: proposed.
- Final fate: `ORDER_REJECTED`, `NRR-027`, `SAFETY_GATES:uptrend blocks short`, rid `aurora_ETHUSDT_1774122301402`.

#### ETHUSDT, 2026-03-21 21:50:01

- Kernel: `decision_score=-0.169308`, `sizing_score=-0.025990`, `admission_shield_mult=0.750`, regime `LOW_VOLATILITY`, side `sell`.
- Signal: emitted.
- Gateway: processed.
- Intent: proposed.
- Final fate: `ORDER_REJECTED`, `NRR-027`, `SAFETY_GATES:uptrend blocks short`, rid `aurora_ETHUSDT_1774122601677`.

#### BTCUSDT and SOLUSDT non-emitting survivors

- BTCUSDT at 21:35 and 21:40 survives admission with non-zero `decision_score`, but remains in regime `UNCERTAIN` and never emits `SIGNAL`.
- SOLUSDT at 21:40 survives admission with `side=sell`, regime `UNCERTAIN`, but never emits `SIGNAL`.
- In the current code/config this is consistent with strict allowlist suppression because `UNCERTAIN` is not listed in `allowed_regimes` for BTCUSDT, ETHUSDT, or SOLUSDT.

## 5. Before vs After

### FACTS

From the prior blocker attribution baseline:

- Before repair, the dominant global death stage was neutral no-side, approximately 80% of all bars.
- Before repair, ETHUSDT and SOLUSDT had 0 observed signals emitted in the cited runtime baseline.
- Before repair, safety-gate rejects were already dominated by `NRR-027`, but only after the small minority of signals that survived the kernel.

### Bounded comparison

| Metric | Prior baseline | Repaired bounded live window |
|---|---:|---:|
| ETHUSDT signal emitted | 0 | 2 |
| ETHUSDT trade intent proposed | 0 | 2 |
| ETHUSDT order placed | 0 | 0 |
| SOLUSDT signal emitted | 0 | 0 |
| BTCUSDT signal emitted | present but sparse in prior baseline | 0 in captured bounded window |
| Global dominant death | neutral starvation | admission block still large, but downstream choke now observable |

### Interpretation

- The repair did not merely move blocking from one hidden neutral bucket to another hidden neutral bucket.
- It opened a real ETH downstream path to signal and intent.
- The repaired system still lacks proof of execution success because every emitted ETH signal in the captured window is killed by directional sanity.

## 6. Downstream Blocker Binding Table

| Blocker family | Count in bounded window | Scope | Config path | Model field | Code owner | Condition | Runtime effect |
|---|---:|---|---|---|---|---|---|
| Strict regime allowlist on `UNCERTAIN` | 3 | post-admission, pre-signal | `config/aurora/strategies/aurora.yaml -> aurora.assets.<SYM>.allowed_regimes` | `AuroraInstrumentConfig.allowed_regimes` | `aurora_decision.py` strict allowlist gate + `regime_allowlist/contract.py` | kernel survives admission, but `state_regime_for_gate='UNCERTAIN'` and `UNCERTAIN` absent from allowlist | no `SIGNAL`, no gateway, no trade intent |
| Directional sanity `NRR-027` | 2 | post-signal, post-gateway, pre-execution | `config/aurora/domains.yaml -> decision_making.directional_sanity.*`; `config/aurora/strategies/aurora.yaml -> aurora.safety_gates.enabled` | `DecisionMakingDomainConfig.directional_sanity`; `SafetyGatesConfig.enabled` | `safety_gates.py` directional gate + `decision_making.py::_handle_safety_deny` | emitted ETH `SELL` while trend gate resolves `UP`, so short is blocked | `ORDER_REJECTED`, `why='SAFETY_GATES:uptrend blocks short'`, no order placement |
| Admission shield zero | 6 | upstream residual choke, not post-admission | `config/aurora/strategies/aurora.yaml -> aurora.decision.decision_geometry.*`; shield config under `aurora.decision.scoring_engine.*` | `DecisionGeometryConfig.admission_shield_floor`; `DecisionConfig.decision_geometry` | `quadratic_scoring_kernel` via `aurora_decision.py` observability | shield cascade yields `admission_shield_mult=0.000` and `decision_score=0.000000` | no side, no downstream traversal |

## 7. Health Assessment

### FACTS

- No `ORDER_PLACED` event is present for BTCUSDT, ETHUSDT, or SOLUSDT in the repaired bounded window.
- No evidence in this window shows gateway risk, exposure, leverage, or venue rejection becoming the dominant choke.
- Both emitted ETH signals are consistent in direction and consistent in failure mode.
- Signal count remains low: 2 signals from 11 repaired evaluations.

### INFERENCE

- There is no evidence of garbage-signal flood.
- There is evidence of directional mismatch for the surviving ETH emissions.
- The system is healthier than pre-repair at the signal-path level, but not yet healthy at the execution-conversion level.

### Narrow health verdict

- `PARTIAL_PATH_IMPROVEMENT_CONFIRMED`
- `DOWNSTREAM_REDISTRIBUTION_CONFIRMED`
- `END_TO_END_EXECUTION_RECOVERY_NOT_CONFIRMED`
- `NO_GARBAGE_SIGNAL_FLOOD_OBSERVED`

## 8. Why The Next Package Is Directional Sanity, Not Something Else

### Selected package

`AURORA_DIRECTIONAL_SANITY_REDESIGN_PACK`

### Why this package is justified

- The repaired system now reaches real signal emission and real trade-intent proposal on ETHUSDT.
- Every emitted repaired signal in the bounded live window dies on the same downstream family: `NRR-027`.
- That makes directional sanity the first proved blocker family that now prevents repaired emissions from converting into orders.

### Why the other options are not justified by current evidence

- `AURORA_EXECUTION_GATE_AUDIT_PACK`
  - Not justified: no emitted repaired signal died in execution gate in the bounded window.
- `AURORA_GATEWAY_RISK_BLOCKER_PACK`
  - Not justified: gateway processed both emitted ETH signals successfully.
- `AURORA_ROLLOUT_GUARDRAIL_PACK`
  - Not justified: no flood, no runaway placements, no order storm.
- `AURORA_REPAIR_ROLLBACK_REASSESS_PACK`
  - Not justified: the repair created a real deeper path for ETH; rollback would discard a proved gain.

## 9. Final Answer To The User Questions

### Куди саме перетекла смерть після зменшення neutral starvation

- First into strict regime allowlist on `UNCERTAIN` for BTCUSDT and SOLUSDT before signal emission.
- Then, for the ETHUSDT cases that do emit, into safety-gate directional sanity `NRR-027` after trade-intent proposal.

### Який blocker family тепер домінує downstream choke

- Across all admission survivors in the bounded live window: strict regime allowlist on `UNCERTAIN`.
- Across actual signal-emitting survivors: directional sanity `NRR-027`.

### Чи repair покращив full signal path, чи лише посунув блокування далі

- It improved the real path beyond admission for ETHUSDT: signal emission and trade intent are now observed live.
- It did not yet recover full order placement.

### Чи є garbage-signal flood

- No. Emission volume remains low and fully fail-closed downstream.

### Exact next package

- `AURORA_DIRECTIONAL_SANITY_REDESIGN_PACK`
