# CURRENT_EXECUTION_CHAIN — llm_microstructure runtime path

This document details the exact execution chain from registered intent/command through the Finite State Machine (FSM) down to the real exchange adapter, classifying each component according to its runtime behavior.

---

## 1. Trace Overview

| Component | Path / Reference | Classification | Description |
| :--- | :--- | :--- | :--- |
| **Strategy Entrypoint** | [LlmMicrostructurePlugin](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/strategies/plugins/llm_microstructure.py#L32) | **STUB / SHADOW** | Registered solely to satisfy StrategyRuntime registration checks. It has no FSM listeners or decision logic. Decisions are driven via IPC into `shadow_telemetry`. |
| **Ingress Influx Bridge** | [LLMIntentIngressBridge](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/shadow_telemetry/main_bridge.py#L368) | **REAL_EXTERNAL_RUNTIME** | A TCP socket server listening for JSONL commands (`eze_open`, etc.) and emitting FSM events. |
| **Command Mapping** | [register_llm_command_mapper](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/shadow_telemetry/main_bridge.py#L722) | **REAL_EXTERNAL_RUNTIME** | Maps `CMD:LLM_INTENT_SUBMIT_V1` and `CMD:LLM_POSITION_CLOSE_V1` to `CMD:EXTERNAL_OPEN_REQUEST_V1` and `CMD:EXTERNAL_POSITION_CLOSE_REQUEST_V1`. |
| **FSM Intake Handler** | [ExecPosFSM._on_external_open_request](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/execution_position/fsm.py#L950) | **REAL_EXTERNAL_RUNTIME** | Listens to `CMD:EXTERNAL_OPEN_REQUEST_V1` and delegates processing to `_intent_router.on_external_open_request()`. |
| **Policy/Gate Chain** | [intent_router.py:on_external_open_request](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/execution_position/flows/open/intent_router.py#L409) | **REAL_EXTERNAL_RUNTIME** | Checks: 1. `intent_id` present, 2. `source` matches `"external_llm"`, 3. `order_type` is `"LIMIT"`, 4. `tif` valid, 5. `price` present, 6. `valid_for_ms` valid. Generates `CMD:OPEN` and calls `FSM.handle()`. |
| **FSM Execution Handler** | [OpenExecutor.execute_open](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/execution_position/flows/open/open_executor.py#L453) | **REAL_EXTERNAL_RUNTIME** | Performs sizing normalizations, checks symbol tidy gates, and calls adapter placement methods. |
| **Adapter Construction** | [AdapterInitMixin._initialize_adapter](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/execution_position/adapters/adapter_init.py#L44) | **REAL_EXTERNAL_RUNTIME** | Loads credentials from `config.binance_api.testnet` and instantiates `BinanceAdapter`. Falls back to simulation (`shadow_mode=True`) if credentials are absent. |
| **Order Submit Method** | [BinanceAdapter.place_limit_entry](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/adapters/binance_adapter.py#L1537) | **REAL_EXTERNAL_RUNTIME** | Calls `_request` to POST `/fapi/v1/order`. |
| **Exchange Response Model**| [ExchangeOrderResponse](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/vfoundation/core/adapters/base.py) | **REAL_EXTERNAL_RUNTIME** | Dataclass representing standard exchange responses. |
| **Lifecycle Recorder** | [wal.py](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/vfoundation/dr/wal.py) / [CsvRecorder](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/data_recorder/recorder.py) | **REAL_EXTERNAL_RUNTIME** | Appends order lifecycle states to WAL events. |
| **Cancel/Close Path** | [BinanceAdapter.cancel_order](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/adapters/binance_adapter.py#L646) | **REAL_EXTERNAL_RUNTIME** | POST `/fapi/v1/order` (DELETE method equivalent on Binance API). |
| **Reconciliation Path** | [ExecPosFSM.reconcile](file:///C:/Users/wekab/Music/Phenix-p42a-real-testnet-bridge/apps/reference/domains/execution_position/fsm.py) | **REAL_EXTERNAL_RUNTIME** | Fetches open positions and orders on startup/loop to align state. |

---

## 2. Inferences & Path Gaps

1. **Testnet Simulation (Shadow Fallback)**:
   If credentials (API key/secret) are missing in the testnet config, `AdapterInitMixin` falls back to `self.shadow_mode = True` and keeps `self.adapter = None`. This means the system continues running in a simulated shadow state rather than crashing, but *cannot* verify external exchange execution.
2. **Double Guarding**:
   FSM safety checks strictly block mainnet execution. `BinanceAdapter` uses `rest_url` which points to `https://testnet.binancefuture.com` when testnet configuration is active.
3. **Idempotency Protection**:
   `idempotent_key` is mapped from the incoming payload and passed to `newClientOrderId` to prevent double-submitting orders over the network.
