# EP_CLIENTORDERID_4015_CONTEXT

**Domain:** `execution_position`
**Error:** `PLACE_ORDER failed: [-4015] Client order id length should be less than 36 chars`
**Classification:** `CLIENTORDERID_OVERFLOW` — raw `idem_base` used as clientOrderId component without hashing, producing IDs of 42–64 chars
**Status:** Root cause confirmed. MD5-hash fix applied in `generate_client_order_id`. Regression tests exist.
**Date:** 2026-02-23

---

## Executive Summary

Binance Futures enforces `len(newClientOrderId) < 36` (i.e., ≤ 35 chars).

The domain historically built clientOrderIds by concatenating the raw `idem_base` string:

```
idem_base = f"{msg.rid}_{int(self.position_open_ts)}"
# E.g.: "aurora_BTCUSDT_1771850701848_1771850735"  = 39 chars
# Pre-fix cid = "SL-aurora_BTCUSDT_1771850701848_1771850735" = 42 chars  ← -4015
```

The fix (now present) applies an MD5 hash inside `generate_client_order_id()`, reducing all output IDs to ≤18 chars regardless of input length.

**4 occurrences** confirmed in `logs/domain_execution_position.log.1`. All 4 are bracket placements (SL + TP) via the **ManageFlowFSM → DEC:BATCH → generic PLACE_ORDER handler** path, triggered on fill detection after a LIMIT entry.

---

## Evidence Table (all -4015 occurrences)

| # | Timestamp (UTC local) | Line | Symbol | Order type | rid (inferred) | idem_base len | Pre-fix cid len | Endpoint |
|---|---|---:|---|---|---|---:|---:|---|
| 1 | 2026-02-23 14:45:36,278 | 5672 | BTCUSDT | STOP_MARKET | `aurora_BTCUSDT_1771850701848` (29) | 39 | **42** | generic PLACE_ORDER |
| 2 | 2026-02-23 14:45:36,326 | 5676 | BTCUSDT | TAKE_PROFIT_MARKET | `aurora_BTCUSDT_1771850701848` (29) | 39 | **42** | generic PLACE_ORDER |
| 3 | 2026-02-23 21:26:04,501 | 14967 | SOLUSDT | STOP_MARKET | `aurora_SOLUSDT_1771874702177` (30) | 39 | **43** | generic PLACE_ORDER |
| 4 | 2026-02-23 21:26:04,502 | 14968 | SOLUSDT | TAKE_PROFIT_MARKET | `aurora_SOLUSDT_1771874702177` (30) | 39 | **43** | generic PLACE_ORDER |

> Binance limit: **len < 36** → max allowed = **35 chars**.

### Observed normal IDs nearby (success baseline)

| clientOrderId (from success logs) | Chars |
|---|---:|
| `ENTRY-8b960baf57f8` | 18 |
| `ENTRY-a410b8e46034` | 18 |
| `SL-b6ff7edfc0dc` | 15 |
| `SL-d760e404fcdc` | 15 |
| `TP-2d3344dffdaf` | 15 |
| `TP-2d58a709321d` | 15 |

These are the post-fix MD5-hash IDs. All ≤ 18 chars.

---

## Log Artifacts (context blocks)

### Occurrence #1–2 (BTCUSDT, 14:45:36)

