# Data Contracts & Payload Map (Gap Analysis)

Mission: document the **exact JSON shapes** involved in the Strategy → DecisionMaking → Execution FSM pipeline and identify **where nested data is ignored/lost**.

Sources (SSOT):
- Contract (schema): `apps/reference/domains/decision_making/schemas/trade_intent_v1.json`
- Producer (DecisionMaking): `apps/reference/domains/decision_making/decision_making.py` (`_propose_trade_intent`)
- Consumer (ExecPosFSM): `apps/reference/domains/execution_position/fsm.py` (`_on_trade_intent_proposed`)
- Origin (MeanReversion): `apps/reference/domains/decision_making/mean_reversion_handler.py` (`_emit_signal`)

> Note: `apps/reference/domains/decision_making/schemas.py` does **not** currently define a `TradeIntentPayload` model; the trade-intent contract is the JSON schema file above.

---

## Section 1: The Event Payload (`EVT:TRADE_INTENT_PROPOSED`)

### 1.1 Origin payload (MeanReversion emits `EVT:STRATEGY_SIGNAL_PRODUCED`)

This is where nested `price_ctx` is **actually produced**:

```json
{
  "schema_version": 1,
  "strategy_id": "mean_reversion",
  "symbol": "BTCUSDT",
  "tf_sec": 60,
  "side": "BUY",
  "readiness": { "warmup_ok": true },
  "score": 0.73,
  "why": "MR: pct_b<0 + regime=RANGE",
  "ts_ms": 1730000000000,
  "rid": "9b1c7f3a-5a5d-4c4a-9d9a-111111111111",
  "why_chain": ["MR: pct_b<0 + regime=RANGE"],
  "price_ctx": {
    "entry_price": "42123.4",
    "stop_price": "41750.0",
    "target_price": "42900.0"
  },
  "regime": "RANGE",
  "volatility": { "atr": "123.45" },
  "liquidity": { "kappa": "0.87" },
  "mr_params": { "sizing_mult": 1.0, "stop_mult": 1.0, "target_mult": 1.0 }
}
```

### 1.2 Produced payload (DecisionMaking emits `EVT:TRADE_INTENT_PROPOSED`)

DecisionMaking **does not forward** `price_ctx`. It flattens bracket prices to top-level `stop_price` / `target_price` and nests execution fields under `order`.

```json
{
  "rid": "9b1c7f3a-5a5d-4c4a-9d9a-111111111111",
  "instrument": "BTCUSDT",
  "side": "BUY",
  "strategy": "mean_reversion",
  "order": {
    "qty": "0.012",
    "price": "42123.4",
    "price_ref": "42123.4",
    "reduce_only": false,
    "order_type": "LIMIT",
    "tif": "GTX"
  },
  "p": "0.75",
  "payoff_ratio_r": "2.0",
  "tca_budget": {
    "max_slippage_bps": "12",
    "max_latency_ms": 250,
    "maker_preference": "prefer"
  },
  "risk_context": { "risk_score": 0.35 },
  "risk_budget": {
    "trade_cvar95_max_bps": "18",
    "session_cvar95_max_bps": "35"
  },
  "size": { "notional_cap_usd": "505.48", "kelly_fraction": "0.1" },
  "valid_for_ms": 60000,
  "why": ["MR: pct_b<0 + regime=RANGE", "entry_plan:sl=41750,tp=42900"],
  "dto_version": "1.0.0",
  "schema_ref": "trade_intent_v1.json",
  "idempotent_key": "22222222-2222-2222-2222-222222222222",
  "stop_price": "41750.0",
  "target_price": "42900.0",
  "entry_plan": {
    "ref_price": "42123.4",
    "atr": "123.45",
    "obi": null,
    "obi_multiplier": 1.0,
    "obi_policy_applied": false,
    "strategy_sl_used": true,
    "strategy_tp_used": true
  }
}
```

**Nested objects actually present in `EVT:TRADE_INTENT_PROPOSED` (producer reality):**
- `order` (qty/price/type/tif/reduce_only)
- `tca_budget` (slippage/latency/maker_preference)
- `risk_budget`
- `size`
- `entry_plan` (optional trace)
- `risk_context` (present in producer and consumer code; **not present** in `trade_intent_v1.json` → schema drift)

