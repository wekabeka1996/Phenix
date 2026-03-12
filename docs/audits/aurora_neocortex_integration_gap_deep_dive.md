# Aurora ↔ Neocortex Integration Gap Deep Dive

**Package:** NEO-PRODUCER-CONTRACT-ALIGNMENT-AUDIT-AND-IMPLEMENTATION-PLAN
**Date:** 2026-03-12
**Status:** AUDIT ONLY
**Branch:** Phenix_v2

---

## Purpose

This document maps the exact data lineage from Aurora's producer surface to
neocortex's consumer contracts. For each hard blocker it traces:
- The current implementation path (what actually happens)
- The required contract (what neocortex expects after P1–P9)
- The exact gap (field vs field, file vs file)
- Why neocortex cannot trust the current surface

---

## Current Implementation Map — Aurora Producer Surface

### Event / Log Surface Overview

Aurora produces 4 log streams and the WAL that neocortex can consume:

| Stream | Format | Producer | Location |
|---|---|---|---|
| `order_log_v1.jsonl` | JSONL | OrderLoggerV1 | `logs/order_log_v1.jsonl` |
| `aurora_core.log` | Python LOG.info text | logging module | `logs/aurora_core.log` |
| `trade_lifecycle.jsonl` | JSONL | TradeLifecycleLogger | `logs/trade_lifecycle.jsonl` |
| `ops/wal/YYYY-MM-DD.jsonl` | JSONL | vfoundation/dr/wal.py | `ops/wal/*.jsonl` |

### order_log_v1.jsonl — Current Schema by Event Type

#### ORDER_INTENT entry (written by `intent_builder.py:357-364`)
```json
{
  "timestamp": 1741800000000,
  "rid": "<decision-uuid>",
  "event_type": "ORDER_INTENT",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": 0.001,
  "price": 85000.0,
  "source_fsm": "DecisionMaking",
  "regime": "TREND_UP",
  "regime_confidence": 0.82,
  "metadata": {
    "intent_proposed": true,
    "idempotent_key": "<uuid4>",
    "normalize_mode_effective": "signed_v2"
  }
}
```
**Missing for neocortex:** `lifecycle_id`, top-level `idempotent_key`

#### ORDER_PLACED entry (written by `open_executor.py:431-438`)
```json
{
  "timestamp": ...,
  "rid": "<decision-uuid>",
  "event_type": "ORDER_PLACED",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": 0.001,
  "client_order_id": "ENTRY-BTCUSDT-abc123",
  "order_id": "123456789",
  "source_fsm": "ExecPosFSM",
  "regime": "TREND_UP",
  "metadata": {"order_type": "MARKET_ENTRY", "corr_id": "..."}
}
```
**Missing for neocortex:** `lifecycle_id`

#### ORDER_FILLED entry (written by `event_handlers.py:401-433`)
```json
{
  "timestamp": ...,
  "rid": "ENTRY-BTCUSDT-abc123",
  "event_type": "ORDER_FILLED",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "quantity": 0.001,
  "price": 84990.0,
  "source_fsm": "ExecPosFSM",
  "reservation_id": "...",
  "order_kind": "ENTRY",
  "metadata": {
    "fill_trade_id": "987654321",
    "realized_pnl": 0.0,
    "commission": 0.084990,
    "commissionAsset": "USDT"
  }
}
```
**Present:** `fill_trade_id` (in metadata), `commission`
**Missing for neocortex:** `lifecycle_id`, top-level `trade_id`
**Note:** `rid` here is `clientOrderId`, NOT the intent UUID from ORDER_INTENT

#### POSITION_CLOSED entry (written by `event_handlers.py:245-261`)
```json
{
  "timestamp": ...,
  "rid": "ENTRY-BTCUSDT-abc123",
  "event_type": "POSITION_CLOSED",
  "symbol": "BTCUSDT",
  "side": "N/A",
  "source_fsm": "ExecPosFSM",
  "why": "SL",
  "close_reason": "SL",
  "metadata": {
    "close_price": 84500.0,
    "realized_pnl": -0.49
  }
}
```
**Missing for neocortex:** `lifecycle_id`, `trade_id`, `fees`, `net_pnl`,
correct `side`, `entry_price`, `close_ts_ms`

---

## Neocortex Required Consumer Contract (Post P1–P9)

### what `order_parser.py` reads from order_log_v1.jsonl

```python
# order_parser.py:135-161
OrderLogEntry(
    event_ts_ms=...,
    event_type=OrderEventType.POSITION_CLOSED,
    symbol=data["symbol"],
    side=data["side"],                        # gets "N/A" today
    quantity=data.get("quantity"),
    price=data.get("price"),
    lifecycle_id=data.get("lifecycle_id"),    # ALWAYS None today
    trade_id=(
        data.get("trade_id")                  # None for POSITION_CLOSED
        or metadata.get("fill_trade_id")      # None for POSITION_CLOSED
    ),
    order_id=data.get("order_id"),
    client_order_id=data.get("client_order_id"),
    legacy_rid=data.get("rid"),               # gets fill-level clientOrderId
    ...
)
```

