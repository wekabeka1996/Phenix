# REPORT

## Problem Framing

This verification checks the active Aurora/Phenix decision_making intent-builder surface for semantic integrity of Kelly-related TradeIntent provenance.

In scope:
- decision_making hot path from strategy signal to TRADE_INTENT_PROPOSED
- Kelly config SSOT versus runtime reader behavior
- TradeIntent payload fields p, payoff_ratio_r, size.kelly_fraction
- WAL and order_log_v1 provenance at this package boundary
- tests that may mask non-SSOT fields or synthetic payload conventions

Out of scope:
- risk_management behavior redesign
- objective_engine redesign
- new Kelly estimator or sizing engine
- live sizing tuning
- WAL rewrite or historical repair

## FACTS

- Active runtime boot loads config from config/aurora through ConfigLoader in apps/reference/main.py:382-383.
- Live domain composition instantiates DecisionMaking directly from core.facade in apps/reference/bootstrap/domain_builder.py:143.
- apps/reference/domains/decision_making/decision_making.py is a compatibility shim that re-exports core.facade; it is not the owning implementation.
- No legacy apps/reference/domains/decision_making/intent_builder.py exists on disk. The active builder surface is apps/reference/domains/decision_making/intent/builder.py.
- StrategyGateway.process_signal is the active signal-to-intent gate chain. On passed gates it calls dm._propose_trade_intent in apps/reference/domains/decision_making/gateway/strategy_gateway.py:654. A reduce-only partial-close path calls the same facade entry in apps/reference/domains/decision_making/gateway/strategy_gateway.py:527.
- DecisionMaking constructs IntentBuilder in apps/reference/domains/decision_making/core/facade.py:191 and forwards the allowed path to self._builder.build_and_emit in apps/reference/domains/decision_making/core/facade.py:358.
- IntentBuilder resolves Kelly fraction through resolve_kelly_fraction in apps/reference/domains/decision_making/intent/builder.py:296.
- resolve_kelly_fraction exists in apps/reference/domains/decision_making/intent/builder_validators.py:130.
- resolve_kelly_fraction reads strat_cfg.decision.kelly.fraction with a default of 0.1 in apps/reference/domains/decision_making/intent/builder_validators.py:138 and returns 0.1 again on blanket exception in apps/reference/domains/decision_making/intent/builder_validators.py:140.
- TradeIntent payload assembly hardcodes p = 0.75 and payoff_ratio_r = 2.0 in apps/reference/domains/decision_making/intent/payload_assembler.py:53-54.
- TradeIntent schema requires p in apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json:23, payoff_ratio_r in apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json:28, and size.kelly_fraction in apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json:84.
- Kelly SSOT type is KellyConfig in apps/reference/config/shared/atoms.py:132.
- KellyConfig fields are base_probability, kelly_cap, kelly_alpha, payoff_ratio_r, p_min, p_max, uplift_factor in apps/reference/config/shared/atoms.py:137-143.
- config/aurora/strategies/aurora.yaml defines Kelly config values base_probability = 0.5, kelly_cap = 0.25, kelly_alpha = 0.8, payoff_ratio_r = 1.5, p_min = 0.45, p_max = 0.65 in config/aurora/strategies/aurora.yaml:221-226.
- A targeted search across config/aurora/strategies/*.yaml found Kelly fields only in config/aurora/strategies/aurora.yaml. No Kelly fraction field was found there.
- Direct runtime probe through ConfigLoader returned the following live result:

```text
{'cfg_type': 'AuroraConfig', 'kelly_type': 'KellyConfig', 'has_fraction': False, 'kelly_keys': ['base_probability', 'kelly_alpha', 'kelly_cap', 'p_max', 'p_min', 'payoff_ratio_r', 'uplift_factor'], 'payoff_ratio_r': 1.5}
```

- Direct runtime probe through IntentBuilder with the real loaded Aurora config returned the following payload result:

```text
{'p': '0.75', 'payoff_ratio_r': '2.0', 'kelly_fraction': '0.1', 'valid_for_ms': 1200000, 'config_payoff_ratio_r': 1.5, 'config_has_fraction': False}
```

- IntentBuilder writes the full TRADE_INTENT_PROPOSED payload to WAL in apps/reference/domains/decision_making/intent/builder.py:404 and emits EVT:TRADE_INTENT_PROPOSED in apps/reference/domains/decision_making/intent/builder.py:417.
- Local archived WAL contains real TRADE_INTENT_PROPOSED rows. Sample from ops/wal/2026-04-20.jsonl:20864 includes p = 0.75, payoff_ratio_r = 2.0, and size.kelly_fraction = 0.1 while strategy = aurora and the same live config family exposes payoff_ratio_r = 1.5.
- OrderLogger projection is built by build_order_intent_log_entry in apps/reference/domains/decision_making/intent/payload_assembler.py:128 and writes an ORDER_INTENT record in apps/reference/domains/decision_making/intent/payload_assembler.py:143-156.
- That ORDER_INTENT projection contains lifecycle_id, intent_proposed, idempotent_key, and normalize_mode_effective, but no p, payoff_ratio_r, or kelly_fraction fields.
- execution_position uses a routing-only TradeIntentRoutingEnvelope in apps/reference/contracts/trade_intent_envelope.py:17 and a typed open-intake model in apps/reference/domains/execution_position/trade_intent_open_intake.py:83.
- TradeIntentOpenIntake.to_cmd_open_payload forwards order fields and metadata including tca_budget and risk_context in apps/reference/domains/execution_position/trade_intent_open_intake.py:121, 144-152. It does not define or forward p, payoff_ratio_r, or kelly_fraction.
- Targeted grep in logs/order_log_v1.jsonl found no ORDER_INTENT rows at inspection time.
- Targeted grep in logs/** and data/** found no TRADE_INTENT_PROPOSED rows at inspection time.
- Targeted grep in ops/** found multiple TRADE_INTENT_PROPOSED rows and supplied the archived WAL sample above.
- tests/unit/llm/test_llm_intent_builder_contract.py injects strat_cfg.decision.kelly.fraction = 0.1 in line 44.
- tests/domains/decision_making/test_intent_builder_payload_contract.py injects decision.kelly.fraction = 0.15 in line 71 and asserts kelly_fraction = 0.15 while also asserting p = 0.75 and payoff_ratio_r = 2.0 in lines 179-193.
- tests/domains/decision_making/test_intent_builder_reservation_cleanup.py injects decision.kelly.fraction = 0.15 in line 36.
- tests/bootstrap/test_schema_registry_activation.py encodes sample payload constants p = 0.75, payoff_ratio_r = 2.0, kelly_fraction = 0.10 in lines 37-49.
- tests/integration/test_ep01_4_tif_plumbing.py encodes sample payload constants p = 0.75, payoff_ratio_r = 2.0, kelly_fraction = 0.1 in lines 155-166 and 201-212.
- tests/unit/decision_making/test_fail_closed_config.py contains standalone Kelly math examples using base_probability, uplift_factor, p_min, and p_max, but it does not invoke the active IntentBuilder hot path.
- AGENTS.md references docs/ai/AGENT_REPORT_SCHEMA.md, docs/ai/DONE_CRITERIA.md, and docs/ai/AURORA_DOMAIN_PROTOCOL.md, but those files were absent on disk during this verification.

## INFERENCES

- The active decision_making TradeIntent boundary is not using a real Kelly calculation on this package surface.
- The active decision_making TradeIntent boundary is also not faithfully using the existing live Kelly config for the inspected metadata fields.
- Current TradeIntent metadata provenance is synthetic:
  - p comes from a payload literal 0.75.
  - payoff_ratio_r comes from a payload literal 2.0.
  - size.kelly_fraction comes from a compatibility reader of a non-SSOT field that currently falls back to 0.1.
- This is a semantic integrity defect even if execution_position ignores these fields, because the full payload is persisted to WAL and becomes historical provenance.
- Direct live open-execution sizing impact was not proven in this package surface, because StrategyGateway passes qty and price into the builder and TradeIntentOpenIntake does not read p, payoff_ratio_r, or kelly_fraction.
- The strongest currently proven blast radius is provenance pollution in WAL and any downstream consumer that trusts WAL TradeIntent metadata.
- order_log_v1 pollution for these exact Kelly fields is not proven on the current surface, because the ORDER_INTENT projection omits those fields and the inspected local order_log_v1 sample had no ORDER_INTENT rows.

## ASSUMPTIONS

- apps/reference/main.py plus apps/reference/bootstrap/domain_builder.py represent the intended live boot path for the current repository state.
- Archived WAL files under ops/wal are acceptable local runtime evidence for historical TradeIntent payload structure.
- The current ConfigLoader probe and current IntentBuilder probe are representative of the active repository state on this branch.

## UNKNOWNS

- Whether any downstream consumer outside execution_position reads p, payoff_ratio_r, or kelly_fraction behaviorally from WAL or event taps.
- Whether historical replay, ML, or RL pipelines consume archived WAL directly, indirectly, or only through projected order logs.
- Whether a truthful producer for p exists elsewhere but is currently ignored or overwritten before payload assembly.
- Whether historical polluted WAL should be quarantined, re-labeled, or merely documented.

## Exact Hot Path Map

1. apps/reference/main.py:382-383 loads config via ConfigLoader(config_dir=project_root / "config" / "aurora").
2. apps/reference/bootstrap/domain_builder.py:143 instantiates DecisionMaking(fsm=fsm, config=config).
3. apps/reference/domains/decision_making/gateway/strategy_gateway.py:254 owns EVT:STRATEGY_SIGNAL_PRODUCED gate-chain processing.
4. apps/reference/domains/decision_making/gateway/strategy_gateway.py:654 forwards passed entry intents to dm._propose_trade_intent with qty_dec and entry_price_dec already computed upstream.
5. apps/reference/domains/decision_making/core/facade.py:358 forwards the allowed path to self._builder.build_and_emit.
6. apps/reference/domains/decision_making/intent/builder.py:296 resolves kelly_frac via resolve_kelly_fraction.
7. apps/reference/domains/decision_making/intent/payload_assembler.py:53-54 hardcodes p and payoff_ratio_r inside build_trade_intent_payload.
8. apps/reference/domains/decision_making/intent/builder.py:404 writes the full trade_intent payload to WAL.
9. apps/reference/domains/decision_making/intent/builder.py:417 emits EVT:TRADE_INTENT_PROPOSED to execution_position.
10. apps/reference/contracts/trade_intent_envelope.py:17 routes only symbol, strategy, rid, side, reduce_only.
11. apps/reference/domains/execution_position/trade_intent_open_intake.py:83 and :121 normalize the execution open-intake seam using order, tca_budget, risk_context, and trace-related fields, but not p, payoff_ratio_r, or kelly_fraction.
12. apps/reference/domains/decision_making/intent/payload_assembler.py:128-156 projects a smaller ORDER_INTENT log entry for order_log_v1.

## Kelly Config SSOT Map

| Surface | Verdict | Evidence | Notes |
| --- | --- | --- | --- |
| YAML SSOT | Present | config/aurora/strategies/aurora.yaml:221-226 | Kelly block defines base_probability, kelly_cap, kelly_alpha, payoff_ratio_r, p_min, p_max |
| Pydantic SSOT | Present | apps/reference/config/shared/atoms.py:132-143 | KellyConfig has no fraction field |
| Loaded config object | Present | Direct ConfigLoader probe output above | Live object type is KellyConfig, has_fraction = False |
| Builder reader | Drifted | apps/reference/domains/decision_making/intent/builder_validators.py:130-140 | Reads decision.kelly.fraction, which is not in current SSOT |
| Payload producer | Drifted | apps/reference/domains/decision_making/intent/payload_assembler.py:53-54 | Emits literal p and payoff_ratio_r instead of sourced values |

## Relevant Occurrence Classification

Unrelated numeric hits such as tick sizes, OBI examples, or non-TradeIntent 0.1/2.0 literals were treated as out-of-scope noise and excluded from this table.

| Occurrence | Classification | Verdict |
| --- | --- | --- |
| apps/reference/domains/decision_making/intent/builder_validators.py:130-140 | runtime hot path | CONFIRMED_SEMANTIC_DRIFT |
| apps/reference/domains/decision_making/intent/payload_assembler.py:53-54 | runtime hot path | CONFIRMED_DEFECT |
| apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json:23,28,84 | schema | FALSE_POSITIVE as root cause; schema only requires presence, not truthful sourcing |
| config/aurora/strategies/aurora.yaml:221-226 | config | CONFIRMED_SEMANTIC_DRIFT because live config exists but payload builder does not honor it |
| apps/reference/config/shared/atoms.py:132-143 | schema/type SSOT | CONFIRMED_SEMANTIC_DRIFT boundary versus builder reader |
| tests/unit/llm/test_llm_intent_builder_contract.py:44 | test-only | CONFIRMED_TEST_MASKING |
| tests/domains/decision_making/test_intent_builder_payload_contract.py:71,179-193 | test-only | CONFIRMED_TEST_MASKING |
| tests/domains/decision_making/test_intent_builder_reservation_cleanup.py:36 | test-only | CONFIRMED_TEST_MASKING |
| tests/bootstrap/test_schema_registry_activation.py:37-49 | test-only sample payload | FALSE_POSITIVE as runtime proof |
| tests/integration/test_ep01_4_tif_plumbing.py:155-166,201-212 | test-only sample payload | FALSE_POSITIVE as Kelly provenance proof |
| apps/reference/domains/decision_making/docs/EVENTS.md | docs | FALSE_POSITIVE as runtime evidence |

## Claim-by-Claim Verdict Table

| Claim | Verdict | Notes |
| --- | --- | --- |
| 1. builder_validators.py has resolve_kelly_fraction() | CONFIRMED_SEMANTIC_DRIFT | The function exists and is on the active hot path, but the defect is not its existence alone; the defect is what it reads and how it falls back. |
| 2. resolve_kelly_fraction() reads strat_cfg.decision.kelly.fraction | CONFIRMED_SEMANTIC_DRIFT | Proven by apps/reference/domains/decision_making/intent/builder_validators.py:138. |
| 3. decision.kelly.fraction does not exist in YAML/Pydantic SSOT | CONFIRMED_SEMANTIC_DRIFT | Proven by config/aurora/strategies/aurora.yaml:221-226, apps/reference/config/shared/atoms.py:132-143, and direct ConfigLoader probe. |
| 4. resolve_kelly_fraction() silently falls back to 0.1 | CONFIRMED_DEFECT | Proven by builder_validators.py:138-140 and direct runtime probe showing kelly_fraction = 0.1 while config_has_fraction = False. |
| 5a. intent builder hardcodes p = 0.75 | CONFIRMED_DEFECT | Proven by payload_assembler.py:53 and direct IntentBuilder probe. |
| 5b. intent builder hardcodes payoff_ratio_r = 2.0 | CONFIRMED_DEFECT | Proven by payload_assembler.py:54 and direct IntentBuilder probe versus live config payoff_ratio_r = 1.5. |
| 5c. runtime kelly_fraction becomes 0.1 on current hot path | CONFIRMED_DEFECT | Proven by builder_validators fallback and direct IntentBuilder probe. |
| 6. aurora.yaml defines real Kelly parameters | CONFIRMED_SEMANTIC_DRIFT | True as config fact; the drift is that the payload producer does not faithfully use them. |
| 7. tests inject synthetic strat_cfg.decision.kelly.fraction = 0.1 or 0.15 | CONFIRMED_TEST_MASKING | Proven by tests/unit/llm/test_llm_intent_builder_contract.py:44 and two decision_making test fixtures. |
| 8a. WAL may contain synthetic Kelly metadata | CONFIRMED_DEFECT | Proven by source path and archived WAL sample ops/wal/2026-04-20.jsonl:20864. |
| 8b. order_log_v1 may contain synthetic Kelly metadata | FALSE_POSITIVE | Current ORDER_INTENT projection omits p, payoff_ratio_r, and kelly_fraction, and the inspected local order_log_v1 sample contained no ORDER_INTENT rows. |

## Runtime Semantic Verdict

Current runtime on the inspected decision_making boundary uses synthetic constants for Kelly-related TradeIntent metadata.

| Field | Current runtime source | Verdict |
| --- | --- | --- |
| p | Literal 0.75 in payload_assembler.py | synthetic constant |
| payoff_ratio_r | Literal 2.0 in payload_assembler.py | synthetic constant |
| size.kelly_fraction | Compatibility read of non-SSOT decision.kelly.fraction, currently falling back to 0.1 | synthetic constant-by-fallback |
| qty | Upstream argument from StrategyGateway gate chain | not recomputed here |
| price | Upstream argument from StrategyGateway gate chain | not recomputed here |

Conclusion: the inspected package surface is not using real Kelly sizing metadata and is not even using the live static Kelly config truthfully for the three inspected TradeIntent fields.

## WAL / Order Log Provenance Verdict

- WAL provenance for TRADE_INTENT_PROPOSED is polluted for p, payoff_ratio_r, and size.kelly_fraction.
- order_log_v1 provenance is not proven polluted for those exact fields on the current builder surface because ORDER_INTENT is a reduced projection without those fields.
- execution_position typed intake does not consume those fields, so direct open-order execution behavior from this seam was not proven to depend on them.
- Historical downstream replay, ML, or RL contamination is plausible for WAL consumers and remains unproven for order_log-only consumers.

## Files Inspected

- apps/reference/main.py
- apps/reference/bootstrap/domain_builder.py
- apps/reference/domains/decision_making/decision_making.py
- apps/reference/domains/decision_making/core/facade.py
- apps/reference/domains/decision_making/gateway/strategy_gateway.py
- apps/reference/domains/decision_making/intent/builder.py
- apps/reference/domains/decision_making/intent/builder_validators.py
- apps/reference/domains/decision_making/intent/payload_assembler.py
- apps/reference/domains/decision_making/intent/schemas/trade_intent_v1.json
- apps/reference/contracts/trade_intent_envelope.py
- apps/reference/domains/decision_making/contracts/boundary_models.py
- apps/reference/domains/execution_position/trade_intent_open_intake.py
- apps/reference/telemetry/order_logger.py
- apps/reference/config/shared/atoms.py
- apps/reference/config_models.py
- apps/reference/config_loader.py
- config/aurora/strategies/aurora.yaml
- config/aurora/strategies/mean_reversion.yaml
- ops/wal/2026-04-20.jsonl
- logs/order_log_v1.jsonl
- tests/domains/decision_making/test_intent_builder_validators.py
- tests/domains/decision_making/test_intent_builder_payload_contract.py
- tests/domains/decision_making/test_intent_builder_reservation_cleanup.py
- tests/domains/execution_position/test_trade_intent_open_intake.py
- tests/unit/llm/test_llm_intent_builder_contract.py
- tests/unit/decision_making/test_fail_closed_config.py
- tests/integration/test_ep01_4_tif_plumbing.py
- tests/bootstrap/test_schema_registry_activation.py
- tests/test_trade_intent_logging.py
- docs/problem/decision_making_intent_boundary_forensic_report_2026-04-01.md

## Files Changed

- docs/problem/decision_making_kelly_tradeintent_provenance_forensic_report_2026-04-25.md

No runtime code was changed.

## Tests Run With Exact Output

### Direct Probes

```text
ConfigLoader probe:
{'cfg_type': 'AuroraConfig', 'kelly_type': 'KellyConfig', 'has_fraction': False, 'kelly_keys': ['base_probability', 'kelly_alpha', 'kelly_cap', 'p_max', 'p_min', 'payoff_ratio_r', 'uplift_factor'], 'payoff_ratio_r': 1.5}

IntentBuilder probe:
C:\Users\user\Music\Phenix\vfoundation\config.py:21: UserWarning: RBAC_ADMIN_TOKENS not set - using INSECURE dev default 'dev-admin-token'. Set RBAC_ADMIN_TOKENS env var in production!
C:\Users\user\Music\Phenix\vfoundation\config.py:22: UserWarning: SIGNING_KEY not set - using INSECURE dev default. Set SIGNING_KEY env var in production!
C:\Users\user\Music\Phenix\vfoundation\config.py:115: UserWarning: WORKER_ID not set - using generated ID: DESKTOP-Q1UTE00-2c75d9bb. Set WORKER_ID env var for stable identification.
{'p': '0.75', 'payoff_ratio_r': '2.0', 'kelly_fraction': '0.1', 'valid_for_ms': 1200000, 'config_payoff_ratio_r': 1.5, 'config_has_fraction': False}
```

### Targeted Test Run

```text
runTests files:
- tests/domains/decision_making/test_intent_builder_validators.py
- tests/domains/decision_making/test_intent_builder_payload_contract.py
- tests/domains/decision_making/test_intent_builder_reservation_cleanup.py
- tests/domains/execution_position/test_trade_intent_open_intake.py
- tests/unit/llm/test_llm_intent_builder_contract.py
- tests/unit/decision_making/test_fail_closed_config.py
- tests/integration/test_ep01_4_tif_plumbing.py
- tests/bootstrap/test_schema_registry_activation.py

Result:
<summary passed=14 failed=1 />

Failure:
tests/domains/execution_position/test_trade_intent_open_intake.py::test_live_execpos_open_path_does_not_bypass_typed_intake
E   ValueError: Missing cleanup ownership config: set execution.fsm_periodic_cleanup_enabled or trading.execution.fsm_periodic_cleanup_enabled
```

### Additional Log Searches

```text
grep ORDER_INTENT in logs/order_log_v1.jsonl -> no matches
grep TRADE_INTENT_PROPOSED in logs/** -> no matches
grep TRADE_INTENT_PROPOSED in data/** -> no matches
grep TRADE_INTENT_PROPOSED in ops/** -> multiple matches, sample inspected at ops/wal/2026-04-20.jsonl:20864
```

## What Is Proven

- The active decision_making TradeIntent hot path is StrategyGateway -> DecisionMaking core.facade -> IntentBuilder -> WAL -> EVT:TRADE_INTENT_PROPOSED.
- resolve_kelly_fraction is on the active hot path and reads a non-SSOT field.
- Live loaded KellyConfig has no fraction field.
- Current runtime payload still emits p = 0.75, payoff_ratio_r = 2.0, kelly_fraction = 0.1.
- Archived WAL contains those synthetic values in real TRADE_INTENT_PROPOSED rows.
- order_log_v1 projection on the current builder surface does not include those fields.
- Several tests mask or normalize the non-SSOT/synthetic behavior instead of guarding against it.

## What Remains Unproven

- Whether any non-execution consumer reads polluted WAL fields as decision inputs.
- Whether historical replay, ML, or RL artifacts require quarantine or relabeling.
- Whether a truthful upstream probability producer for p already exists outside this package but is being discarded here.
- Whether a minimal metadata-only repair is fully safe for all downstream forensic consumers without a coordinated replay-consumer audit.

## Recommended Next Package If Repair Is Needed

Primary next package:
- decision_making intent boundary provenance repair

Smallest safe repair plan for that package:
- remove the silent Kelly fraction fallback or fail closed when fraction cannot be truthfully resolved
- stop emitting synthetic p and payoff_ratio_r literals unless a truthful existing source is wired
- update masking tests so they do not inject non-SSOT decision.kelly.fraction
- add regression tests that prove provenance against live ConfigLoader output

Follow-up package after boundary repair:
- replay and provenance consumer audit for WAL readers, especially any neocortex or offline training path that trusts TRADE_INTENT_PROPOSED metadata

Hard stop respected:
- no new probability estimator
- no sizing redesign
- no risk budget tuning
- no WAL rewrite
