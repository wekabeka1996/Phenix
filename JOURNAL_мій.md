## 2025-11-23: OCO-AUDIT-R1 Package Completed

### Summary

Completed full audit package **OCO-AUDIT-R1** for Aggregated OCO / TP-SL lifecycle analysis.

### Tasks Completed

#### ✅ OCO-AUDIT-R1-A: Architectural Map
- **File:** `docs/audit/OCO_AUDIT_R1A_ARCH_MAP.md`
- **Output:** Complete architectural documentation
  - 11 component modules mapped
  - 10+ FSM events identified
  - 2 implementation paths (Legacy vs V2)
  - 11 identified gaps (P0-P2 severity)
  - State diagram with 8 states
  - Event-to-handler mapping for both paths
  
**Key Findings:**
- Dual implementation (Legacy FSM + V2 Runtime) creates maintenance burden
- `recalc_on_partial_close=false` default in legacy is critical bug
- No `position_id` binding — brackets tied only to `(symbol, side)` key

#### ✅ OCO-AUDIT-R1-B: Size Synchronization
- **File:** `docs/audit/OCO_AUDIT_R1B_SIZE_SYNC.md`
- **Output:** Position size sync audit
  - 4 scenarios analyzed (partial close, scale-in, reverse, full close)
  - 3 formal invariants defined (R1-B-INV-1/2/3)
  - 4 legacy gaps identified
  - Complete code traces for each scenario
  
**Key Findings:**
- **R1-B-GAP-1 (P0):** Legacy `recalc_on_partial_close=false` leaves positions unprotected
- **R1-B-INV-1:** Bracket qty ≤ position qty — violated in legacy, enforced in V2
- V2 always enforces recalc via `BracketService.evaluate()`

#### ✅ OCO-AUDIT-R1-C: Race Conditions
- **File:** `docs/audit/OCO_AUDIT_R1C_RACES.md`
- **Output:** Race condition analysis
  - 4 race scenarios with sequence diagrams
  - 7 risks cataloged (R1-C-RISK-1 through R1-C-RISK-7)
  - Data staleness analysis (position & orders sources)
  - Mitigation strategies documented
  
**Key Findings:**
- **R1-C-RISK-1 (P0):** OrderGuardian cleanup before position visible
- **R1-C-RISK-3 (P0):** Concurrent fills → duplicate SL/TP
- V2 mitigates via throttling (3s), snapshot TTL, guard loop

#### ✅ OCO-AUDIT-R1-D: Test Plan
- **File:** `docs/audit/OCO_AUDIT_R1D_TESTPLAN.md`
- **Output:** Comprehensive test package proposal
  - 48 test scenarios across 4 groups
  - Fixture structure defined
  - Test-to-invariant mapping
  - Test-to-risk mapping
  - Mock implementations
  - Execution strategy (3-week plan)
  
**Key Deliverables:**
- Group 1: Position size changes (10 tests)
- Group 2: Close + re-entry races (5 tests)
- Group 3: Timeout/snapshot (6 tests)
- Group 4: Manual cancel (4 tests)
- Unit tests: Invariant validation (5 tests)
- Integration tests: E2E flows (10+ tests)

### Artifacts Created

```
docs/audit/
├── OCO_AUDIT_R1A_ARCH_MAP.md       (Architecture)
├── OCO_AUDIT_R1B_SIZE_SYNC.md      (Size sync audit)
├── OCO_AUDIT_R1C_RACES.md          (Race conditions)
└── OCO_AUDIT_R1D_TESTPLAN.md       (Test plan)
```

### Invariants Defined

| ID | Definition | Enforcement |
|----|------------|-------------|
| **R1-B-INV-1** | Bracket qty ≤ position qty | Legacy: Config-dependent ❌; V2: Automatic ✅ |
| **R1-B-INV-2** | Flat position → No brackets within N events | Both: ✅ Satisfied |
| **R1-B-INV-3** | No hanging brackets (untracked orders) | Legacy: At risk ⚠️; V2: Enforced ✅ |

### Risks Cataloged

| ID | Severity | Description | Mitigation |
|----|----------|-------------|------------|
| **R1-C-RISK-1** | P0 | OrderGuardian cleanup timing | V2: TTL protection |
| **R1-C-RISK-2** | P1 | Symbol-only cleanup key | V2: Side segregation |
| **R1-C-RISK-3** | P0 | Concurrent fills duplicate brackets | V2: Throttling (3s) |
| **R1-C-RISK-4** | P1 | Duplicate bracket orders | V2: Equivalence check |
| **R1-C-RISK-5** | P2 | Stale ORDERS_SNAPSHOT | V2: Force refresh |
| **R1-C-RISK-6** | P1 | Position flip cleanup | V2: Watchdog auto-cancel |
| **R1-C-RISK-7** | P1 | Watchdog + fill race | V2: Throttling + equivalence |

### Gaps Identified

| ID | Severity | Component | Description |
|----|----------|-----------|-------------|
| **R1-A-GAP-1** | P1 | Architecture | Dual implementation drift |
| **R1-A-GAP-5** | P0 | Legacy | `_clear_guardian_bracket_set()` NOT called on partial close |
| **R1-B-GAP-1** | P0 | Legacy Config | `recalc_on_partial_close=false` default |
| **R1-B-GAP-2** | P1 | Legacy | Guardian metadata cleared without recalc |

### Statistics

- **Total audit artifacts:** 4 documents
- **Total pages:** ~60 pages of analysis
- **Total test scenarios proposed:** 48
- **Total invariants defined:** 3
- **Total risks identified:** 7
- **Total gaps identified:** 11
- **Time invested:** ~3 hours

### Recommendations

#### Immediate Actions (P0):
1. ✅ Set `recalc_on_partial_close=true` in all production configs (Legacy)
2. ✅ Maintain V2 invariants (already enforced)
3. 📊 Add monitoring for `partial_close_no_recalc_count` metric

#### Short-term Actions (P1):
1. 🧪 Implement test suite from R1-D (48 tests)
2. 🔍 Add `position_id` to bracket_set key
3. 📈 Track watchdog violations in production metrics

#### Long-term Actions (P2):
1. 🏗️ Complete legacy → V2 migration
2. 🧹 Remove legacy code paths
3. 📚 Document V2 contracts in wiki

### Next Phase

**PACK: OCO-STABILIZE-R2** (Future) will implement:
- All 48 tests from R1-D
- Fixes for identified P0/P1 gaps
- Enhanced monitoring and alerting
- Production validation

### References

- Parent task: `PACK: OCO-AUDIT-R1`
- Previous work: `INVESTIGATION_AGGREGATED_OCO.md` (Nov 19, 2025)
- Related: `EP_STAB_LIVEPOS_SL_SPAM_AUDIT.md`

---

**Completed by:** AI Auditor (Antigravity)  
**Date:** 2025-11-23  
**Status:** ✅ READY FOR HANDOFF