### What DatasetSampleProvenance requires

```python
# datasets/contracts.py
class DatasetSampleProvenance(BaseModel):
    lifecycle_id: Optional[str] = None      # for execution_quality source_ref
    trade_id: Optional[str] = None          # canonical close identity
    event_ts_ms: int                        # canonical timestamp
```

### What the adapter's execution_quality path requires

```python
# transport/adapter.py:935-940
reward_complete = raw.get("reward_complete")
if reward_complete is None and isinstance(episode_reward, dict):
    reward_complete = bool(episode_reward.get("reward_complete", False))
if reward_complete is None:
    reward_complete = reward is not None and episode_reward is None
reward_missing = reward is None or not bool(reward_complete)
```

For `reward_complete=True`:
- `reward` must be non-None (requires `net_pnl` or structured `realized_pnl`)
- `episode_reward.reward_complete=True` if coming from structured close feed

---

## Data Lineage — Field by Field

### `lifecycle_id` Lineage

```
INTENT_BUILD TIME
  intent_builder.py:255
    idempotent_key = str(uuid.uuid4())   ← born here
    trade_intent["idempotent_key"] = idempotent_key

  intent_builder.py:357-364
    ORDER_INTENT log: metadata.idempotent_key = idempotent_key
    ┗━ lifecycle_id NOT emitted at top level

FILL TIME
  event_handlers.py:352-388
    rid = payload.get("rid") or event.rid  ← DIFFERENT from intent rid
    _last_lifecycle_rid_by_symbol[symbol] = rid  ← fill-level clientOrderId
    ORDER_FILLED log: no lifecycle_id field
    ┗━ intent idempotent_key NOT carried here

CLOSE DETECTION TIME
  event_handlers.py:219-225
    rid_for_sym = _last_lifecycle_rid_by_symbol.get(sym)  ← fill-level rid
    POSITION_CLOSED log: no lifecycle_id field
    ┗━ original intent identity completely lost

NEOCORTEX PARSER
  order_parser.py:143
    lifecycle_id = data.get("lifecycle_id")  ← ALWAYS None
```

### `trade_id` Lineage

```
FILL TIME (received from Binance)
  event_handlers.py:426-430
    metadata["fill_trade_id"] = str(payload.get("tradeId", ""))
    ┗━ present in ORDER_FILLED metadata.fill_trade_id ✓

POSITION_CLOSED WRITE
  event_handlers.py:246-261
    NO cache lookup for tradeId
    POSITION_CLOSED: no trade_id field ✗

NEOCORTEX PARSER
  order_parser.py:144-148
    trade_id = data.get("trade_id")            ← None for POSITION_CLOSED
            or metadata.get("fill_trade_id")   ← None for POSITION_CLOSED
```

**Bridge opportunity:** ORDER_FILLED's `legacy_rid` (clientOrderId) could link
back to the ORDER_PLACED entry, which links to the exchange `orderId`. But
Binance's `tradeId` is a different identifier than `orderId`.

### `fees` Lineage

```
FILL TIME (received from Binance)
  event_handlers.py:392-399
    trade_lifecycle.on_fill(fees=commission)   ← TradeLifecycleLogger receives it ✓
  event_handlers.py:428-430
    ORDER_FILLED metadata.commission = payload.get("commission")   ← logged ✓

ACCUMULATION
  No per-symbol fee accumulator exists in ExecPosFSM               ✗
  _last_realized_pnl_by_symbol: only last fill's realizedPnl

CLOSE DETECTION TIME
  event_handlers.py:246-261
    POSITION_CLOSED metadata: {"close_price": ..., "realized_pnl": ...}
    NO fees field                                                   ✗
    NO net_pnl field                                                ✗

TRADE LIFECYCLE LOGGER
  trade_lifecycle_logger.py:54-97
    TradeRecord.fill_fees = fees from on_fill()   ← stored in memory ✓
    on_close() does NOT compute pnl_usdt from fill_fees             ✗
    _flush() writes record with fill_fees populated, but:
    - no net_pnl computed
    - neocortex doesn't read this file
```

### `realized_pnl_net` / `net_pnl` Lineage

```
NOWHERE IN THE CODEBASE is net_pnl = realized_pnl - fees computed.
The closest is:
  - TradeRecord.pnl_usdt (passed to on_close() from caller)
  - But caller (event_handlers.py:231-235) doesn't compute or pass it
```

### `reward_complete` Determination in Neocortex

