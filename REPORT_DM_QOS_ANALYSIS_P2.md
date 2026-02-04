# REPORT: DM_QOS_DEEP_DIVE_ANALYSIS (P2)

Target: `apps/reference/domains/decision_making/decision_making.py`

Scope note: This report is strictly code-forensics on `decision_making.py` as it exists. No assumptions about other processes or persistence layers unless explicitly evidenced in-file.

---

## Section 1: Evidence Map (Split-Brain & Mutations)

### 1.1 `_qos_state` initialization (intended structure)

`DecisionMaking.__init__` initializes `_qos_state` as a `defaultdict` partitioned by `strategy_id`, where each partition is a dict containing keys like `last_exposure_block`, `symbol_cooldowns`, and `symbol_intent_counts`. This implies the **intended shape**:

```py
_qos_state[strategy_id]["last_exposure_block"]
_qos_state[strategy_id]["symbol_cooldowns"][symbol]
_qos_state[strategy_id]["symbol_intent_counts"][symbol]
```

Evidence:
- `__init__` @ `decision_making.py:186`

---

### 1.2 Mapping: every read/write of `self._qos_state`

#### Group A — Flat access (global keys on `_qos_state`)

Reads:
- `_check_qos_rules` @ `decision_making.py:1376` (`dget(self._qos_state, "last_exposure_block", 0.0)`)
- `_check_qos_rules` @ `decision_making.py:1382` (`dget(self._qos_state, "symbol_cooldowns", {})`)
- `_check_qos_rules` @ `decision_making.py:1389` (`dget(self._qos_state, "symbol_intent_counts", {})`)

Writes:
- `_handle_exposure_block` @ `decision_making.py:1476` (`self._qos_state["last_exposure_block"] = current_time`)

Key observation:
- These treat `_qos_state` as a single flat dict with global keys, which directly contradicts the strategy-partitioned structure created in `__init__` (`decision_making.py:186`).

#### Group B — Partitioned access (by `strategy_id`)

Reads (and implicit partition creation due to `defaultdict` indexing):
- `_qos_allow` @ `decision_making.py:1293` (`strat_state = self._qos_state[strategy_id]`)
- `_calculate_next_allowed_time` @ `decision_making.py:1413` (`strat_state = self._qos_state[strategy_id]`)

Writes:
- `_update_symbol_cooldown` @ `decision_making.py:1344` (`strat_state = self._qos_state[strategy_id]`, then writes cooldown)
- `_update_intent_count` @ `decision_making.py:1354` (`strat_state = self._qos_state[strategy_id]`, then writes counters)
- `_update_qos_state` @ `decision_making.py:1446` (`strategy_state = self._qos_state[strategy_id]`, then writes cooldown + counters)

---

### 1.3 Split-brain conflict check (structural mismatch + missing synchronization)

**Conflict 1 — Global vs partitioned “last_exposure_block”:**
- Modern path `_qos_allow(..., is_exposure_block=True)` reads `strat_state["last_exposure_block"]` (per-strategy) @ `decision_making.py:1297`.
- Legacy-ish `_handle_exposure_block` writes `_qos_state["last_exposure_block"]` (global/flat) @ `decision_making.py:1476`.
- There is **no synchronization** bridging these (no code that copies/propagates global → per-strategy or vice versa).

**Conflict 2 — Global vs partitioned “symbol_cooldowns” and “symbol_intent_counts”:**
- `_check_qos_rules` reads flat keys @ `decision_making.py:1382` and `decision_making.py:1389`.
- The active strategy-gateway QoS uses partitioned state via `_qos_allow`/`_update_qos_state` @ `decision_making.py:1293` and `decision_making.py:1446`.
- There is **no synchronization**; these are logically separate storage locations.

**Risk amplifier — Type corruption hazard:**
- `_qos_state` is annotated as `dict[str, dict[str, Any]]` @ `decision_making.py:186`.
- `_handle_exposure_block` assigns a `float` into the top-level dict under key `"last_exposure_block"` @ `decision_making.py:1476`, which violates that type and can break any future code that expects `_qos_state[some_key]` to always be a dict.

