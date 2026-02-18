# Intent Reject Audit — 72h Window

> **Period:** 2026-02-15 23:59 UTC → 2026-02-18 23:59 UTC  
> **Generated:** 2026-02-18 19:21 UTC

---

## §1 — Топ-10 причин REJECT (reason_code из WAL)

| Rank | reason_code | Count | % of intents |
|-----:|:------------|------:|-------------:|
| 1 | `NRR-046` | 4,139 | 70.2% |
| 2 | `GATE_ANTI_FOMO_SIGMA` | 739 | 12.5% |
| 3 | `REGIME_NOT_ALLOWLISTED` | 590 | 10.0% |
| 4 | `GATE_ANTI_FLAT_SIGMA` | 46 | 0.8% |
| 5 | `ATR_MISSING_FAIL_CLOSED` | 17 | 0.3% |

### Full why-string

| Rank | why | Count |
|-----:|:----|------:|
| 1 | `Ignoring tick-level EVT:FEATURES_CALCULATED (bar-only strategies)` | 4,009 |
| 2 | `aurora_handler:anti_fomo: VOL_GATE` | 739 |
| 3 | `aurora_handler:strict_regime_allowlist: REGIME` | 590 |
| 4 | `EP-01.3-INT: LIMIT requires tf_sec to derive valid_for_ms` | 130 |
| 5 | `aurora_handler:anti_flat: VOL_GATE` | 46 |
| 6 | `aurora_handler:volatility_entry: DATA_NOT_READY` | 17 |

---

## §2 — Загальна кількість Intents

| Метрика | Значення |
|:--------|--------:|
| TRADE_INTENT_PROPOSED | 363 |
| TRADE_INTENT_REJECTED | 5,531 |
| **Rejected rate** | **93.8%** |
| Orders PLACED | 520 |
| Orders CANCELLED/REJECTED | 198 |

---

## §3 — % Rejected по групах гейтів

| Gate Group | Count | % of rejected |
|:-----------|------:|--------------:|
| Noise (tick-filter) | 4,139 | 74.8% |
| QoS | 785 | 14.2% |
| Regime | 590 | 10.7% |
| Data/Infra | 17 | 0.3% |

---

## §4 — Intents, що пройшли гейти → Limit Cancelled (`ORDER_REJECTED`)

| Метрика | Значення |
|:--------|--------:|
| Orders placed | 520 |
| Cancelled/rejected | 198 |
| **Cancel rate** | **38.1%** |

### Top-5 cancel reasons

| Reason | Count |
|:-------|------:|
| `adapter_execution_failed` | 161 |
| `MAKER_ONLY_REJECT` | 37 |

---

## §5 — Text-log Gate Hits

### domain_decision_making.log

| Keyword | Hits |
|:--------|-----:|
| `SAFETY_GATE` | 9 |

---
*Source: ops/wal/, logs/domain_decision_making.log, logs/domain_risk_management.log*