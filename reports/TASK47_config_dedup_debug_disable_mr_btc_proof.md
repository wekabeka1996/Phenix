# TASK47-I — SSOT Dedup + Safe Debug Disables + MR Thresholds + BTC Dual-Strategy Proof

## Load / Merge Order (SSOT)

ConfigLoader reads primary YAML fragments in this order (then hydrates SSOT add-ons):
- `config/aurora/system.yaml`
- `config/aurora/trading.yaml`
- `config/aurora/regime.yaml`
- `config/aurora/domains.yaml`
- then: `config/aurora/instruments.yaml`, `config/aurora/strategies.yaml` + `config/aurora/strategies/*.yaml`, `config/aurora/aurora_instruments.yaml`

---

## G1 — Dedup (Crash-on-duplicate)

### What duplicates were found & removed (SSOT table)

| Path | Duplicated in | SSOT home now |
|---|---|---|
| `position_tracking.positions_stale_ttl_sec` | `system.yaml` + `domains.yaml` | `config/aurora/domains.yaml` |
| `trading.market_data.websocket_streams` | `system.yaml` + `trading.yaml` | `config/aurora/trading.yaml` |
| `config_version` | `system.yaml` + `regime.yaml` | `config/aurora/system.yaml` (regime removed) |
| `hotreload_whitelist` | `system.yaml` + `regime.yaml` | `config/aurora/regime.yaml` (system removed) |

### Enforcement

- Loader now fails fast if the same leaf-path exists in >1 YAML fragment (no whitelist, fail-closed).
- Implementation: `apps/reference/config_loader.py` (duplicate leaf-path flatten + `ConfigContractError`).

---

## G2 — Safe debug disables (2 timers)

### Flags (SSOT, with comments)

Added to `config/aurora/domains.yaml`:
- `debug.disable_positions_stale_gate` (T1)
- `debug.disable_daily_loss_limit` (T2)

### Runtime behavior

- If enabled (DEV/SHADOW only):
  - T1: AuroraBridge portfolio stale gate does not DEFER; it proceeds with OPEN and emits `EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE`.
  - T2: RiskManagement daily loss/drawdown gate does not block `is_trading_allowed`; it proceeds and emits `EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE`.
- Safety: if `trading.mode` is `live`/`production` and any debug disable is `true` → fail-closed at startup (`apps/reference/config_loader.py`).

---

## G3 — Lower MR thresholds (observable)

To make “mean-reversion regime” entries easier (avoid `Neutral signal score ...`):
- BTC per-instrument threshold multiplier lowered for `MEAN_REVERSION`:
  - `config/aurora/aurora_instruments.yaml` adds `BTCUSDT.regime_thresholds.MEAN_REVERSION: 0.5`
  - `BTCUSDT.allowed_regimes` now includes `MEAN_REVERSION`

Unit proof: `tests/domains/decision_making/test_task47_mr_threshold_allows_intent.py`.

---

## G4 — BTC dual-strategy proof (eligibility + intents)

- BTC is assigned to both strategies in SSOT:
  - `config/aurora/strategies.yaml` → `BTCUSDT: [aurora, mean_reversion]`
- Arbitration is now windowed (no permanent suppression on hybrid symbols):
  - `config/aurora/strategies.yaml` → `arbitration.window_ms: 1000`
  - `apps/reference/domains/decision_making/decision_making.py` commits arbitration only when emitting an intent (`decision_ts_ms` window).

Proof test: `tests/domains/decision_making/test_task47_btc_dual_strategy_intents.py`.

---

## Tests / Commands

Config validate:
`python tools/auroractl.py config-validate`

```text
CONFIG_OK
```

Targeted tests (TASK47 proofs):
`pytest -q tests/config/test_task47_config_dedup_and_debug_flags.py tests/config/test_task47_loader_effective_values.py tests/domains/position_tracking/test_task47_disable_stale_gate.py tests/domains/risk_management/test_task47_disable_daily_loss_limit.py tests/domains/decision_making/test_task47_mr_threshold_allows_intent.py tests/domains/decision_making/test_task47_btc_dual_strategy_intents.py`

```text
collected 10 items
10 passed in 0.48s
```

Full suite note:
- `pytest -q` currently hits an existing timeout in `tests/api/test_api_health.py` (30s timeout plugin); not caused by TASK47 changes.

---

## Changed / Added Files

**Code**
- `apps/reference/config_loader.py`
- `apps/reference/config_models.py`
- `apps/reference/main.py`
- `apps/reference/domains/risk_management/risk_management.py`
- `apps/reference/domains/decision_making/decision_making.py`
- `tools/auroractl.py`

**Config**
- `config/aurora/system.yaml`
- `config/aurora/trading.yaml` (SSOT kept; no duplicates)
- `config/aurora/regime.yaml`
- `config/aurora/domains.yaml`
- `config/aurora/strategies.yaml`
- `config/aurora/aurora_instruments.yaml`

**Tests**
- `tests/config/test_task47_config_dedup_and_debug_flags.py`
- `tests/config/test_task47_loader_effective_values.py`
- `tests/domains/position_tracking/test_task47_disable_stale_gate.py`
- `tests/domains/risk_management/test_task47_disable_daily_loss_limit.py`
- `tests/domains/decision_making/test_task47_mr_threshold_allows_intent.py`
- `tests/domains/decision_making/test_task47_btc_dual_strategy_intents.py`