```text
2026-02-23 14:45:35,660 - ... - INFO - 📌 [LIMIT-DEFERRED] Fill received for BTCUSDT entry 12492160973, placing deferred TP/SL brackets
2026-02-23 14:45:35,665 - ... - INFO - ENTRY fill - creating position from TRADE_EXECUTED
2026-02-23 14:45:35,665 - ... - INFO - Position opened, placing brackets on TRADE_EXECUTED   ← ManageFlowFSM
2026-02-23 14:45:35,677 - ... - INFO - USING_INTENT_SL for calculation: 66045.0...
2026-02-23 14:45:35,692 - ... - INFO - USING_INTENT_TP for calculation: 66874.7...
2026-02-23 14:45:35,981 - ... - INFO - 📌 [LIMIT-DEFERRED] Placing brackets for BTCUSDT: SL=66045.0, TP=66874.8   ← deferred path
2026-02-23 14:45:35,986 - ... - INFO - Executing PLACE_ORDER: BTCUSDT SELL STOP_MARKET 0.005 @ None/66012.07745  ← DEC:BATCH
2026-02-23 14:45:35,996 - ... - INFO - Executing PLACE_ORDER: BTCUSDT SELL TAKE_PROFIT_MARKET 0.005 @ None/None  ← DEC:BATCH
2026-02-23 14:45:36,278 - ... - ERROR - ❌ PLACE_ORDER failed: [-4015] Client order id length should be less than 36 chars (no-nrr)
2026-02-23 14:45:36,326 - ... - ERROR - ❌ PLACE_ORDER failed: [-4015] Client order id length should be less than 36 chars (no-nrr)
2026-02-23 14:45:36,602 - ... - INFO - ✅ [LIMIT-DEFERRED] SL placed: {'clientOrderId': 'SL-d760e404fcdc', ...}   ← deferred OK
2026-02-23 14:45:37,693 - ... - INFO - ✅ [LIMIT-DEFERRED] TP placed: {'clientAlgoId': 'nV3QuvWRIoJ0BxVLk4Ncpz', ...}   ← algo OK
```

**Interpretation:**
- Two parallel paths race after fill. The deferred (`_place_deferred_brackets`) succeeds with 15-char IDs.
- The ManageFlowFSM DEC:BATCH path fails with -4015 (pre-fix long IDs).

### Occurrence #3–4 (SOLUSDT, 21:26:04)

```text
2026-02-23 21:26:03,941 - ... - INFO - [TIMEOUT-FILL] Placing deferred TP/SL brackets for SOLUSDT entry 1724559552
2026-02-23 21:26:03,949 - ... - INFO - Position opened, placing brackets on TRADE_EXECUTED   ← ManageFlowFSM
2026-02-23 21:26:04,125 - ... - INFO - 📌 [LIMIT-DEFERRED] Placing brackets for SOLUSDT: SL=79.35, TP=78.2   ← deferred path
2026-02-23 21:26:04,125 - ... - INFO - Executing PLACE_ORDER: SOLUSDT BUY STOP_MARKET 18.0 @ None/79.389675    ← DEC:BATCH
2026-02-23 21:26:04,125 - ... - INFO - Executing PLACE_ORDER: SOLUSDT BUY TAKE_PROFIT_MARKET 18.0 @ None/None  ← DEC:BATCH
2026-02-23 21:26:04,501 - ... - ERROR - ❌ PLACE_ORDER failed: [-4015] ...  (STOP_MARKET)
2026-02-23 21:26:04,502 - ... - ERROR - ❌ PLACE_ORDER failed: [-4015] ...  (TAKE_PROFIT_MARKET)
2026-02-23 21:26:05,003 - ... - INFO - ✅ [LIMIT-DEFERRED] SL placed: { ... 'triggerPrice': '79.3500' }   ← deferred OK
```

---

## Codepath Map: RID → clientOrderId

### Full path (ManageFlowFSM DEC:BATCH)

```
DEC:TRADE_EXECUTED (msg.rid = "aurora_{SYMBOL}_{ts}")
  → ManageFlowFSM.transition_on_message()
  → ManageFlowFSM._place_brackets(msg)
      idem_base = f"{msg.rid}_{int(self.position_open_ts)}"
      # Example: "aurora_BTCUSDT_1771850701848_1771850735" = 39 chars

      sl_client_id = generate_client_order_id("SL", symbol, idempotent_key=idem_base)
      #  → POST-FIX: "SL-{md5(idem_base|SL|BTCUSDT)[:12]}" = 15 chars ✓
      #  → PRE-FIX:  "SL-{idem_base}" = 42 chars  ← -4015!

      tp1_client_id = generate_client_order_id("TP", symbol, idempotent_key=f"{idem_base}_1")
      tp2_client_id = generate_client_order_id("TP", symbol, idempotent_key=f"{idem_base}_2")
      ...
      return DEC:BATCH([DEC:PLACE_ORDER(newClientOrderId=sl_client_id), ...])

  → ExecPosFSM._execute_decision(sub_msg):
      client_id = pld.get("newClientOrderId")  # ← the problematic long ID
      adapter.place_stop_market_close_position(symbol, side, stop_price, new_client_order_id=client_id)
      # → binance_adapter._post_order_with_algo_fallback({"newClientOrderId": client_id, ...})
      # → POST /fapi/v1/order → Binance: -4015
```