```python
# Current execution path for a POSITION_CLOSED episode:

# Step 1: order_parser.py parses POSITION_CLOSED → OrderLogEntry
#   lifecycle_id = None
#   trade_id = None
#   fees = None
#   net_pnl = None

# Step 2: neocortex adapter builds episode from ingest
#   episode.reward = None (no structured reward)
#   episode.reward_complete = False

# Step 3: transport/adapter.py:940
#   reward_missing = reward is None or not reward_complete
#   reward_missing = True  ← ALWAYS TRUE

# Step 4: adapter alerts
#   "NO_STRUCTURED_REWARD_RECEIVED" WARN emitted for every close
#   execution_quality sample marked diagnostics_only or quarantined
```

---

## Why Neocortex Cannot Trust the Current Producer Surface

### Reason 1: Non-Deterministic Episode Identity

Without `lifecycle_id`, neocortex must match close events to open events using:
- Symbol + approximate timestamp
- `legacy_rid` (fill-level clientOrderId) — only available in ORDER_FILLED,
  not in POSITION_CLOSED

If two BTCUSDT positions are opened within the same second (possible but rare),
or if system restarts and timestamps conflict, episode matching fails silently.
Neocortex's fail-closed rule (P2: "ambiguous close mapping fails closed") means
such episodes are marked `unresolved` and excluded from training.

### Reason 2: Reward Always Missing

`reward_complete=True` requires structured `net_pnl`. Since `fees` and
`net_pnl` are never emitted, every close triggers `reward_missing=True`,
and the execution_quality dataset accumulates only `diagnostics_only` entries.

The adapter emits `NO_STRUCTURED_REWARD_RECEIVED` for every trade.

### Reason 3: Regex Path Cannot Substitute

The `core_parser.py` regex path extracts at most `symbol` + `realized_pnl`
from the core log. In practice, `realized_pnl={pos_pnl}` in the LOG.info
message may extract a value, but:
- `realized_pnl_net` (net of fees) is never in any log line
- `trade_id` is never in any log line
- Even if `realized_pnl` is extracted, `fees=None` → `net_pnl` cannot be computed
- `reward_complete` remains False

### Reason 4: Side "N/A" Corrupts Directional Analysis

POSITION_CLOSED `"side": "N/A"` means neocortex cannot:
- Determine which direction the trade was
- Compute directional execution quality metrics
- Route samples to correct regime↔side histograms

### Reason 5: `trade_lifecycle.jsonl` is an Orphaned SSOT

`TradeLifecycleLogger` accumulates the richest structured record, but nothing
reads it. It is a correct, complete, structured JSONL file that neocortex
doesn't consume. This is the largest unused asset in the system.

---

## Full Field Gap Matrix

| Field | ORDER_INTENT | ORDER_FILLED | POSITION_CLOSED | Required By |
|---|---|---|---|---|
| `timestamp` / `event_ts_ms` | ✓ | ✓ | ✓ | P1 time contract |
| `symbol` | ✓ | ✓ | ✓ | All contracts |
| `side` | ✓ | ✓ | ✗ ("N/A") | P2 episode identity |
| `quantity` | ✓ | ✓ | ✗ | P2 episode identity |
| `price` / `close_price` | ✓ | ✓ | ✓ (fill cache) | P3 reward |
| `lifecycle_id` | ✗ | ✗ | ✗ | P2 CRITICAL |
| `trade_id` | N/A | via metadata only | ✗ | P2 CRITICAL |
| `fees` | N/A | via metadata only | ✗ | P3 CRITICAL |
| `net_pnl` | N/A | N/A | ✗ | P3 CRITICAL |
| `realized_pnl` | N/A | ✓ (fill only) | ✓ (partial) | P3 partial |
| `realized_pnl_net` | N/A | N/A | ✗ | P3 CRITICAL |
| `close_ts_ms` | N/A | N/A | ✗ (wallclock only) | P1/P3 |
| `entry_price` | ✓ intent | ✓ fill | ✗ | P3 |
| `regime` | ✓ | ✗ | ✓ (via open_regime) | P4 objective split |
| `strategy_id` | ✓ | partial | ✗ | P6 provenance |
| `close_reason` | N/A | N/A | ✓ | Evaluator |

**✓** = field present | **✗** = field absent | **N/A** = not applicable at stage

---

## Impact on Neocortex Objective Families

### representation (VAE/world model)
- **Impact:** NONE from HB-1 to HB-4
- Features-based only (`EVT:FEATURES_CALCULATED`)
- Can proceed now in offline replay

### regime_supervision (PPO head / oracle label)
- **Impact:** MINOR from HB-1 to HB-4
- Samples come from regime events, not from trade closes
- Can proceed now in offline replay

### execution_quality (diagnostic / evaluator)
- **Impact:** CRITICAL from HB-1 to HB-4
- All samples have `reward_complete=False`
- Episodes have `lifecycle_id=None`, `trade_id=None`
- Sample matching is heuristic and unreliable
- **Completely blocked without PKG-1 to PKG-4**

