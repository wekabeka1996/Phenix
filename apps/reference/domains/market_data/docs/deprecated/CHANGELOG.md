# Market Data Changelog

## Overview
**Current Version:** 1.1.0 (Forensic Audit)
**Status:** ⚠️ **UNDER REPAIR** (Previously "Production Ready")

This changelog tracks the evolution of the `market_data` domain, from its initial REST-based implementation to the current Multi-Process Proxy architecture, and the recent Forensic Audit findings.

---

## Version History

### [1.1.0] - 2026-01-27 (Forensic Audit)
**Release Type:** Forensic Correction & Risk Disclosure
**Focus:** Transparency regarding architectural risks identified during the Principal Architect audit.

#### 🚨 Critical Findings
-   **Memory Leak:** `WebSocketAggregator` identified as having unbounded memory growth (`seen_trade_ids`).
-   **Data Loss Risk:** `BarAggregator` strict Out-of-Order drop logic identified as dangerous for HFT execution.
-   **Legacy Debt:** Explicitly marked `MarketDataConnector` as "Zombie Code".

#### 🔧 Changes
-   **Docs**: Complete rewrite of documentation to reflect "Reality vs Promise".
-   **Architecture**: Officially deprecated Single-Process Mode.

---

### [1.0.0] - 2024-01-15 (Legacy Baseline)
**Release Type:** Major Release
**Note:** This version was optimistically marked as "production ready" based on happy-path testing.

#### Added
-   **Hybrid Data Ingestion**: REST + WebSocket.
-   **Feature Calculation**: OBI and TFI features.
-   **Bar Aggregation**: Initial implementation of 1m/5m bars.
-   **Macro Sync**: Anchor symbol support.

#### Characteristics
-   **Test Coverage**: 100% (Happy Path).
-   **Latency**: < 2s.

---

### [0.9.0] - 2024-01-10 (Beta)
**Release Type:** Beta
-   Initial WebSocketAggregator implementation.
-   Basic Event emission (`EVT:MARKET_TICK_RECEIVED`).
-   Environment-based configuration.

---

### [0.8.0] - 2024-01-05 (Alpha)
**Release Type:** Alpha
-   Basic MarketDataConnector (REST only).
-   BinanceAdapter abstraction.

---

## Migration Guide (1.0.0 -> 1.1.0)

### For Safety
1.  **Enforce Process Isolation**: Ensure `market_data.mode` is set to `proxy`.
2.  **Mitigate Leaks**: Apply strict Docker memory limits until the patch is merged.
3.  **Monitor Freshness**: Rely on `/health` endpoint for "Blackhole" detection.

### Breaking Changes
-   Legacy `market_ws_client.py` is slated for deletion.
-   `MarketDataConnector` class is deprecated.
