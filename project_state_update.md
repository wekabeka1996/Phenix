# Aurora Core FSM - Architectural Baseline State

## [System Overview]
The system, primarily known as **Aurora Core FSM**, is a Federated State Machine architecture designed for algorithmic cryptocurrency trading on Binance Futures. It utilizes real-time order book data, asynchronous event-driven pipelines, and a sophisticated multi-domain layout (located entirely in `apps/reference/domains`) to calculate risk, extract features, and execute trades. The structural backbone leverages **vFoundation**, providing Meta-FSM capabilities, dynamic routing, and Disaster Recovery (WAL, snapshots), while event schemas are governed strictly by global registries located in `apps/reference/dictionaries`. Currently, the system is configured to run in a `hybrid_live_data_testnet_exec` mode.

## [Architecture Topology]

```mermaid
C4Context
    title System Context diagram for Aurora Core FSM

    Person(admin, "Principal Architect/Trader", "Monitors and directs system")
    
    System_Boundary(base, "vFoundation Core Platform") {
        System_Boundary(app, "Aurora Reference App (apps/reference/domains)") {
            Container(market_data, "Market Data Domain", "Trio/Websockets", "Ingests live order flows and Binance depth events")
            Container(feature_eng, "Feature Engineering", "Pandas/NumPy", "Generates indicators and signals")
            Container(neocortex, "Neocortex", "Python", "Multi-agent dynamic decision making")
            Container(risk_mgmt, "Risk Management", "Python", "Validates dynamic limits (CVaR, inventory)")
            Container(execution, "Execution & Position FSM", "Python (FSM)", "Places/manages/cancels orders & handles brackets")
        }
        Container(dictionaries, "Dictionaries & Event Registry", "YAML", "Central ontology defining verbs, schemas (e.g., verb_registry_v1.yaml)")
    }

    SystemExt(binance, "Binance API", "Mainnet / Testnet Futures")
    
    Rel(binance, market_data, "Streams order book data (WebSocket)")
    Rel(market_data, feature_eng, "Parsed market ticks/bars")
    Rel(feature_eng, neocortex, "Signals & Features")
    Rel(neocortex, risk_mgmt, "Proposed orders")
    Rel(risk_mgmt, execution, "Approved trades")
    Rel(execution, binance, "Executes API calls (REST/WS)")
    Rel(app, dictionaries, "Validates message ontology during inter-domain routing")
```

## [Tech Stack & Dependencies]
- **Language**: Python (leveraging async/await patterns heavily)
- **Core Framework**: **vFoundation** (acting as FSM-LLM Federated Modular Architecture base)
- **Concurrency Frameworks**: `trio` (async operations) and `fastapi` for metrics / API.
- **Data Engineering**: `pandas` >=2.0.0, `numpy` >=1.24.0
- **Serialization**: `orjson` (fast JSON parsing), `pydantic` v2
- **Config & Ontology**: `PyYAML`, `dotenv`, and centralized YAML verb dictionaries (`apps/reference/dictionaries`)
- **Observability**: `prometheus_client`

## [Hardware & Infrastructure Constraints]
`[REQUIRES USER INPUT: Define local VRAM/RAM/Compute limits here]`

## [Critical Modules (Red Lines)]
These paths manipulate financial state or live orders and are strictly protected.
**[HITL REQUIRED - NO AUTO-COMMITS]**
- `apps/reference/domains/execution_position/fsm.py` (Core FSM Orchestrator)
- `apps/reference/domains/execution_position/fsm_open.py`
- `apps/reference/domains/execution_position/fsm_manage.py`
- `apps/reference/domains/execution_position/fsm_close.py`
- `apps/reference/domains/execution_position/order_guardian.py`
- `apps/reference/domains/execution_position/exposure_guard.py`
- `apps/reference/domains/risk_management/*`

## [Current Technical Debt / Focus]
- **Architecture Synchronization**: Realignment of the system's focus towards `apps/reference/domains` as the sole locus of business logic, explicitly sunsetting/ignoring loosely coupled or legacy implementations like `alysha_core`.
- **Execution Consolidation**: There's ongoing structural audit focus on logic duplication and race conditions within `execution_position` and `order_guardian`, maximizing the native `vFoundation` DR/WAL capabilities for predictability.
- **Async/Sync Complexity**: Potential mixing of async methods in synchronous flows within the FSM pipelines, needing structural validation against the core concurrency practices of `vFoundation`.