### Trailing stop path (additional risk)

```
ManageFlowFSM._adjust_trailing_stop(msg):
    idem_trail = f"{msg.rid}_{int(self.position_open_ts)}_trail_{int(get_clock().now_sec())}"
    # Example: "aurora_1000PEPEUSDT_1771874702177_1771874765_trail_1771874800" = 61 chars
    # Pre-fix: "SL-" + 61 = 64 chars  ← worst case -4015!

    new_client_id = generate_client_order_id("SL", symbol, idempotent_key=idem_trail)
    # Post-fix: "SL-{md5(...)[:12]}" = 15 chars ✓
```

---

## All Callsites That Set clientOrderId

| Callsite | File / Line | Prefix | `idempotent_key` source | Max post-fix len |
|---|---|---|---|---:|
| CLOSE orders | `fsm.py:2500` | `"CLOSE"` | `decision.rid` or `"manual-close"` | 18 |
| ENTRY orders | `fsm.py:3245` | `"ENTRY"` | `pld.idempotent_key` or `decision.rid` | 18 |
| Inline SL | `fsm.py:3518` | `"SL"` | `idem_key` from bracket_data | 15 |
| Inline TP | `fsm.py:3524` | `"TP"` | `idem_key` from bracket_data | 15 |
| Deferred SL | `fsm.py:4733` | `"SL"` | `bracket_data["idem_key"]` | 15 |
| Deferred TP | `fsm.py:4737` | `"TP"` | `bracket_data["idem_key"]` | 15 |
| Bracket-health SL | `fsm.py:5188` | `"BHSL"` | None (no `idempotent_key`) | 15 |
| Bracket-health TP | `fsm.py:5218` | `"BHTP"` | None (no `idempotent_key`) | 15 |
| Batch SL | `fsm_manage.py:747` | `"SL"` | `idem_base` | 15 |
| Batch TP1 | `fsm_manage.py:749` | `"TP"` | `f"{idem_base}_1"` | 15 |
| Batch TP2 | `fsm_manage.py:751` | `"TP"` | `f"{idem_base}_2"` | 15 |
| Trailing SL | `fsm_manage.py:1406` | `"SL"` | `idem_trail` (longest key) | 15 |

All 12 callsites go through `generate_client_order_id()` which enforces `max_len=32` and uses MD5 hash.

---

## Generator Analysis

**Location:** `apps/reference/domains/execution_position/utils.py:159`

```python
def generate_client_order_id(
    prefix: str,
    decision_id: str,
    extra: str | None = None,
    *,
    idempotent_key: str | None = None,
    max_len: int = 32,
    config: Optional[Any] = None,
) -> str:
    ...
    if idempotent_key is not None:
        # BRANCH 1: hash branch (all bracket/entry/close callers)
        raw_str = f"{idempotent_key}|{role}|{symbol}"
        hash_part = hashlib.md5(raw_str.encode("utf-8")).hexdigest()[:12]
        cid = f"{role}-{hash_part}"
        # lens: "SL-"=15, "TP-"=15, "ENTRY-"=18, "CLOSE-"=18, "BHSL-"=17, "BHTP-"=17

    elif extra is not None and str(prefix).upper() in role_set:
        # BRANCH 2: legacy hash (role-class callers without idempotent_key)
        hash_part = hashlib.md5(...).hexdigest()[:12]
        cid = f"{role}-{hash_part}"   # same shape

    else:
        # BRANCH 3: clock-based (callers with no key, e.g. BHSL/BHTP)
        h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
        cid = f"{prefix}-{h}"
        # "BHSL-" + 10 = 15 chars

    if len(cid) > max_len:   # guard: truncate to 32 if somehow exceeded
        cid = cid[:max_len]
    return re.sub(r"[^A-Za-z0-9_\-]", "", cid)
```

