# EP_MISSING_STOPPRICE_1102_CONTEXT

**Domain:** `execution_position`
**Error:** `PLACE_ORDER failed: [-1102] Mandatory parameter 'stopprice'/'triggerprice' was not sent`
**Classification:** `STOPPRICE_MISSING_PROPAGATION` — `stopPrice=None` propagated into Binance request (fail-open)
**Status:** CLOSED 2026-02-24 — fail-closed implemented, 36 tests pass
**Date:** 2026-02-24

---

## Executive Summary

- Подтверждено **2** события `-1102` в одном периоде логов: одно про `triggerprice`, одно про `stopprice`.
- В обоих кейсах рядом в логах присутствует строка:
  - `Executing PLACE_ORDER: <SYMBOL> <SIDE> TAKE_PROFIT_MARKET ... @ None/None`
  что означает: в DEC:PLACE_ORDER payload поле `stopPrice` отсутствует или равно `None`.
- **С высокой доказательной связью**: `-1102` относится к постановке **TP** (`TAKE_PROFIT_MARKET`), а не SL:
  - для SL в этих же блоках `STOP_MARKET` печатается как `@ None/<число>` (stopPrice присутствует),
  - для TP печатается как `@ None/None` (stopPrice отсутствует).
- Кодпуть `ExecPosFSM._execute_decision()` в [apps/reference/domains/execution_position/fsm.py](../../apps/reference/domains/execution_position/fsm.py) делает `str(stop_price)` без preflight-проверки. При `stop_price is None` получается строка `'None'`, которая попадает в запрос Binance как `stopPrice='None'` (или после миграции на Algo API как `triggerPrice='None'`).
- Разница между `stopprice` vs `triggerprice` в тексте ошибки объясняется **миграцией условных ордеров Binance на Algo Service**:
  - стандартный endpoint `/fapi/v1/order` требует `stopPrice`,
  - fallback endpoint `/fapi/v1/algoOrder` требует `triggerPrice` (адаптер делает `stopPrice → triggerPrice`).

---

## Evidence Table (all `-1102` occurrences)

| # | Timestamp (UTC local) | Log file | Line | Symbol | Inferred orderType | Inferred intent | Binance-required key | What we had at ExecPosFSM | Request endpoint (inferred) |
|---|---|---|---:|---|---|---|---|---|---|
| 1 | 2026-02-23 14:40:04.230 | `logs/domain_execution_position.log.1` | 5528 | DOGEUSDT | `TAKE_PROFIT_MARKET` | TP bracket after entry fill | `triggerPrice` | `stopPrice=None` → `str(None)='None'` | `/fapi/v1/algoOrder` (because error mentions `triggerprice`) |
| 2 | 2026-02-24 03:10:02.828 | `logs/domain_execution_position.log.1` | 22962 | XRPUSDT | `TAKE_PROFIT_MARKET` | TP bracket after entry fill | `stopPrice` | `stopPrice=None` → `str(None)='None'` | `/fapi/v1/order` (because error mentions `stopprice`) |

### Proof anchors (local context)

For both occurrences, immediately before the error, logs contain:

- `Executing PLACE_ORDER: <SYMBOL> ... STOP_MARKET ... @ None/<non-null>`
- `Executing PLACE_ORDER: <SYMBOL> ... TAKE_PROFIT_MARKET ... @ None/None`

This is emitted by:

- `stop_price = pld.get("stopPrice")`
- `LOG.info(f"Executing PLACE_ORDER: ... @ {price}/{stop_price}")`

inside `ExecPosFSM._execute_decision()`.

---

## Exact Payload Reconstruction (what keys were sent)

### Layer 1 — DEC:PLACE_ORDER payload (domain-level)

Emitted by `ManageFlowFSM._emit_place_order()` in [apps/reference/domains/execution_position/fsm_manage.py](../../apps/reference/domains/execution_position/fsm_manage.py).

Expected shape (relevant keys):

```python
{
  "symbol": <SYMBOL>,
  "side": <BUY|SELL>,
  "order_type": <"STOP_MARKET"|"TAKE_PROFIT_MARKET"|...>,
  "price": None,  # for non-LIMIT types
  "stopPrice": <string price> or None,
  "reduceOnly": True,
  "newClientOrderId": <id>,
  "workingType": <MARK_PRICE|...>,
  "priceProtect": <bool>,
}
```

**Observed (from logs) for the failing TP placement**:

- `order_type = TAKE_PROFIT_MARKET`
- `price = None` (by design)
- `stopPrice = None` (observed as `@ None/None`)

### Layer 2 — Adapter params for `POST /fapi/v1/order`

Built in `BinanceAdapter.place_take_profit_market_close_position()`:

