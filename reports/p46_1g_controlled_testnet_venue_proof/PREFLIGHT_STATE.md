# Preflight State

## FACTS

```yaml
preflight:
  symbol: null
  position_amount: unknown
  open_order_count: unknown
  mark_or_reference_price: unknown
  wallet_or_available_balance_ref: unknown
  min_qty: unknown
  step_size: unknown
  min_notional: unknown
  selected_target_notional: "10.0"
  calculated_quantity: null
  account_mode: unknown
  position_mode: unknown
  blocker: CREDENTIALS_MISSING
```

## INFERENCES

- Stopping before symbol selection prevents touching unrelated operator state.

## ASSUMPTIONS

- Preferred SOLUSDT is only a candidate, not a selection.

## UNKNOWNS

- All authenticated account and venue state fields remain unknown.