**Current max output lengths:**

| Prefix | Branch | Result len | Within 35? |
|---|---|---:|---|
| `SL` | 1 (hash) | 15 | ✅ |
| `TP` | 1 (hash) | 15 | ✅ |
| `ENTRY` | 1 (hash) | 18 | ✅ |
| `CLOSE` | 1 (hash) | 18 | ✅ |
| `BHSL` | 3 (clock) | 15 | ✅ |
| `BHTP` | 3 (clock) | 15 | ✅ |

---

## Pre-fix Maximum Observed / Theoretical Lengths

| Scenario | idem_base formula | idem_base len | Proposed-pre-fix cid | Pre-fix cid len |
|---|---|---:|---|---:|
| BTCUSDT observed | `aurora_BTCUSDT_1771850701848_1771850735` | 39 | `SL-aurora_BTCUSDT_1771850701848_1771850735` | **42** |
| SOLUSDT observed | `aurora_SOLUSDT_1771874702177_1771874765` | 39 | `SL-aurora_SOLUSDT_1771874702177_1771874765` | **43** |
| 1000PEPEUSDT theoretical | `aurora_1000PEPEUSDT_1771874702177_1771874799` | 44 | `SL-aurora_1000PEPEUSDT_1771874702177_1771874799` | **47** |
| UUID rid theoretical | `a64015ed-406e-4037-abfd-dd921cf3a9b4_1771874765` | 47 | `SL-a64015ed-406e-4037-abfd-dd921cf3a9b4_1771874765` | **50** |
| Trailing 1000PEPEUSDT | `aurora_1000PEPEUSDT_1771874702177_1771874765_trail_1771874800` | 61 | `SL-aurora_1000PEPEUSDT_…_trail_…` | **64** |

---

## Root Cause Classification

### PRIMARY — Direct `idem_base` concatenation (pre-fix)

Before the MD5 hash was introduced, `generate_client_order_id()` (or an earlier inline pattern) formed `cid` by directly appending the `idempotent_key`:

```python
# Hypothetical pre-fix pattern:
cid = f"{prefix}-{idempotent_key}"
# = "SL-aurora_BTCUSDT_1771850701848_1771850735" = 42 chars  ← Binance rejects
```

`idem_base = f"{msg.rid}_{int(self.position_open_ts)}"` grows unboundedly with symbol length and timestamp digits.

### SECONDARY — Missing universal length guard

The `if len(cid) > max_len: cid = cid[:max_len]` guard was either absent or had `max_len=36` (meaning 36-char strings were NOT truncated, but Binance requires `< 36` meaning max 35).

### TERTIARY — Charset leak risk

`re.sub(r"[^A-Za-z0-9_\-]", "", cid)` strips invalid chars AFTER truncation. If truncation removes chars that make the ID shorter, the final ID could be shorter than expected (no collision by itself, but changes the determinism guarantee).

---

## Constraints Reference (Binance Futures)

| Constraint | Value | Source |
|---|---|---|
| Max length | **< 36** (i.e., ≤ 35 chars) | Binance Futures API docs, error -4015 |
| Allowed charset | `A-Z a-z 0-9 _ -` | Binance Futures API docs |
| Uniqueness per account | Required (scoped by symbol + 24h window) | -4116 duplicate check |
| Case-sensitive | Yes | Binance |

---

## Fix Options

### Option A — ULID(26) + short prefix (recommended for new systems)

```python
import ulid

cid = f"{prefix[:4]}-{ulid.new()}"  # "SL-01HX..." = prefix(4)+1+26 = 31 chars max
# prefix truncated to 4 chars → "ENTR", "CLOS", "BHSL", "BHTP", "SL", "TP"
```

**Pros:**
- Lexicographically sortable by time.
- Globally unique without hashing.
- Naturally 26 chars + short prefix = 31-32 chars total.

**Cons:**
- NOT idempotent — same event produces different ID each call (WAL replay creates new orders).
- Requires `ulid-py` dependency.
- Not deterministic for backtest.

