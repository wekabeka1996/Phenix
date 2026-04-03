# BTC_CROSS_ASSET_INFLUENCE_AUDIT

Date: 2026-03-30

## Scope

This audit answers one question only:

- Through which already-existing runtime surfaces do BTC or configured anchor symbols influence non-anchor instruments today?

This report does not treat config presence as proof by itself. A surface is counted only when a live producer and a live consumer were both found, or when the absence of a consumer was explicitly proven in searched runtime paths.

## Executive Verdict

- BTC and anchor influence already exists in the current runtime. It is not hypothetical.
- The strongest live influence path is not raw regime override. It is anchor-data ingestion into FeatureEngineering, then macro_resid readiness and macro_resid feature production, then Aurora directional logic and anchor_shock_veto.
- BTC influence also indirectly affects all DecisionMaking strategies through feature warmup readiness when anchor-derived features are not ready.
- macro_sync is still actively computed in FeatureEngineering, but no direct consumer was found in the inspected decision_making or objective_engine runtime paths. In the current audited state, macro_sync should not be counted as a proven live decision input.
- A new BTC leader-follow layer would risk double counting if it simply re-scores the same anchor move already represented by macro_resid and anchor_shock_veto.

## Evidence Base

Primary files inspected:

- apps/reference/domains/market_data/market_data_connector.py
- apps/reference/domains/market_data/proxy.py
- apps/reference/domains/feature_engineering/feature_engineering.py
- apps/reference/domains/feature_engineering/calculation_engine.py
- apps/reference/domains/decision_making/readiness_gates.py
- apps/reference/domains/decision_making/aurora_decision.py
- config/aurora/trading.yaml
- config/aurora/domains.yaml
- config/aurora/strategies/aurora.yaml
- apps/reference/config_models.py

## FACTS

### 1. Anchor universe is configured and transported today

Current checked config surfaces include:

- config/aurora/trading.yaml macro_sync anchors: BTCUSDT and ETHUSDT
- config/aurora/domains.yaml feature_engineering macro_sync anchors: BTCUSDT and ETHUSDT

Market-data transport proof found in code:

- market_data_connector.py emits EVT:ANCHOR_UPDATED
- market_data/proxy.py also documents and emits EVT:ANCHOR_UPDATED

FeatureEngineering consumer proof:

- FeatureEngineering subscribes to EVT:ANCHOR_UPDATED
- FeatureEngineering handles EVT:ANCHOR_UPDATED in _on_anchor_updated_event

This establishes a live anchor event path from market data into FeatureEngineering.

### 2. There are two anchor update paths in current FeatureEngineering

Current repo facts:

- FeatureEngineering can update anchor buffers from EVT:ANCHOR_UPDATED.
- FeatureEngineering can also update anchor buffers directly from ticks when macro_sync_anchor_update_from_ticks is true.

Current checked config split:

- config/aurora/domains.yaml sets anchor_update_from_ticks: true for FeatureEngineering macro_sync.
- config/aurora/trading.yaml sets anchor_update_from_ticks: false under market_data macro_sync.

The strict statement supported by code is:

- The active FeatureEngineering gate for tick-based anchor updates reads the FeatureEngineering config surface.
- There are two config surfaces with different values, which makes anchor ingestion behavior easy to misread unless the actual consumer path is checked.

### 3. macro_sync is computed, but not proven as a current decision input

Proven in FeatureEngineering:

- macro_sync buffers exist.
- macro_sync is computed.
- macro_sync readiness and timestamps are tracked.

Not proven in the inspected live decision paths:

- No macro_sync match was found in apps/reference/domains/decision_making/**/*.py.
- No macro_sync match was found in apps/reference/domains/objective_engine/**/*.py.

Therefore the correct audited statement is:

- macro_sync is a live FeatureEngineering computation surface.
- macro_sync was not proven to be a live direct input to current decision_making or objective_engine runtime paths.

### 4. macro_resid is a live anchor-derived feature and a material influence surface

Proven in FeatureEngineering and calculation_engine:

- calculation_engine.update_macro_resid stores both asset returns and anchor returns.
- calculation_engine.compute_macro_resid computes a residualized, scaled, clipped value from those returns.
- FeatureEngineering writes features["macro_resid"] only when macro_resid is ready; otherwise it emits None for that feature.
- FeatureEngineering comments and logic explicitly reference BTCUSDT anchor dependency in the macro_resid warmup path.

This proves macro_resid is not a generic standalone indicator. It is explicitly an anchor-relative cross-asset feature.

### 5. Anchor readiness can indirectly block all trade decisions that depend on FE warmup

Proven in FeatureEngineering:

- FeatureEngineering warmup readiness includes macro_resid readiness when macro_resid is enabled.
- If macro_resid is not ready, FeatureEngineering warmup.full_ready remains false.