### policy (PPO action learning)
- **Impact:** N/A currently
- Policy training is disabled by design (P4 objective split gate)
- Will be blocked even after execution_quality unblocked until P9 gates pass

---

## Structured vs Regex Path Decision Tree (Current vs Desired)

### Current (broken):
```
Aurora LOG.info("[POSITION_CLOSED] BTCUSDT: ...realized_pnl=0.0")
  ↓
core_parser.py line contains "POSITION_CLOSED"?  YES
  ↓
any structured field present?
  → realized_pnl=0.0 maybe extracted (via kv regex)
  → realized_pnl_net: MISSING
  → trade_id: MISSING
  → fees: MISSING
  ↓
CoreLogEntry(symbol=BTCUSDT, realized_pnl=0.0, everything_else=None)
  ↓
neocortex: reward=0.0, reward_complete=False, trade_id=None
```

### Desired (after PKG-1 to PKG-4):
```
Aurora order_logger.write({
    "event_type": "POSITION_CLOSED",
    "lifecycle_id": "<same as ORDER_INTENT>",
    "trade_id": "<Binance tradeId>",
    "fees": 0.085,
    "net_pnl": -0.575,
    "realized_pnl": -0.49,
    "side": "BUY",
    ...
})
  ↓
order_parser.py:
  lifecycle_id="<uuid>"  ✓
  trade_id="987654321"   ✓
  fees=0.085             ✓ (via metadata)
  net_pnl=-0.575         ✓ (via metadata)
  reward_complete=True   ✓
  ↓
neocortex: reward=-0.575, reward_complete=True, lifecycle_id established
```

---

## `trade_lifecycle.jsonl` Asset Analysis

The `TradeLifecycleLogger` at `apps/reference/telemetry/trade_lifecycle_logger.py`
already produces a complete per-trade record:

```python
@dataclass
class TradeRecord:
    rid: str
    symbol: str
    strategy_id: str
    side: str          # LONG / SHORT — CORRECT
    regime: str
    entry_type: str
    intent_ts_ms: int
    order_id: str
    fill_price: float
    fill_qty: float
    fill_fees: float   # FEE ACCUMULATION — correct
    sl_price: float
    tp_price: float
    close_price: float
    close_reason: str
    close_ts_ms: int
    pnl_pct: float
    pnl_usdt: float    # NET PNL — but only if caller provides it
    status: str
```

**What it has:** `side`, `fill_fees`, `close_price`, `close_ts`, `strategy_id`
**What it's missing:** `lifecycle_id` (currently uses `rid`), `trade_id` (Binance tradeId)
**What neocortex needs to use it:** a dedicated lifecycle parser pointed to this file

**Why it's not yet wired as primary:**
1. Neocortex ingest is configured for `order_log_v1.jsonl` + `aurora_core.log`
2. `TradeRecord` schema differs from `OrderLogEntry` — needs a separate parser
3. `pnl_usdt` is only populated if the caller computes it — currently `on_close()`
   is called without `pnl_usdt` from `event_handlers.py:231-235`
4. No `trade_id` (Binance `tradeId`) field in `TradeRecord`

**Minimum changes to make it usable as structured source:**
- Add `trade_id: str = ""` to `TradeRecord`
- Add `net_pnl: float = None` or use `pnl_usdt` consistently
- Wire `tradeId` cache → `trade_lifecycle.on_fill(trade_id=...)`
- Compute `net_pnl` in `_flush()` or in `on_close()`
- Add neocortex config entry: `ingest.lifecycle_log_path`
- Add `lifecycle_parser.py` to `neocortex/logic/ingest/parsers/`

This is Option B from HB-3/HB-4 alternatives — valid long-term architecture.

---

## Summary: Why the Gap Is Narrow but Consequential

The gap is architecturally narrow (5–8 fields across 2 files), but each
missing field blocks a category of neocortex learning entirely:

| Missing field | Blocked neocortex capability |
|---|---|
| `lifecycle_id` | Episode provenance, deduplication, comparison corpus |
| `trade_id` | Canonical close matching, partial fill attribution |
| `fees` | Reward completeness, net PnL accuracy |
| `net_pnl` | Reward truth for execution quality PPO |
| correct `side` | Directional execution quality analysis |

The producer side has 95% of the needed data in memory and in fill events.
The final 5% requires small, additive, fail-safe changes to:
- `ExecPosFSM.__init__` — add 2–3 per-symbol caches
- `event_handlers.py:on_order_fill` — cache `tradeId` and accumulate `commission`
- `event_handlers.py:POSITION_CLOSED write` — add cached fields to dict
- `intent_builder.py:ORDER_INTENT log` — add `lifecycle_id = idempotent_key`