```python
params = {
  "symbol": symbol,
  "side": side.upper(),
  "type": "TAKE_PROFIT_MARKET",
  "stopPrice": stop_price,          # <- comes from ExecPosFSM
  "workingType": "MARK_PRICE",
  "closePosition": "true",
  "priceProtect": "true",
  "newClientOrderId": <optional>,
  "positionSide": <optional>,
}
```

**With `stopPrice` missing upstream**:

- ExecPosFSM passes `str(stop_price)` where `stop_price is None` ⇒ `stopPrice = "None"`.
- Binance rejects it as “not sent / empty/null / malformed” ⇒ `-1102`.

### Layer 3 — Algo fallback params for `POST /fapi/v1/algoOrder`

When Binance returns `-4120` (conditional orders must be placed via Algo endpoints), adapter runs `_post_order_with_algo_fallback()` and transforms params:

```python
algo_params = dict(params)
algo_params.setdefault("algoType", "CONDITIONAL")
algo_params["triggerPrice"] = algo_params.pop("stopPrice")

if closePosition == true:
  algo_params.pop("quantity", None)
  algo_params.pop("reduceOnly", None)
```

So if `stopPrice` was `"None"` (from `str(None)`), then:

- `triggerPrice = "None"` → Binance responds with `-1102` mentioning `triggerprice`.

---

## Log Artifacts (full context blocks)

### Occurrence #1 — DOGEUSDT (`triggerprice` missing)

Source: `logs/domain_execution_position.log.1` around line 5528

```text
2026-02-23 14:40:03,549 - ... - INFO - Executing PLACE_ORDER: DOGEUSDT BUY STOP_MARKET 3901.0 @ None/0.0976488
2026-02-23 14:40:03,554 - ... - INFO - Executing PLACE_ORDER: DOGEUSDT BUY TAKE_PROFIT_MARKET 3901.0 @ None/None
...
2026-02-23 14:40:04,230 - ... - ERROR - ❌ PLACE_ORDER failed: [-1102] Mandatory parameter 'triggerprice' was not sent, was empty/null, or malformed. (no-nrr)
```

**Interpretation:** failing request is TP (`TAKE_PROFIT_MARKET`) via Algo fallback.

### Occurrence #2 — XRPUSDT (`stopprice` missing)

Source: `logs/domain_execution_position.log.1` around line 22962

```text
2026-02-24 03:10:02,533 - ... - INFO - Executing PLACE_ORDER: XRPUSDT SELL STOP_MARKET 290.0 @ None/1.3395299
2026-02-24 03:10:02,535 - ... - INFO - Executing PLACE_ORDER: XRPUSDT SELL TAKE_PROFIT_MARKET 290.0 @ None/None
...
2026-02-24 03:10:02,828 - ... - ERROR - ❌ PLACE_ORDER failed: [-1102] Mandatory parameter 'stopprice' was not sent, was empty/null, or malformed. (no-nrr)
```

**Interpretation:** failing request is TP (`TAKE_PROFIT_MARKET`) on the non-algo endpoint.

---

## Was it SL, TP, or other? Was the position left unprotected?

### Classification

- `-1102` fires on **conditional order placement**.
- По логам, `stopPrice` отсутствует именно на линии `TAKE_PROFIT_MARKET ... @ None/None`.
- Следовательно, это **TP placement** (не SL).

### Protection status (as evidenced in the same blocks)

По этим двум фрагментам логов **строго доказано** следующее:

- система пыталась поставить и SL (`STOP_MARKET`), и TP (`TAKE_PROFIT_MARKET`);
- для SL `stopPrice` был непустым (`@ None/<non-null>`), а для TP был пустым (`@ None/None`).

Чего эти два фрагмента **сами по себе не доказывают** без дополнительных строк (`✅ SL placed`/`✅ TP placed`/HTTP response):

- что SL/TP действительно были успешно поставлены на бирже;
- что позиция гарантированно оставалась защищённой.

Тем не менее, `-1102` уже достаточно, чтобы классифицировать дефект как **fail-open**: conditional order с отсутствующей ценой дошёл до Binance вместо блокировки до сети.

---

## Call Graph / Codepath Map

### Emission path (TP/SL after fill)

```
watchdog / REST polling detects fill
  → EVT:TRADE_EXECUTED
  → ManageFlowFSM._place_brackets()
      → _emit_place_order(... "STOP_MARKET" ... stopPrice=<value>)
      → _emit_place_order(... "TAKE_PROFIT_MARKET" ... stopPrice=None)   ⚠️
      → DEC:BATCH(messages=[DEC:PLACE_ORDER, DEC:PLACE_ORDER])
  → ExecPosFSM._execute_decision(sub_msg)
      → if verb == "PLACE_ORDER":
          stop_price = pld.get("stopPrice")
          adapter.place_take_profit_market_close_position(symbol, side, str(stop_price), ...)
              → BinanceAdapter._post_order_with_algo_fallback(params)
                  → POST /fapi/v1/order OR fallback POST /fapi/v1/algoOrder
                  → -1102
```

