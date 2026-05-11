# PKG-7 Preflight Gate Spec

## Goal

Abort expensive runtime when a requested trial does not produce a real effective config delta relative to its anchor.

## Inputs

- requested overlay
- `trial_id`
- `arm_id`
- `trial_params_json`
- `expected_changed_paths`
- optional `parent_anchor`
- optional `anchor_overrides`

## Preflight Flow

1. Load the requested config with overlay.
2. Materialize the effective config payload.
3. Compute `effective_config_hash` and `effective_strategy_slice_hash`.
4. If a non-empty `trial_params_json` is provided, load the anchor config in the same execution context.
5. Compute anchor effective hashes.
6. If both effective hashes match the anchor hashes, reject before runtime.
7. Persist the manifest before returning.

## Rejection Modes

- `MISSING_PARENT_ANCHOR`
  - Trigger: a trial requests deltas but no parent anchor is provided.

- `NO_EFFECTIVE_CONFIG_DELTA`
  - Trigger: requested trial params are non-empty, but both effective hashes match the anchor hashes.

## Artifact Guarantees

- manifest is written before runtime starts
- rejected trials still produce an auditable manifest
- runtime completion updates the same manifest instead of creating a second artifact

## Why This Matters

PKG-6 proved that post-hoc candidate comparison without preflight materialization is not trustworthy. PKG-7 makes ineffective trials fail closed immediately.