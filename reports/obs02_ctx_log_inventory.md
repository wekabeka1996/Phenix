# OBS-02-CTX — Log/WAL Inventory (generated 2026-01-12T14:43:40Z)

Scope patterns:
- `logs/**/*.jsonl`
- `ops/wal/**/*.jsonl`
- `reports/**/*.jsonl`

## Files
| file | lines | bad_json | time fields (top) | key fields present (top) |
|---|---:|---:|---|---|
| `/home/wekabeka/Музыка/Phenix/logs/aurora_events.jsonl` | 22 | 0 | `ts_ms` (22) | `symbol` (22), `clientOrderId` (22), `exchangeOrderId` (22) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-05.jsonl` | 6677 | 0 | `timestamp` (6448), `ts` (229), `ISO@timestamp` (6) | `pld.symbol` (110), `pld.tif` (73), `pld.order_type` (73) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-06.jsonl` | 19410 | 0 | `timestamp` (14844), `ts` (4566) | `pld.symbol` (3044), `pld.tif` (1781), `pld.order_type` (1781) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-07.jsonl` | 9728 | 0 | `timestamp` (7551), `ts` (2177) | `pld.symbol` (1444), `pld.tif` (880), `pld.order_type` (880) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-08.jsonl` | 2042 | 0 | `timestamp` (1659), `ts` (383), `ISO@timestamp` (54) | `pld.symbol` (210), `pld.tif` (187), `pld.order_type` (187) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-09.jsonl` | 11168 | 0 | `timestamp` (9562), `ts` (1606), `ISO@timestamp` (24) | `pld.symbol` (1054), `pld.tif` (972), `pld.order_type` (972) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-10.jsonl` | 16604 | 0 | `timestamp` (15164), `ts` (1440) | `pld.symbol` (960), `pld.tif` (885), `pld.order_type` (885) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-11.jsonl` | 13684 | 0 | `timestamp` (12614), `ts` (1070), `ISO@timestamp` (6) | `pld.symbol` (708), `pld.tif` (672), `pld.order_type` (672) |
| `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-12.jsonl` | 278 | 0 | `timestamp` (278), `pld.ts` (2) | `pld.symbol` (2) |
| `/home/wekabeka/Музыка/Phenix/reports/mr_chain_probe.jsonl` | 26 | 0 | _(none)_ | `symbol` (25), `tf_sec` (10) |
| `/home/wekabeka/Музыка/Phenix/reports/mr_restore_002_probe.jsonl` | 29 | 0 | `ts_ms` (29) | `symbol` (29), `tf_sec` (4) |

## Top Values (top-20 per key; merged root + `pld.*`)
### `/home/wekabeka/Музыка/Phenix/logs/aurora_events.jsonl`
- lines: `22`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | `ORDER_STATE_CHANGED` (22) |
| `op` | _(none)_ |
| `verb` | _(none)_ |
| `type` | _(none)_ |
| `status` | `EXPIRED` (18), `FILLED` (4) |
| `reason` | _(none)_ |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-05.jsonl`
- lines: `6677`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (6556), `DEC` (78), `CMD` (36), `ERR` (1) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (6442), `TRADE_INTENT_PROPOSED` (114), `OPEN` (74), `CLOSE` (36), `TEST` (5) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `reduce_only_trade_intent` (34), `MAX_HOLD_TIME_EXCEEDED` (2), `CONCENTRATION_BREACH` (1) |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-06.jsonl`
- lines: `19410`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (16366), `CMD` (1522), `ERR` (1263), `DEC` (259) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (14844), `OPEN` (3044), `TRADE_INTENT_PROPOSED` (1522) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `CONCENTRATION_BREACH` (1254), `SOFT_LIMIT_BELOW_CLIP_MIN` (9) |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-07.jsonl`
- lines: `9728`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (8284), `CMD` (717), `ERR` (559), `DEC` (168) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (7551), `OPEN` (1439), `TRADE_INTENT_PROPOSED` (733), `CLOSE` (5) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `CONCENTRATION_BREACH` (559), `MAX_HOLD_TIME_EXCEEDED` (5) |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-08.jsonl`
- lines: `2042`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (1733), `DEC` (161), `CMD` (88), `ERR` (6) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (1605), `OPEN` (193), `TRADE_INTENT_PROPOSED` (128), `TEST` (45), `CLOSE` (17) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `MAX_HOLD_TIME_EXCEEDED` (17), `DIRECTIONAL_RATIO_BREACH` (6) |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-09.jsonl`
- lines: `11168`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (10070), `CMD` (522), `DEC` (475), `ERR` (77) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (9538), `OPEN` (1049), `TRADE_INTENT_PROPOSED` (532), `TEST` (20), `CLOSE` (5) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `SOFT_LIMIT_BELOW_CLIP_MIN` (47), `DIRECTIONAL_RATIO_BREACH` (24), `CONCENTRATION_BREACH` (6), `MAX_HOLD_TIME_EXCEEDED` (5) |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-10.jsonl`
- lines: `16604`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (15644), `CMD` (480), `DEC` (405), `ERR` (75) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (15164), `OPEN` (960), `TRADE_INTENT_PROPOSED` (480) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `SOFT_LIMIT_BELOW_CLIP_MIN` (56), `DIRECTIONAL_RATIO_BREACH` (19) |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-11.jsonl`
- lines: `13684`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (12965), `CMD` (354), `DEC` (323), `ERR` (36) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (12608), `OPEN` (708), `TRADE_INTENT_PROPOSED` (357), `TEST` (5) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `DIRECTIONAL_RATIO_BREACH` (25), `SOFT_LIMIT_BELOW_CLIP_MIN` (11) |

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-12.jsonl`
- lines: `278`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | `EVT` (278) |
| `verb` | `ACCOUNT_UPDATE_RECEIVED` (275), `EVT:TRADE_EXECUTED` (2), `EVT:ACCOUNT_UPDATE_RECEIVED` (1) |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | _(none)_ |

### `/home/wekabeka/Музыка/Phenix/reports/mr_chain_probe.jsonl`
- lines: `26`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | `EVT:MARKET_TICK_FORWARDED` (1) |
| `op` | _(none)_ |
| `verb` | _(none)_ |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | `tf_sec 0 != 180` (15) |

### `/home/wekabeka/Музыка/Phenix/reports/mr_restore_002_probe.jsonl`
- lines: `29`; bad_json_lines: `0`
| key | top-20 values |
|---|---|
| `event` | _(none)_ |
| `op` | _(none)_ |
| `verb` | _(none)_ |
| `type` | _(none)_ |
| `status` | _(none)_ |
| `reason` | _(none)_ |

## WAL Presence Checks
These are counts of `verb` values found in `ops/wal/**/*.jsonl`.

### Bars
- `BAR_CLOSED`: `0`
- `EVT:BAR_CLOSED`: `0`
- `EVT:BAR_CLOSED_V1`: `0`

### Strategy / Decision SSOT
- `CMD:PROCESS_STRATEGY`: `0`
- `PROCESS_STRATEGY`: `0`
- `TRADE_INTENT_PROPOSED`: `3866`
- `TRADE_INTENT_REJECTED`: `0`
- `STRATEGY_SIGNAL_PRODUCED`: `0`
- `DECISION_TRACE_EMITTED`: `0`

### Orders (for time-to-fill)
- `OPEN`: `7467`
- `CLOSE`: `63`
- `ORDER_PLACED`: `0`
- `ORDER_ACK`: `0`
- `ORDER_FILL`: `0`
- `ORDER_STATE_CHANGED`: `0`
- `ORDER_REJECTED`: `0`

## Example Lines (structure preserved; best-effort redaction)
### `/home/wekabeka/Музыка/Phenix/logs/aurora_events.jsonl`
```json
{"avg_fill_price": "42000.00", "clientOrderId": "ENTRY_BTC_123", "event": "ORDER_STATE_CHANGED", "exchangeOrderId": "12345678", "filled_qty": "0", "idempotent_key": "idem_key_123", "qty": "0.01", "rid": "test_rid_123", "status": "EXPIRED", "symbol": "BTCUSDT", "ts_ms": 1768225683702, "why": "MAKER_ONLY_REJECT"}
```

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-05.jsonl`
```json
{"_hash": "<hex:redacted>", "_prev": "<hex:redacted>", "corr_id": null, "data_ref": ["margin_first_ok"], "dst": "bridge", "idempotent_key": null, "intent": "PROPOSAL", "key": null, "link_ack_id": null, "link_fill_id": null, "mode": "live", "mode_contract": null, "oco_group_id": null, "op": "EVT", "parent_client_order_id": null, "parent_span_id": null, "pld": {"dto_version": "1.0.0", "idempotent_key": "94d05bf5-d1da-43c0-952b-58d0575ab4ef", "instrument": "BTCUSDT", "order": {"price": "93366.0", "price_ref": "93366.0", "qty": "0.003", "reduce_only": false}, "p": "0.75", "payoff_ratio_r": "2.0", "rid": "031c6801-d3b0-4e1d-acd8-2415dc4a1b60", "risk_budget": {"session_cvar95_max_bps": "200", "trade_cvar95_max_bps": "100"}, "schema_ref": "...", "side": "buy", "size": {"kelly_fraction": "0.1", "notional_cap_usd": "280.0980"}, "strategy": "aurora", "tca_budget": {"max_latency_ms": 500, "max_slippage_bps": "10"}, "valid_for_ms": 5000, "why": ["margin_first_ok"]}, "rid": "031c6801-d3b0-4e1d-acd8-2415dc4a1b60", "sig": "<redacted>", "span_id": "5fa7fdb6493846a3b4805f1c8f8463e3", "src": "decision_making", "ts": 1767624755623, "ttl_ms": 2000, "v": 1, "verb": "TRADE_INTENT_PROPOSED", "why": "trade_intent", "why_explain_ref": null}
```

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-05.jsonl`
```json
{"_hash": "<hex:redacted>", "_prev": "<hex:redacted>", "corr_id": null, "data_ref": [], "dst": "decision_making", "idempotent_key": null, "intent": null, "key": null, "link_ack_id": null, "link_fill_id": null, "mode": "live", "mode_contract": null, "oco_group_id": null, "op": "ERR", "parent_client_order_id": null, "parent_span_id": null, "pld": {"idempotent_key": "3f29514b-d79a-4767-9a9a-ec17a315bafe", "reason": "CONCENTRATION_BREACH", "requested_notional": "-3523.13052", "side": "SELL", "stale_sec": 0, "symbol": "ETHUSDT"}, "rid": "aurora_ETHUSDT_1767657269634", "sig": "<redacted>", "span_id": "bded954d152f4dc3adccdc6e38fe6e55", "src": "execution_position", "ts": 1767657269642, "ttl_ms": 2000, "v": 1, "verb": "OPEN", "why": "exposure_fail_closed_concentration_breach", "why_explain_ref": null}
```

### `/home/wekabeka/Музыка/Phenix/reports/mr_chain_probe.jsonl`
```json
{"raw": "2026-01-09 01:47:58,239 - apps.reference.domains.decision_making.mean_reversion_handler.MRHandler - WARNING - MR rejecting features for XRPUSDT: tf_sec 0 != 180", "reason": "tf_sec 0 != 180", "source": "mr_reject", "symbol": "XRPUSDT"}
```

### `/home/wekabeka/Музыка/Phenix/ops/wal/2026-01-06.jsonl`
```json
{"_hash": "<hex:redacted>", "_prev": "<hex:redacted>", "dst": "any", "op": "EVT", "pld": {"positions": [], "totalCrossWalletBalance": "781.23708833", "totalUnrealizedProfit": "0E-8", "totalWalletBalance": "781.23708833", "updateTime": 1767657601771}, "rid": "2c3b291e-2133-42d0-9edd-75c7978dcee0", "src": "fsm_core", "timestamp": 1767657601.7721126, "verb": "ACCOUNT_UPDATE_RECEIVED"}
```

## Quick Findings / Holes
- `ops/wal/**/*.jsonl` currently contains **no BAR_CLOSED**-like records (see WAL Presence Checks).
- `TRADE_INTENT_PROPOSED` exists in WAL, but symbol identity sometimes lives under `pld.instrument` (not `pld.symbol`) → parser hole.
- WAL uses mixed time fields (`ts` in ms vs `timestamp` float seconds) depending on producer → normalize for SSOT parsing.
