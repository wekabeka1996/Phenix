# PROXY UNIVERSE SPEC

## Goal

PKG-5 needed the smallest honest March proxy surface for future bounded search.

The proxy must preserve enough context for Aurora readiness and macro features while remaining computationally narrow.

## Contract

The proxy-universe contract is now persisted under:

- `system_meta.runtime.research_proxy`
- report top-level `proxy_universe`

Fields:

- `label`
- `tracked_symbols`
- `tradable_symbols`
- `context_symbols`
- `strategy_assignments`
- `fail_closed_on_scoring_fallback`

## Validity Rules

### ETH-only is invalid

ETH-only proxy was already measured in PKG-4 and rejected.

Reason:

- removing BTC anchor context collapses readiness and macro-resid usefulness,
- resulting surface degenerated into a zero-trade triviality,
- that violates honest-search constraints.

Therefore:

- `tracked_symbols = ["ETHUSDT"]` with no BTC context is not an acceptable research surface.

### ETH tradable + BTC context is the first acceptable proxy

Accepted PKG-5 proxy:

- `tracked_symbols = ["ETHUSDT", "BTCUSDT"]`
- `tradable_symbols = ["ETHUSDT"]`
- `context_symbols = ["BTCUSDT"]`
- `strategy_assignments = {"ETHUSDT": ["aurora"]}`

Why this is acceptable:

- ETH remains the only tradable symbol, keeping search narrow.
- BTC remains available as anchor/context input, preserving the minimal market context Aurora still depends on.
- The proxy produced real trades and non-trivial runtime behavior.

## Fail-Closed Policy

For honest bounded search on this proxy, PKG-5 requires:

- `fail_closed_on_scoring_fallback = true`

This means proxy runs are not accepted if fallback contamination appears.

## PKG-5 Verified Proxy Instances

Baseline proxy run `20260314_170343`:

- label: `pkg5_eth_btc_baseline`
- tracked: `ETHUSDT`, `BTCUSDT`
- tradable: `ETHUSDT`
- context: `BTCUSDT`

V1 proxy run `20260314_172657`:

- label: `pkg5_eth_btc_v1`
- tracked: `ETHUSDT`, `BTCUSDT`
- tradable: `ETHUSDT`
- context: `BTCUSDT`

## Allowed Use In Next Package

This proxy is acceptable for:

- bounded search over existing code-backed YAML knobs,
- March-only proxy comparisons,
- artifact-verified fallback-free research.

It is not a substitute for:

- full-universe canonical evaluation,
- Jan/Feb/Q2 generalization claims,
- production-readiness claims.