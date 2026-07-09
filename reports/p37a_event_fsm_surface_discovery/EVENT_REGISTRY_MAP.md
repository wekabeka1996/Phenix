# Event Registry Map

We mapped the event and command registries of the Phenix codebase.

## 1. Single Source of Truth (SSOT): Verb Registry
- **File**: `apps/reference/dictionaries/verb_registry_v1.yaml`
- **Function**: Declares all verbs alongside their operational prefixes, owner domains, schema paths, and lifecycle statuses.
- **Prefixes**:
  - `EVT:` (Events): E.g., `EVT:ACCOUNT_UPDATE_RECEIVED`, `EVT:TRADE_EXECUTED`.
  - `CMD:` (Commands): E.g., `CMD:OPEN`, `CMD:CLOSE`.
  - `DEC:` (Decisions): E.g., `DEC:OPEN`, `DEC:CLOSE`.
  - `ERR:` (Errors): E.g., `ERR:OPEN`.

## 2. Python Event Names Mapping
- **File**: `apps/reference/domains/execution_position/contract_layer/event_names.py`
- **Constants**: Maps events to Python constants (e.g. `CMD_OPEN = "CMD:OPEN"`) and publishes `OWNED_EVENT_NAMES` tuple for contract validation checks.

## 3. Event Schema Definitions
- **Location**: `apps/reference/schemas/`
- **Function**: Houses the draft schemas (e.g., `order_logger_v1.json`, `startup_seed_status_v1.json`) to enforce contract compliance on write or emit.