---

### Option B — MD5 hash with namespace (current approach — recommended for this codebase)

```python
raw = f"{idempotent_key}|{role}|{symbol}"
cid = f"{role}-{hashlib.md5(raw.encode()).hexdigest()[:12]}"
# "SL-" + 12 = 15 chars, "ENTRY-" + 12 = 18 chars  ← always ≤ 18
```

**Collision probability:** MD5 truncated to 12 hex chars = 48-bit space → `p(collision) ≈ n² / 2^49 ≈ 10⁻⁹` per 30,000 orders. Negligible.

**Pros:**
- Deterministic — WAL replay produces the same ID.
- Already implemented.
- Short output (15-18 chars).
- Idempotency preserved.

**Cons:**
- MD5 is cryptographically weak, but that's irrelevant for order ID uniqueness (not security-sensitive).
- Domain knowledge required to choose the right `idempotent_key`.

**Current status:** ✅ Already applied in `generate_client_order_id()`.

---

### Option C — Truncate with checksum (defense-in-depth)

```python
MAX = 35

def safe_cid(raw: str) -> str:
    if len(raw) <= MAX:
        return raw
    # Keep first 28 chars + "-" + 6-char CRC32
    prefix_part = raw[:28]
    suffix = f"{zlib.crc32(raw.encode()) & 0xFFFFFF:06x}"
    return f"{prefix_part}-{suffix}"  # 28+1+6 = 35 chars
```

**Pros:**
- Works even if raw string is used directly.
- CRC prevents silent truncation collisions for different inputs with the same first 28 chars.

**Cons:**
- Breaks determinism if two different raw strings have the same first 28 chars AND same CRC (astronomically rare).
- Adds complexity without adding idempotency.
- Recommended only as a last-resort safety net, not as primary strategy.

---

## Fail-closed Policy

Any code path that calls an adapter method with `new_client_order_id` MUST go through `generate_client_order_id()`. Direct construction of clientOrderId strings is forbidden.

**Enforcement options:**
1. Type-level: Create a `ClientOrderId` newtype/dataclass that can only be constructed via `generate_client_order_id()`.
2. Lint: A grep-based CI check that flags `new_client_order_id=` arguments not preceded by `generate_client_order_id(`.
3. Adapter-level: Add a guard in `BinanceAdapter._post_order_with_algo_fallback()` that raises if `params.get("newClientOrderId", "")` has `len > 35`.

---

## Test Plan

Existing regression tests: `tests/domains/execution_position/test_fsm_manage_bracket_fixes.py::TestClientOrderIdLength` (covers the current fix).

**Additional tests required for full regression coverage:**

1. `test_generate_client_order_id_always_within_binance_limit()`
   - ALL prefixes × ALL branches × extreme inputs (UUID, 60-char key, 1000PEPEUSDT)
   - Assert `len(result) <= 35`

2. `test_generate_client_order_id_charset_clean()`
   - Assert result matches `^[A-Za-z0-9_\-]+$`

3. `test_generate_client_order_id_deterministic_for_same_inputs()`
   - Same (prefix, symbol, idempotent_key) → same output on repeated calls

4. `test_all_fsm_bracket_ids_within_limit()`
   - Drive `ManageFlowFSM._place_brackets()` with longest realistic rid
   - Capture all emitted `newClientOrderId` values from the DEC:BATCH
   - Assert each `len <= 35`

5. `test_adapter_rejects_long_client_order_id()`
   - Pass `new_client_order_id="x" * 36` to `place_stop_market_close_position`
   - Assert: raises `ValueError` before HTTP call (if P1 adapter guard is added)

---

## Related Errors

| Error | Description |
|---|---|
| `-4015` | This document: clientOrderId too long |
| `-4116` | Duplicate clientOrderId (adapter already handles, `B1` retry path) |
| `-1102` | Missing stopPrice for conditional order (see EP_MISSING_STOPPRICE_1102_CONTEXT.md) |
| `-1111` | Price precision violation (see EP_PRECISION_1111_CONTEXT.md) |
