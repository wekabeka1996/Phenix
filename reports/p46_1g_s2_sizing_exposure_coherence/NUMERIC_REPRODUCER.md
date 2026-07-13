# Numeric Reproducer

## FACTS

```yaml
sizing_chain:
  symbol: DOGEUSDT
  side: BUY
  reference_price: 0.0722 USDT/DOGE
  reference_price_source: deterministic fixture constrained by prior observed qty=138
  reference_price_timestamp: prior exact venue timestamp not persisted
  account_equity_or_balance: 3093.52554595 USDT
  account_snapshot_source: prior authenticated Testnet account preflight
  account_snapshot_timestamp: 2026-07-13 S1 run; exact source timestamp not persisted
  target_notional_quote: 10.0 USDT pre-buffer
  operator_cap_quote: 20.0 USDT
  policy_risk_fraction: 0.0003232557756987608819264420078
  gross_soft_limit_quote: 20000 USDT side headroom
  fee_buffer_quote: 0.01 USDT notional equivalent
  slippage_buffer_quote: 0 USDT in this sizing function
  existing_exposure_quote: 0 USDT
  reserved_exposure_quote: 0 USDT
  remaining_soft_limit_quote: 9.9636 USDT requested after floor
  exchange_min_qty: 1 DOGE
  exchange_step_size: 1 DOGE
  exchange_min_notional: 5 USDT
  policy_clip_min_qty: 139 DOGE at fixture price
  policy_clip_min_quote: 10 USDT
  raw_quantity: 138.3656509695290858725761773 DOGE
  rounded_quantity: 138 DOGE
  rounded_notional_quote: 9.9636 USDT
  rejection_reason: SOFT_LIMIT_BELOW_CLIP_MIN
```

- The deterministic test uses production `compute_notional_target`, `compute_qty`, and `SoftClipEngine`.

## INFERENCES

- The guard rejection was mathematically inevitable for a pre-buffer target equal to the clip floor.

## ASSUMPTIONS

- The fixture price is representative of the lost S1 price because it reproduces the persisted quantity exactly; it is not claimed as the exact historical ask.

## UNKNOWNS

- The exact S1 ask was not persisted.