**Dead/unused warning (important for “objective criticality”):**
- `_check_qos_rules` has **no callers** in this repo via static search (`_check_qos_rules(` appears only at its definition).
- `_handle_exposure_block` has **no callers** in production code (only referenced in docs).
- As a result, the split-brain is currently a **latent defect** in runtime paths (but becomes immediately user-impacting if these methods are wired back in).

---

### 1.4 `_qos_allow` side-effects (CQRS / “query mutates state”)

`_qos_allow` returns `(allowed: bool, reject_reason)` but performs mutations:

1) **Implicit mutation (partition creation)**
- `strat_state = self._qos_state[strategy_id]` @ `decision_making.py:1293`
- Because `_qos_state` is a `defaultdict`, this line creates a new partition as a side effect of “checking”.

2) **Explicit mutation (rate-limit window reset)**
- Resets `intent_data["count"]` and `intent_data["window_start"]` when the window elapsed ≥ 60s @ `decision_making.py:1325`–`decision_making.py:1328`.
- This mutation persists **only if** `intent_data` is a reference to an existing dict stored in `strat_state["symbol_intent_counts"][symbol]`; if `symbol` was absent and `intent_data` came from the fallback default created at `decision_making.py:1320`, the reset does **not** persist (because that fallback dict is not written back).

Notably, `_qos_allow` does **not**:
- increment intent counts, or
- update symbol cooldown timestamps.

Those mutations occur later in `_update_qos_state` (and only after a successful intent emission path) @ `decision_making.py:1231` and `decision_making.py:1449`–`decision_making.py:1465`.

---

### 1.5 All callers of `_qos_allow` (and “dry-run” risk)

Production caller:
- `_on_strategy_signal_gateway` @ `decision_making.py:844`

Context classification:
- This call is in the **live gating path** (not a dry-run/shadow/validation call): `_on_strategy_signal_gateway` is the domain gateway that blocks/defers/emits intents.

Other callers (tests/docs):
- Unit tests call it directly (e.g., `tests/unit/test_qos_nrr012.py`).
- Docs demonstrate calling it (e.g., `apps/reference/domains/decision_making/docs/TESTING.md`).

Conclusion:
- Today, `_qos_allow` is **not** called from any “read-only” context in production code, but it is **not safe** to use in logging/telemetry/dry-run contexts because it can mutate state (partition creation + window reset).

---

## Section 2: Scenario Outcomes

### Scenario A: “Ghost” Block (Split-Brain)

Question: If a legacy/global block is set in `_qos_state`, does the modern `_qos_allow` see it?

Outcome (based on actual code paths):
- Modern `_qos_allow` consults per-strategy `strat_state["last_exposure_block"]` only when `is_exposure_block=True` @ `decision_making.py:1296`–`decision_making.py:1306`.
- `_handle_exposure_block` writes a flat/global `_qos_state["last_exposure_block"]` @ `decision_making.py:1476`, which `_qos_allow` will **never read**.
- Additionally, `_qos_allow` is never called with `is_exposure_block=True` anywhere in `decision_making.py` (string appears only in `_qos_allow`’s signature/body).

Result:
- A “global cooldown” recorded via `_handle_exposure_block` would be a **ghost** to the modern QoS gate: strategy intents would continue to be evaluated under only symbol cooldown + per-symbol rate limit.
- Even worse: the exposure-block cooldown mechanism is effectively **non-functional** in the current runtime wiring (no calls to set per-strategy `last_exposure_block`, and no calls using `is_exposure_block=True`).

Business impact:
- If the business expectation is “after exposure-limit breach, stop trading for N seconds”, the current implementation provides **no enforceable guarantee** in the active gateway flow.

### Scenario B: “Heisenberg” Check (Side-Effects)

Question: If we add `logger.info(f"Can trade: {self._qos_allow(...)}")`, can it accidentally consume quota or allow a double-burst?

Outcome:
- `_qos_allow` does **not** increment counts or update cooldowns; it mainly *reads* state.
- However, it **can mutate**:
  - create the strategy partition via `defaultdict` indexing @ `decision_making.py:1293`;
  - reset the rate-limit window when ≥60s elapsed @ `decision_making.py:1325`–`decision_making.py:1328`.

Result:
- A log call would **not “consume” a trade quota** (no counter increment), but it can change the window start alignment at minute boundaries.
- The specific “double-burst” hypothesis (log call resets window then allows extra orders) is **not supported** by the current code: window reset happens only when the window has already expired (≥60s), where a reset is logically equivalent to what the next real trade would need anyway.

