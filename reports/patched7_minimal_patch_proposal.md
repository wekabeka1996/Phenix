# patched7: Minimal Patch Proposal

## Verdict

`config-only impossible`

F6 cannot be expressed with the current Aurora config surface alone.

Required runtime condition:
- symbol = `ETHUSDT`
- regime = `TREND_DOWN`
- side = `BUY` / LONG
- current 5m bar is green
- delta vs previous close `> +0.15%`

Current config knobs do not encode that conjunction.

## Why config-only is impossible

Existing per-asset Aurora config for ETH exposes:
- `allowed_regimes`
- `signal_threshold`
- `regime_thresholds`
- `regime_sizing`
- `side_bias`
- `volatility_entry_logic`
- exit / TP / trailing / cooldown controls

These knobs are present in [config/aurora/strategies/aurora.yaml](config/aurora/strategies/aurora.yaml#L217) and modeled by [apps/reference/config_models.py](apps/reference/config_models.py#L3330).

What is missing:
- no config field for bar-color gating
- no config field for `delta_vs_prev_close`
- no config field for a symbol+regime+side-specific entry veto based on current bar shape

There is also an important runtime nuance:
- bar-driven FE already computes OHLC-based bar features and injects `bar_body` / `true_range` into `CMD:PROCESS_STRATEGY` at [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L1540)
- the command schema includes full OHLC bar plus volatility block at [apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json](apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json#L1)
- but current `delta_price` is explicitly forced to `close - open` for bar-close processing, not `close - prev_close`, via the synthetic previous-tick logic at [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L776)

So even though the bar path already knows the current bar is green or red from OHLC, the exact F6 metric `delta vs previous close` is not currently exposed as a config-driven gate input.

## Minimal patch surface

### 1. Add one additive FE field

In [apps/reference/domains/feature_engineering/feature_engineering.py](apps/reference/domains/feature_engineering/feature_engineering.py#L1540), export one new additive metric inside `features["volatility"]`:

- `delta_vs_prev_close_pct`

Definition:

```text
(bar_close - prev_close) / prev_close
```

Use the already-maintained `vol_state.prev_close` before it is overwritten with current `bar_close`.

Schema update:
- extend [apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json](apps/reference/domains/feature_engineering/schemas/cmd_process_strategy_v1.json#L1)

### 2. Add one small config block

In [apps/reference/config_models.py](apps/reference/config_models.py#L3330), add an optional per-instrument gate, for example:

```yaml
entry_phase_guard:
  enabled: true
  apply_regimes: ["TREND_DOWN"]
  apply_sides: ["BUY"]
  reject_green_bar_if_delta_vs_prev_close_gt_pct: 0.0015
```

Then wire it into `AuroraInstrumentConfig`.

Target runtime config location after implementation:
- `config/aurora/strategies/aurora.yaml`
- mirrored in `config/aurora_baseline/strategies/aurora.yaml` only if baseline must understand the new schema

### 3. Add one gate in Aurora decision flow

In [apps/reference/domains/decision_making/aurora_decision.py](apps/reference/domains/decision_making/aurora_decision.py#L220), insert a narrow fail-closed veto after:
- scoring has determined side
- regime allowlist has passed

and before:
- payload emit via `EVT:STRATEGY_SIGNAL_PRODUCED`

Gate logic:

```text
if symbol == ETHUSDT
and effective side == BUY
and regime == TREND_DOWN
and bar_close > bar_open
and delta_vs_prev_close_pct > 0.0015:
    block signal
```

Suggested reason code:
- `ENTRY_PHASE_GUARD_BLOCKED`

Suggested why-chain fragment:
- `ENTRY_PHASE_GUARD`
- `GREEN_BOUNCE_EXHAUSTION`

## Proposed runtime YAML once code support exists

```yaml
strategies:
  aurora:
    assets:
      ETHUSDT:
        entry_phase_guard:
          enabled: true
          apply_regimes: ["TREND_DOWN"]
          apply_sides: ["BUY"]
          reject_green_bar_if_delta_vs_prev_close_gt_pct: 0.0015
```

## Why this is the minimal safe patch

- no change to scoring weights
- no change to TP/SL geometry
- no change to regime detector
- no change to symbol registry
- no broad behavioral rewrite
- only one additive FE metric, one optional config block, one narrow Aurora-side veto

## Validation sequence after implementation

1. Loader parse smoke for the new config key.
2. Narrow unit/schema checks for the new FE field and decision veto.
3. Manual March-only backtest.
4. Manual Q1 cumulative backtest.

The prepared window files for steps 3-4 are:
- [config/overlays/patched7_march_only.yaml](config/overlays/patched7_march_only.yaml)
- [config/overlays/patched7_q1_cumulative.yaml](config/overlays/patched7_q1_cumulative.yaml)