Proven in DecisionMaking:

- ReadinessGates blocks trade-intent progression when features warmup.full_ready is false.

Therefore:

- BTC and anchor readiness already influence all downstream strategies indirectly through the feature warmup gate, even where a strategy does not directly consume macro_resid in its scoring logic.

This is an important surface because it is cross-asset influence via availability and readiness, not only via scoring.

### 6. Aurora has a direct, material BTC-anchor influence path

The Aurora strategy path contains several separate but related anchor surfaces.

#### 6.1 macro_resid is a live Aurora feature

Proven in current checked Aurora config:

- config/aurora/strategies/aurora.yaml states that macro_resid replaces macro_sync in directional scoring.
- macro_resid appears in the directional feature/weight config.
- macro_resid appears in essential_features.

This proves Aurora treats macro_resid as a live decision input, not just telemetry.

#### 6.2 anchor_shock_veto is live and BTC-specific in current config

Current checked Aurora config includes:

- anchor_symbol: BTCUSDT
- threshold: -2.0 for anchor_shock_veto

Current Aurora decision code proves:

- macro_resid is read from features
- anchor_shock_veto is evaluated
- a non-anchor BUY is blocked when macro_resid is below the configured threshold

This is a direct BTC-to-alt policy influence surface.

### 7. Direct macro_resid consumption was not proven in MR or MD-AMR

Searched decision_making runtime results for macro_resid showed matches in Aurora decision code only.

So the strict audited statement is:

- Direct macro_resid scoring or veto use was proven in Aurora.
- Direct macro_resid scoring or veto use was not proven in the inspected MR or MD-AMR decision paths.
- MR and MD-AMR can still be indirectly affected by anchor readiness through FE warmup.full_ready.

### 8. Surface classification

| Surface | Producer | Consumer | Current status | Materiality |
| --- | --- | --- | --- | --- |
| EVT:ANCHOR_UPDATED transport | market_data | FeatureEngineering | Active | Transport only by itself |
| Tick-based anchor updates | FeatureEngineering tick path | FeatureEngineering anchor buffers | Active in code, config-split | Material upstream data path |
| macro_sync | FeatureEngineering | No direct decision/objective consumer found | Computed but not proven decision-live | Not counted as current direct trading influence |
| macro_resid | FeatureEngineering and calculation_engine | Aurora decision flow | Active | Direct material decision input |
| macro_resid readiness | FeatureEngineering | DecisionMaking warmup gate | Active | Indirect material block on trade progression |
| anchor_shock_veto | Aurora config plus Aurora decision code | Aurora | Active | Direct BTC-specific policy veto |
| Direct BTC feature in MR | Not proven | Not proven | Not proven | None proven |
| Direct BTC feature in MD-AMR | Not proven | Not proven | Not proven | None proven |

### 9. Current double-count risk is real if new BTC logic is naive

The current repo already has at least three distinct BTC-anchor-related influence mechanisms:

- anchor-derived feature readiness and warmup blocking
- macro_resid as a directional feature in Aurora
- anchor_shock_veto as a binary adverse-shock veto in Aurora

Therefore a new BTC leader-follow feature would be at high risk of double counting if it simply adds another directional score driven by the same recent BTC move.

## INFERENCES

- The cleanest new BTC leader-follow concept should be temporal or lifecycle-aware, not just another magnitude-based directional score on the same anchor movement already expressed by macro_resid and anchor_shock_veto.
- Because macro_sync is not currently proven as a direct decision input, reviving it as a decision feature would introduce an additional overlap surface and should not be treated as a free or orthogonal signal.
- The current split between trading.yaml and domains.yaml for anchor_update_from_ticks increases the risk of operator misunderstanding and replay/live parity mistakes.

## ASSUMPTIONS

- This audit assumes the inspected decision_making and objective_engine directories are the relevant in-repo consumers for current trading decisions.
- This audit does not assume out-of-repo consumers of macro_sync.

## UNKNOWNS

- Whether production market-data plumbing deduplicates anchor updates in a way that fully neutralizes the config split between event-based and tick-based anchor updates.
- Whether any out-of-scope analytics or observability service consumes macro_sync in a way that operators subjectively treat as trading-relevant.
- Whether future strategies outside the inspected runtime paths already plan to consume macro_sync or other anchor-relative features.

## Bottom Line

BTC already influences other symbols today through anchor transport, anchor-derived warmup readiness, macro_resid, and Aurora anchor-shock veto logic. The strongest current trading effect is not a BTC-driven rewrite of local regime. It is cross-asset context entering through anchor-relative features and vetoes. Any new BTC leader-follow design should be built to avoid re-scoring the same BTC move that the current runtime already prices in through macro_resid and anchor_shock_veto.