Business impact:
- Low immediate risk, but the method violates CQRS expectations and is unsafe for future “shadow / dry-run / audit-only” use.

### Scenario C: “Amnesiac” Restart (Persistence)

Question: What happens to QoS cooldowns if the process restarts?

Evidence:
- `_qos_state` is initialized in-memory in `__init__` @ `decision_making.py:186`.
- No persistence, serialization, or reload logic for `_qos_state` is present in `decision_making.py`.

Result:
- All QoS cooldowns and per-minute counters are **lost on restart**.
- Immediately after restart, QoS will behave as if the bot has not recently traded (until it rebuilds state from new intents).

Business impact:
- If QoS is a safety control meant to prevent rapid re-entry after losses/blocks, a restart creates a “fresh memory” window that can lead to immediate re-trading.
- Whether that causes “re-enter the same losing position” depends on *other* gates (portfolio state, re-entry cooldown gates, etc.), but QoS itself provides **no persistence-based protection**.

---

## Section 3: Verdict (Criticality, Debt, Go/No-Go)

### Issue 1 — Split-Brain `_qos_state` structure (flat vs partitioned)

Severity: **High (latent) / Medium (current runtime)**

Objective justification:
- The file defines `_qos_state` as strategy-partitioned @ `decision_making.py:186`, but still contains flat/global reads @ `decision_making.py:1376`, `decision_making.py:1382`, `decision_making.py:1389` and a flat/global write @ `decision_making.py:1476`.
- There is no synchronization between these “worldviews”.
- `_handle_exposure_block` additionally risks **type corruption** by storing a float into a dict-of-dicts @ `decision_making.py:1476`.
- Today, these legacy/global methods appear unused, reducing immediate blast radius; however, wiring them back in (or a partial refactor) can silently produce “ghost” cooldowns and inconsistent enforcement.

Business impact:
- High once activated: inconsistent enforcement across strategies can lead to over-trading, violation of exchange limits, fee amplification, or risk policy breaches (especially if “exposure block cooldown” is expected to halt trading).

### Issue 2 — CQRS violation: `_qos_allow` performs state mutation

Severity: **Low–Medium**

Objective justification:
- `_qos_allow` creates partitions via `defaultdict` indexing @ `decision_making.py:1293`.
- `_qos_allow` resets rate-limit window state @ `decision_making.py:1325`–`decision_making.py:1328`.
- Production caller is the live gate `_on_strategy_signal_gateway` @ `decision_making.py:844`, so this does not currently create an obvious “log line consumes quota” hazard.

Business impact:
- Low today; medium future risk if `_qos_allow` is reused for “dry-run checks”, audit logging, or preflight validation (because calling it changes state and can affect subsequent enforcement).

### Issue 3 — No persistence for QoS memory across restarts

Severity: **Medium**

Objective justification:
- `_qos_state` is purely in-memory and reset at `__init__` @ `decision_making.py:186`, with no persistence in-file.

Business impact:
- A restart can remove protective throttles (cooldown / rate-limit memory), potentially allowing rapid re-entry or bursts after a crash/redeploy.

---

### Architecture debt assessment

Not currently sustainable for adding strategies safely, because:
- The codebase contains both “partitioned” and “flat/global” QoS state access patterns without a single authoritative contract.
- Critical QoS concepts (exposure-block cooldown, busy-guard) exist as code but are not wired into the active gateway flow; this increases the chance of “half-integrations” during future changes.
- `_qos_allow` lacks an explicit “commit=False” or “dry_run” contract (unlike arbitration), making it easy to misuse.

### Go/No-Go recommendation (Refactor P2)

Recommendation: **Go (proceed with P2 refactor)**.

Rationale:
- The split-brain state model is an architectural foot-gun: it is easy to accidentally re-enable dead paths and get inconsistent QoS enforcement.
- The exposure-block mechanism appears non-functional in the current gateway wiring; if the business expects it, refactoring is required to make it real and testable.
- A refactor can cleanly separate:
  - *Query* (pure decision: “would this be allowed?”) from
  - *Command* (state commit: “record that we acted/blocked/deferrred”),
  while also deciding explicitly whether QoS should count attempted intents or only successful ones.