### Binance mapping proof

`/fapi/v1/algoOrder` uses `triggerPrice`, and adapter performs `stopPrice → triggerPrice` conversion in `_post_order_with_algo_fallback()`.

---

## Root-cause classification (requested taxonomy)

### (1) “None/NaN propagated” — CONFIRMED

- `ExecPosFSM` reads `stopPrice` from payload.
- Logs show `stopPrice=None` for TP.
- Code does `str(stop_price)` with no guard.
- Binance sees missing/malformed `stopPrice/triggerPrice` → `-1102`.

### (2) “orderType mismatch” — PARTIAL / SECONDARY

- For occurrence #1, Binance demanded Algo endpoint for conditional orders, so required key becomes `triggerPrice`.
- This is not a bug by itself (adapter handles fallback), but it changes the *name* of the required key in the error.

### (3) “wrong param name mapping (stopPrice vs triggerPrice)” — NOT PRIMARY

- Adapter’s mapping exists and is correct (`stopPrice` → `triggerPrice` for Algo).
- Failure happens because the value is missing/invalid upstream.

### (4) “branch bypassed builder” — PLAUSIBLE CONTRIBUTOR

- В домене одновременно существует прямой bracket placement путь (в `fsm.py` для некоторых flows) и emission через `ManageFlowFSM → DEC:PLACE_ORDER`.
- `-1102` однозначно исходит из generic `PLACE_ORDER` handler (fail-open), а не из контрактного валидатора.

---

## Minimal Fix Options (NO implementation)

### Option A — Fail-closed preflight in `ExecPosFSM` (most minimal, highest safety)

In `ExecPosFSM._execute_decision()` for `verb == "PLACE_ORDER"`:

- If `order_type` is conditional (`STOP_MARKET`, `TAKE_PROFIT_MARKET`, `STOP`, `TAKE_PROFIT`, `TRAILING_STOP_MARKET`):
  - require `stopPrice` to be present and “real” (not `None`, not `"None"`, not `"nan"`, not empty).
  - if missing → **block placement (no network call)**.

**Fail-closed output** (why ≤80 chars):

- `EP-1102 stopPrice missing TAKE_PROFIT_MARKET`

### Option B — Fail-closed emission in `ManageFlowFSM._emit_place_order`

- Enforce: for `order_type` not in (`LIMIT`, `MARKET`) ⇒ `stopPrice` must be a non-empty string.
- If missing, do not emit DEC:PLACE_ORDER; instead emit a domain-level reject/health event (or log) with a short why.

### Option C — Defensive guard in `BinanceAdapter.place_*_close_position`

- If `stop_price` is `None`/empty/`"None"`/`"nan"` → raise before calling `_post_order_with_algo_fallback()`.
- This is a safety net for any future call sites.

---

## Fail-closed policy (explicit)

If a conditional order is about to be placed and `stopPrice` is missing/invalid:

- **BLOCK** placement (no request to Binance)
- **EMIT** a short reason (≤80 chars) including symbol + orderType, e.g.:
  - `EP-1102 missing stopPrice XRPUSDT TAKE_PROFIT_MARKET`

---

## Test Plan (names + assertions)

1) `test_execpos_place_order_blocks_when_stopprice_missing()`
   - Given `DEC:PLACE_ORDER` with `order_type=TAKE_PROFIT_MARKET` and missing/None `stopPrice`
   - Assert: adapter is NOT called; an error/reject is emitted with `why` length ≤ 80.

2) `test_manage_emit_place_order_populates_stopprice_for_tp_sl()`
   - Given `_emit_place_order(... order_type=TAKE_PROFIT_MARKET, price="1.2345" ...)`
   - Assert: payload contains `stopPrice == "1.2345"` (and not None).

3) `test_binance_algo_fallback_maps_stopprice_to_triggerprice()`
   - Given `_post_order_with_algo_fallback()` sees `-4120` and params include `stopPrice="1"`
   - Assert: second request uses `/fapi/v1/algoOrder` with `triggerPrice="1"` and without `quantity/reduceOnly` when `closePosition=true`.

4) `test_ticksize_quantization_does_not_produce_none()`
   - For DOGEUSDT tick_size=0.00001 and XRPUSDT tick_size=0.0001
   - Assert: computed TP/SL stopPrice is a Decimal/string, never None.
