# Phase 9 «Quadratic Brain» — План Виправлень v4.0

> **Дата:** 2026-02-16 (ре-аудит після 2 днів)  
> **Мета:** Довести Phase 9 до production-ready runtime

---

## Поточний стан — Верифіковано в коді 2026-02-16T19:00

| Компонент | Статус | Деталі |
|---|---|---|
| Pillar Indicators | ✅ DONE | 392L: ROC, LinReg+ADX, SMA200, aggregate |
| Pillar Backfill | ✅ DONE | 273L: D1/H4/M15 fetch, warmup_pillars |
| PillarsConfig (Pydantic) | ✅ DONE | `extra="forbid"` |
| Quadratic Kernel | ✅ DONE | 310L: `sign(Σ)×Σ²`, shield_fn, feature flag |
| scoring_version routing | ✅ DONE | `handler:275-281` → `QuadraticScoringKernel` |
| ContextShield | ⚠️ 80% | Regime multipliers ✅, **TTL stale policy ❌** |
| MemoryShield | ✅ DONE | 470L: evaluate pure-read, record_visit idempotent |
| MemoryShield Persistence | ✅ DONE | dirty-flag + flush_interval_sec |
| DangerZoneShield | ✅ DONE | 120L: `DANGER_ZONE:` prefix, 3 checks |
| InstrumentQuantizer | ✅ DONE | 261L: quantize + risk_adjusted + structural_stop |
| ExecutionGate | ✅ DONE | 212L: 5-stage gate |
| EntryPlan | ✅ DONE | 312L: ATR-based SL/TP, structural stop |
| ExitManager | ⚠️ 85% | DZ + Time + Reversal + PnL guard ✅, **Trailing ❌** |
| ModeManager | ✅ DONE | PARANOID/CURIOUS |
| Dashboard | ✅ DONE | Sharpe/WinRate/MemCoverage |
| Knife Entry | ❌ TODO | Blocked by ExecutionGate counter-trend |
| Fallback on Error | ❌ TODO | `fallback_on_error: legacy` not wired |

---

## Sprint 1 — ✅ COMPLETE (всі 8 fixes verified)

Деталі: див. walkthrough.md

---

## Sprint 2 — Gaps (оновлений після ре-аудиту)

### P1 — Необхідно для production

| # | Задача | Оцінка |
|---|---|---|
| S2-1 | ContextShield: додати TTL stale policy (`regime_ts_ms`, 4h TTL, stale multipliers) | 2-3h |
| S2-2 | ExitManager: додати Trailing Stop (`activation_r: 1.5`) | 3-4h |
| S2-3 | Unit тести: ContextShield, MemoryShield, DangerZone | 4-6h |
| S2-4 | Unit тести: ExecutionGate, ExitManager | 3-4h |
| S2-5 | Unit тести: InstrumentQuantizer | 2-3h |
| S2-6 | Mode coverage test (backtest/live/hybrid/optimization) | 2-3h |

### P2 — Hardening / Nice-to-have

| # | Задача | Оцінка |
|---|---|---|
| S2-7 | `fallback_on_error: legacy` wrapper в handler | 1-2h |
| S2-8 | Knife Entry протокол в ExecutionGate | 4-6h |
| S2-9 | DangerZone: ATR-based trigger (roadmap alignment) | 2-3h |
| S2-10 | Toggle verification (кожен компонент вимикається) | 2-3h |
| S2-11 | Backtest порівняння v2 vs quadratic | 4-6h |

---

## Критерії завершення (Definition of Done)

### Sprint 1 (✅ DONE)
- [x] DangerZone `DANGER_ZONE:` prefix
- [x] MemoryShield rewrite (coarse-hash, decay, ABC)
- [x] MemoryShield `evaluate()` pure read
- [x] MemoryShield `record_visit()` idempotent + handler-wired
- [x] ExitManager fail-closed (strict mode)
- [x] ExitManager PnL guard + cross-price guard
- [x] Persistence throttling (dirty-flag, flush interval)
- [x] InstrumentQuantizer wired + fail-closed
- [x] `scoring_version: quadratic` enabled
- [x] `ShieldResult.details` field

### Sprint 2 (IN PROGRESS)
- [ ] ContextShield TTL stale policy
- [ ] ExitManager Trailing Stop
- [ ] Unit tests (9 missing of 13)
- [ ] Mode coverage testing
- [ ] `fallback_on_error` wrapper
- [ ] Knife Entry protocol
- [ ] Toggle verification
- [ ] Backtest comparison

---

*v4.0 — 2026-02-16T19:50 — Full re-audit, 6 gaps found, Sprint 2 updated*
