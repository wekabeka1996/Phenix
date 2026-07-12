# Patch Diff

## FACTS

Commits before reports:

- `8919f643` contract, sizing adapter, registry, and endpoint config;
- `fb15589a` HTTP/TCP/main-bridge transport integration;
- `fdb19ef8` focused authority/sizing/transport tests.

Exact changed implementation/test files:

- `apps/reference/domains/shadow_telemetry/agent_trade_intent_v2.py`
- `apps/reference/domains/shadow_telemetry/main.py`
- `apps/reference/domains/shadow_telemetry/main_bridge.py`
- `apps/reference/config/domains/shadow_telemetry.py`
- `apps/reference/dictionaries/verb_registry_v1.yaml`
- `config/aurora/domains.yaml`
- `tests/domains/shadow_telemetry/test_agent_trade_intent_v2.py`
- `tests/domains/shadow_telemetry/test_main_bridge.py`
- `tests/config/test_shadow_telemetry_contracts.py`

No Cockpit, provider, execution-position, FSM, adapter, sizing helper, instrument business config, or Testnet source changed.

## INFERENCES

- Changes are additive at ingress and reuse the existing execution command boundary.

## ASSUMPTIONS

- Reports are committed in one final documentation commit.

## UNKNOWNS

- Final branch SHA is the report commit containing this package.

