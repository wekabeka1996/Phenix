# Aggregated OCO v1 — XAI Logging Contract

## 1. Події

### 1.1. AGG_OCO_BRACKET_SET_CHANGED

Емітиться при:
- створенні нового aggregated bracket_set;
- перерахунку після scale-in / partial-close / manual-fix (`partial_close_unprotected`);
- повному видаленні при full-close / flip.

Поля (JSON):

- `event_type: "AGG_OCO_BRACKET_SET_CHANGED"`
- `symbol: str`
- `side: "LONG" | "SHORT"`
- `bracket_set_id: str`
- `version: int`
- `action: "create" | "recalc_scale_in" | "recalc_partial" | "recalc_manual_fix" | "cleanup_full_close" | "flip_reset"`
- `position_qty_before: Decimal`
- `position_qty_after: Decimal`
- `avg_price_before: Decimal`
- `avg_price_after: Decimal`
- `sl_price_before: Decimal | null`
- `sl_price_after: Decimal | null`
- `tp_price_before: Decimal | null`
- `tp_price_after: Decimal | null`
- `why: str` (≤80 символів)
- `rid: str` (request/route id, якщо є в контексті FSM)

### 1.2. AGG_OCO_BRACKET_GUARD

Емітиться в `OrderGuardian.ensure_single_bracket_set_for_position` при:

- спрацюванні TTL guard;
- очищенні дублікатів;
- fail-closed блокуванні cleanup;
- відсутності мета-стану під час cleanup;
- zero-position cleanup, коли `position_amt` дорівнює нулю, але reduceOnly ордери ще відкриті.

Поля:

- `event_type: "AGG_OCO_BRACKET_GUARD"`
- `symbol: str`
- `side: "LONG" | "SHORT"`
- `bracket_set_id: str | null`
- `position_amt: Decimal`
- `decision: "ttl_skip" | "cleanup_extras" | "skip_to_keep_sl" | "no_meta_state" | "cleanup_zero_position"`
- `extra_cancelled: int`
- `has_sl_after: bool`
- `why: str` (≤80 символів)
- `rid: str`

## 2. Runtime sources

- `apps/reference/domains/execution_position/fsm_manage.py`:
	- `_recalc_aggregated_brackets` → emits `AGG_OCO_BRACKET_SET_CHANGED` for `action` values `create`, `recalc_scale_in`, `recalc_partial`, `recalc_manual_fix`, `cleanup_full_close`, `flip_reset`.
	- `_rehydrate_aggregated_brackets_on_startup` → emits `AGG_OCO_BRACKET_SET_CHANGED(action="rehydrate")` when DR rebuilds metadata before guardian cleanup.
- `apps/reference/services/order_guardian.py`:
	- `ensure_single_bracket_set_for_position` → emits `AGG_OCO_BRACKET_GUARD` with `decision` = `ttl_skip`, `cleanup_extras`, `skip_to_keep_sl`, `no_meta_state`, `cleanup_zero_position`.
	- `rehydrate_bracket_set_for_position` → emits `AGG_OCO_BRACKET_SET_CHANGED(action="rehydrate")` with source `guardian` when metadata was missing and is rebuilt from live orders.

## 3. Sample logs (truncated)

```json
{"event_type":"AGG_OCO_BRACKET_SET_CHANGED","symbol":"SOLUSDT","side":"LONG","bracket_set_id":"RID123_sl_tp","action":"recalc_scale_in","position_qty_before":"1.0","position_qty_after":"2.5","sl_price_after":"95.10","tp_price_after":"110.40","why":"agg_scale_in_recalc","rid":"RID123"}
```

```json
{"event_type":"AGG_OCO_BRACKET_GUARD","symbol":"SOLUSDT","side":"LONG","bracket_set_id":"RID123_sl_tp","position_amt":"2.5","decision":"ttl_skip","extra_cancelled":0,"has_sl_after":true,"why":"age_ms=1200 ttl_ms=3000"}

{"event_type":"AGG_OCO_BRACKET_GUARD","symbol":"SOLUSDT","side":"LONG","bracket_set_id":"RID123_sl_tp","position_amt":"0","decision":"cleanup_zero_position","extra_cancelled":2,"has_sl_after":false,"why":"position_amt_zero"}
```
