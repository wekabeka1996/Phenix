# Exposure Policy Resolver

This module centralizes access to `trading.execution.exposure` and `trading.execution.fallback` configuration. It exposes normalized dataclasses that downstream consumers can rely on without manually spelunking nested dictionaries or Pydantic models.

## Location

```
apps/reference/config_exposure_policy.py
```

## Returned Structures

- `ExposureCaps`: pre-normalized ratio values for equity, directional, and per-symbol limits, plus the notional fallback fraction.
- `PendingReservations`: TTL settings for reservations, post-fill holds, and position staleness.
- `LeverageDefaults`: default leverage and per-symbol overrides with `resolve_for(symbol)` helper.
- `FallbackConfig`: retry/backoff policy with explicit `max_attempts`, `enabled`, and normalized percent reduction.
- `ExposurePolicy`: wrapper that groups the above with flags for counting pending orders and excluding reduce-only instructions.

## Consumer Guidance

1. Call `resolve_exposure_policy(config)` once during component initialization and cache the result.
2. Use the provided dataclass helpers instead of querying the raw config object.
3. Prefer `FallbackConfig.backoff_sequence()` and `FallbackConfig.max_attempts` when building retry loops so configuration updates remain consistent.

The resolver is additive-only and backwards compatible; missing fields fall back to existing defaults from the legacy implementation.