**Not present in `EVT:TRADE_INTENT_PROPOSED`:**
- `price_ctx` (exists in `EVT:STRATEGY_SIGNAL_PRODUCED`, not forwarded)
- `tca_ctx`, `features_ctx` (not present in current SSOT payloads)

---

## Section 2: The Consumer Gap (Forensics Table)

ExecPosFSM consumes `EVT:TRADE_INTENT_PROPOSED` and extracts fields mostly from:
- `pld["instrument"]` (symbol) and `pld["order"]` (qty/price/type/tif)
- **top-level** `pld["stop_price"]` / `pld["target_price"]`

It does **not** read `pld["price_ctx"][...]` at all.

| Field | Producer Path (Strategy) | Consumer Path (FSM) | Status |
| :--- | :--- | :--- | :--- |
| **Symbol** | `pld.symbol` | `pld.get("instrument") or pld.get("symbol")` | ✅ **OK** |
| **Side** | `pld.side` | `pld.get("side")` | ✅ **OK** |
| **Entry Price** | `pld.price_ctx.entry_price` | `pld.get("order", {}).get("price")` | ❌ **BROKEN / IGNORED** *(if strategy payload is passed through without DM normalization)* |
| **Stop Price** | `pld.price_ctx.stop_price` | `pld.get("stop_price")` | ❌ **BROKEN / IGNORED** |
| **Target Price** | `pld.price_ctx.target_price` | `pld.get("target_price")` | ❌ **BROKEN / IGNORED** |
| **Quantity** | *(not in MR signal; computed in DM)* | `pld.get("order", {}).get("qty")` | ✅ **OK** *(only when DM produced the intent)* |
| **Order Type** | *(not in MR signal; resolved in DM)* | `pld.get("order", {}).get("order_type")` | ✅ **OK** *(strict; missing → reject)* |
| **Time In Force** | *(not in MR signal; resolved in DM)* | `pld.get("order", {}).get("tif")` | ✅ **OK** *(LIMIT requires it)* |
| **Max Slippage (bps)** | `pld.tca_budget.max_slippage_bps` *(from DM)* | `pld.get("tca_budget", {}).get("max_slippage_bps")` *(logged only)* | ❌ **LOST** *(not forwarded into `CMD:OPEN`)* |
| **Max Latency (ms)** | `pld.tca_budget.max_latency_ms` *(from DM)* | *(Not read)* | ❌ **LOST** |
| **Maker Preference** | `pld.tca_budget.maker_preference` *(from DM)* | *(Not read)* | ❌ **LOST** |
| **Risk Score** | `pld.risk_context.risk_score` *(from DM)* | `pld.get("risk_context", {}).get("risk_score")` *(logged only)* | ❌ **LOST** *(not forwarded into `CMD:OPEN`)* |
| **Strategy ID** | `pld.strategy_id` | *(Not read)* | ❌ **LOST** |

---

## Section 3: Engineer's Conclusion

1) **Why nested prices “disappear”**  
MeanReversion provides bracket prices under `price_ctx` in `EVT:STRATEGY_SIGNAL_PRODUCED`. ExecPosFSM’s intent handler does **not** look inside `price_ctx`; it only checks top-level `stop_price` / `target_price` when building `CMD:OPEN` (`apps/reference/domains/execution_position/fsm.py`).

2) **Why the FSM falls back to default bracket calculations**  
If `CMD:OPEN` contains `stop_price=None` / `target_price=None`, the open flow falls back to config-driven SL/TP (e.g., `strategies.aurora.assets.<SYM>.exit.sl_pct`, `take_profit.tp_low_ratio`) (`apps/reference/domains/execution_position/fsm.py`).

3) **Secondary loss: TCA/Risk context is not carried into execution**  
Although ExecPosFSM logs `tca_budget.max_slippage_bps` and `risk_context.risk_score`, it does not include them in `CMD:OPEN`. Downstream execution therefore cannot enforce strategy/risk-engine-specific TCA constraints.

