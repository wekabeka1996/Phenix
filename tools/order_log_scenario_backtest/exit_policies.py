from __future__ import annotations

from bisect import bisect_left, bisect_right
from decimal import Decimal
from pathlib import Path
from typing import Any
import json

from tools.analysis.order_reconstruction_tp_sl_common import iso_utc, stringify, to_float, to_int

from .config_loader import resolve_asset_config
from .models import CanonicalEntry, ExitEvent, ScenarioRuntime

DEFAULT_REPLAY_HORIZON_MS = 24 * 60 * 60 * 1000


def _ceil_to_minute_close_ts(ts_ms: int) -> int:
    remainder = ts_ms % 60000
    if remainder == 59999:
        return ts_ms
    return ((ts_ms // 60000) + 1) * 60000 - 1


def _tp_sl_horizon_end(entry: CanonicalEntry) -> int:
    return entry.entry_ts_ms + DEFAULT_REPLAY_HORIZON_MS


def _decimal(value: float | int | str) -> Decimal:
    return Decimal(str(value))


def _fee_roi_pct(entry: CanonicalEntry, runtime: ScenarioRuntime) -> float:
    fees = runtime.config.get("fees") or {}
    open_fee_bps = float(fees.get("open_fee_bps") or 0.0)
    close_fee_bps = float(fees.get("close_fee_bps") or 0.0)
    return (open_fee_bps + close_fee_bps) * entry.leverage / 100.0


def _gross_price_move_pct(entry: CanonicalEntry, exit_price: float) -> float:
    if entry.side.upper() == "BUY":
        return (exit_price - entry.entry_price) / entry.entry_price * 100.0
    return (entry.entry_price - exit_price) / entry.entry_price * 100.0


def _trade_metrics(
    entry: CanonicalEntry,
    runtime: ScenarioRuntime,
    exit_event: ExitEvent,
) -> dict[str, Any]:
    if exit_event.price is None or exit_event.ts_ms is None:
        return {
            "exit_ts_ms": "",
            "exit_time_iso": "",
            "exit_price": "",
            "holding_minutes": "",
            "gross_pnl_roi_pct": "",
            "fee_roi_pct": "",
            "net_pnl_roi_pct": "",
            "status": "unresolved",
        }
    gross_price_move_pct = _gross_price_move_pct(entry, exit_event.price)
    gross_pnl_roi_pct = gross_price_move_pct * entry.leverage
    fee_roi_pct = _fee_roi_pct(entry, runtime)
    net_pnl_roi_pct = gross_pnl_roi_pct - fee_roi_pct
    if net_pnl_roi_pct > 0:
        status = "win"
    elif net_pnl_roi_pct < 0:
        status = "loss"
    else:
        status = "flat"
    return {
        "exit_ts_ms": exit_event.ts_ms,
        "exit_time_iso": iso_utc(exit_event.ts_ms) or "",
        "exit_price": round(exit_event.price, 8),
        "holding_minutes": round((exit_event.ts_ms - entry.entry_ts_ms) / 60000.0, 6),
        "gross_pnl_roi_pct": round(gross_pnl_roi_pct, 8),
        "fee_roi_pct": round(fee_roi_pct, 8),
        "net_pnl_roi_pct": round(net_pnl_roi_pct, 8),
        "status": status,
    }


def compute_tpsl_geometry(entry: CanonicalEntry, runtime: ScenarioRuntime) -> dict[str, Any]:
    asset_cfg = resolve_asset_config(runtime.config, entry.symbol)
    regime_tpsl = asset_cfg.get("regime_tpsl") or {}
    if not asset_cfg or not regime_tpsl:
        return {"error": "asset_config_missing"}
    if not bool(regime_tpsl.get("enabled", False)):
        return {"error": "regime_tpsl_disabled"}
    if str(regime_tpsl.get("mode") or "") != "pct_mult":
        return {"error": "unsupported_tpsl_mode"}

    sl_pct_raw = asset_cfg.get("sl_pct")
    tp_low_ratio_raw = asset_cfg.get("tp_low_ratio")
    sl_mult_map = dict(regime_tpsl.get("sl_mult") or {})
    tp_mult_map = dict(regime_tpsl.get("tp_mult") or {})
    if sl_pct_raw is None or tp_low_ratio_raw is None:
        return {"error": "required_tpsl_inputs_missing"}
    if "DEFAULT" not in sl_mult_map or "DEFAULT" not in tp_mult_map:
        return {"error": "default_multiplier_missing"}

    regime_key = entry.regime_at_entry or "DEFAULT"
    sl_pct_eff = _decimal(sl_pct_raw) * _decimal(sl_mult_map.get(regime_key, sl_mult_map["DEFAULT"]))
    tp_rr_eff = _decimal(tp_low_ratio_raw) * _decimal(tp_mult_map.get(regime_key, tp_mult_map["DEFAULT"]))
    tp_dist_pct = sl_pct_eff * tp_rr_eff
    entry_price = _decimal(entry.entry_price)
    side = entry.side.upper()
    if side == "BUY":
        stop_price = entry_price * (Decimal("1") - sl_pct_eff)
        target_price = entry_price * (Decimal("1") + tp_dist_pct)
    elif side == "SELL":
        stop_price = entry_price * (Decimal("1") + sl_pct_eff)
        target_price = entry_price * (Decimal("1") - tp_dist_pct)
    else:
        return {"error": "unsupported_side"}

    min_sl_pct = _decimal(regime_tpsl.get("min_sl_pct", 0.003))
    max_sl_pct = _decimal(regime_tpsl.get("max_sl_pct", 0.06))
    min_tp_rr = _decimal(regime_tpsl.get("min_tp_rr", 0.3))
    max_tp_rr = _decimal(regime_tpsl.get("max_tp_rr", 3.0))
    min_dist_bps = int(regime_tpsl.get("min_dist_bps", 15))
    guardrail_ctx: dict[str, Any] = {
        "mode": "pct_mult",
        "regime_used": regime_key,
        "sl_pct_eff_pre": float(sl_pct_eff),
        "tp_rr_eff_pre": float(tp_rr_eff),
    }

    if side == "BUY":
        sl_dist_pct = (entry_price - stop_price) / entry_price
        tp_dist_pct = (target_price - entry_price) / entry_price
    else:
        sl_dist_pct = (stop_price - entry_price) / entry_price
        tp_dist_pct = (entry_price - target_price) / entry_price
    if sl_dist_pct <= 0 or tp_dist_pct <= 0:
        return {"error": "invalid_tpsl_direction"}

    if sl_dist_pct < min_sl_pct:
        sl_dist_pct = min_sl_pct
        guardrail_ctx["guardrail_sl_clamp"] = "min"
    elif sl_dist_pct > max_sl_pct:
        sl_dist_pct = max_sl_pct
        guardrail_ctx["guardrail_sl_clamp"] = "max"

    current_rr = tp_dist_pct / sl_dist_pct
    if current_rr < min_tp_rr:
        tp_dist_pct = sl_dist_pct * min_tp_rr
        current_rr = min_tp_rr
        guardrail_ctx["guardrail_rr_clamp"] = "min"
    elif current_rr > max_tp_rr:
        tp_dist_pct = sl_dist_pct * max_tp_rr
        current_rr = max_tp_rr
        guardrail_ctx["guardrail_rr_clamp"] = "max"

    min_dist_dec = _decimal(min_dist_bps) / Decimal("10000")
    if sl_dist_pct < min_dist_dec:
        return {"error": "sl_below_min_dist_bps"}
    if tp_dist_pct < min_dist_dec:
        return {"error": "tp_below_min_dist_bps"}

    if side == "BUY":
        stop_price = entry_price * (Decimal("1") - sl_dist_pct)
        target_price = entry_price * (Decimal("1") + tp_dist_pct)
    else:
        stop_price = entry_price * (Decimal("1") + sl_dist_pct)
        target_price = entry_price * (Decimal("1") - tp_dist_pct)

    guardrail_ctx["sl_pct_eff"] = float(sl_dist_pct)
    guardrail_ctx["tp_pct_eff"] = float(tp_dist_pct)
    guardrail_ctx["rr_eff"] = float(current_rr)
    return {
        "tp_price": float(target_price),
        "sl_price": float(stop_price),
        "context": guardrail_ctx,
    }


def tp_sl_only_exit(entry: CanonicalEntry, runtime: ScenarioRuntime) -> tuple[ExitEvent, dict[str, Any]]:
    geometry = compute_tpsl_geometry(entry, runtime)
    if "error" in geometry:
        return (
            ExitEvent(
                reason="tpsl_unresolved",
                ts_ms=None,
                price=None,
                source="tpsl_config",
                support_quality=geometry["error"],
            ),
            {"tp_price": "", "sl_price": "", "tpsl_context": geometry},
        )

    series = runtime.candles_by_symbol.get(entry.symbol)
    if series is None:
        return (
            ExitEvent(
                reason="tpsl_unresolved",
                ts_ms=None,
                price=None,
                source="candles",
                support_quality="symbol_candles_missing",
            ),
            {"tp_price": geometry["tp_price"], "sl_price": geometry["sl_price"], "tpsl_context": geometry.get("context")},
        )

    start_ts = _ceil_to_minute_close_ts(entry.entry_ts_ms)
    end_ts = _tp_sl_horizon_end(entry)
    start_idx = bisect_left(series.timestamps, start_ts)
    end_idx = bisect_right(series.timestamps, end_ts)
    tp_price = float(geometry["tp_price"])
    sl_price = float(geometry["sl_price"])

    for candle in series.rows[start_idx:end_idx]:
        if entry.side.upper() == "BUY":
            hit_tp = candle["high"] >= tp_price
            hit_sl = candle["low"] <= sl_price
        else:
            hit_tp = candle["low"] <= tp_price
            hit_sl = candle["high"] >= sl_price
        if hit_tp and hit_sl:
            return (
                ExitEvent(
                    reason="sl_first_ambiguous_intrabar",
                    ts_ms=int(candle["timestamp"]),
                    price=sl_price,
                    source="1m_candle_replay",
                    support_quality="sl_first_ambiguous_bar",
                ),
                {"tp_price": tp_price, "sl_price": sl_price, "tpsl_context": geometry.get("context")},
            )
        if hit_tp:
            return (
                ExitEvent(
                    reason="tp_hit",
                    ts_ms=int(candle["timestamp"]),
                    price=tp_price,
                    source="1m_candle_replay",
                    support_quality="high",
                ),
                {"tp_price": tp_price, "sl_price": sl_price, "tpsl_context": geometry.get("context")},
            )
        if hit_sl:
            return (
                ExitEvent(
                    reason="sl_hit",
                    ts_ms=int(candle["timestamp"]),
                    price=sl_price,
                    source="1m_candle_replay",
                    support_quality="high",
                ),
                {"tp_price": tp_price, "sl_price": sl_price, "tpsl_context": geometry.get("context")},
            )

    return (
        ExitEvent(
            reason="unresolved_at_horizon",
            ts_ms=None,
            price=None,
            source="1m_candle_replay",
            support_quality="no_tp_sl_hit",
        ),
        {"tp_price": tp_price, "sl_price": sl_price, "tpsl_context": geometry.get("context")},
    )


def load_sidecar_requests(runtime_root: Path) -> list[dict[str, Any]]:
    path = runtime_root / "trade_lifecycle.jsonl"
    requests: list[dict[str, Any]] = []
    if not path.exists():
        return requests
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            if payload.get("event_type") not in {
                "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
                "POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE",
            }:
                continue
            payload["_source_line"] = line_no
            requests.append(payload)
    return requests


def build_sidecar_request_index(requests: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    by_lifecycle_id: dict[str, list[dict[str, Any]]] = {}
    by_rid: dict[str, list[dict[str, Any]]] = {}
    by_client_order_id: dict[str, list[dict[str, Any]]] = {}
    by_order_id: dict[str, list[dict[str, Any]]] = {}
    by_symbol: dict[str, list[dict[str, Any]]] = {}

    for payload in requests:
        policy_context = payload.get("policy_context") or {}
        fill_correlation = (
            policy_context.get("fill_correlation")
            or payload.get("fill_correlation")
            or {}
        )
        lifecycle_id = stringify(payload.get("lifecycle_id")) or stringify(
            policy_context.get("lifecycle_id")
        ) or stringify(fill_correlation.get("lifecycle_id"))
        rid = stringify(fill_correlation.get("rid"))
        client_order_id = stringify(fill_correlation.get("client_order_id"))
        order_id = stringify(fill_correlation.get("order_id"))
        symbol = stringify(payload.get("symbol")) or stringify(policy_context.get("symbol"))
        if lifecycle_id:
            by_lifecycle_id.setdefault(lifecycle_id, []).append(payload)
        if rid:
            by_rid.setdefault(rid, []).append(payload)
        if client_order_id:
            by_client_order_id.setdefault(client_order_id, []).append(payload)
        if order_id:
            by_order_id.setdefault(order_id, []).append(payload)
        if symbol:
            by_symbol.setdefault(symbol, []).append(payload)

    for bucket in (by_lifecycle_id, by_rid, by_client_order_id, by_order_id, by_symbol):
        for key, values in bucket.items():
            values.sort(key=lambda item: to_int(item.get("request_ts_ms")) or to_int(item.get("ts_ms")) or 0)
            bucket[key] = values

    return {
        "lifecycle_id": by_lifecycle_id,
        "rid": by_rid,
        "client_order_id": by_client_order_id,
        "order_id": by_order_id,
        "symbol": by_symbol,
    }


def _pick_sidecar_request(
    entry: CanonicalEntry,
    runtime: ScenarioRuntime,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    audit = {
        "entry_id": entry.entry_id,
        "symbol": entry.symbol,
        "join_method": "none",
        "join_quality": "none",
        "join_delta_ms": "",
        "request_id": "",
        "request_ts_ms": "",
        "request_event_type": "",
        "trace_id": "",
        "source_line": "",
    }
    index = runtime.sidecar_request_index or {}

    for method, key in (
        ("lifecycle_id", entry.lifecycle_id),
        ("rid", entry.rid),
    ):
        candidates = (index.get(method) or {}).get(key) or []
        if candidates:
            chosen = candidates[0]
            request_ts_ms = to_int(chosen.get("request_ts_ms")) or to_int(chosen.get("ts_ms"))
            audit.update(
                {
                    "join_method": method,
                    "join_quality": "exact",
                    "join_delta_ms": abs((request_ts_ms or 0) - entry.entry_ts_ms),
                    "request_id": stringify(chosen.get("request_id")) or "",
                    "request_ts_ms": request_ts_ms or "",
                    "request_event_type": stringify(chosen.get("event_type")) or "",
                    "trace_id": stringify(chosen.get("trace_id")) or "",
                    "source_line": chosen.get("_source_line") or "",
                }
            )
            return chosen, audit

    for method in ("client_order_id", "order_id"):
        candidates = (index.get(method) or {}).get(entry.trade_id) or []
        if candidates:
            chosen = candidates[0]
            request_ts_ms = to_int(chosen.get("request_ts_ms")) or to_int(chosen.get("ts_ms"))
            audit.update(
                {
                    "join_method": method,
                    "join_quality": "exact",
                    "join_delta_ms": abs((request_ts_ms or 0) - entry.entry_ts_ms),
                    "request_id": stringify(chosen.get("request_id")) or "",
                    "request_ts_ms": request_ts_ms or "",
                    "request_event_type": stringify(chosen.get("event_type")) or "",
                    "trace_id": stringify(chosen.get("trace_id")) or "",
                    "source_line": chosen.get("_source_line") or "",
                }
            )
            return chosen, audit

    candidates = (index.get("symbol") or {}).get(entry.symbol) or []
    best = None
    best_delta = None
    horizon_end = _tp_sl_horizon_end(entry)
    for candidate in candidates:
        request_ts_ms = to_int(candidate.get("request_ts_ms")) or to_int(candidate.get("ts_ms"))
        if request_ts_ms is None:
            continue
        if request_ts_ms < entry.entry_ts_ms or request_ts_ms > horizon_end:
            continue
        delta = request_ts_ms - entry.entry_ts_ms
        if best is None or delta < best_delta:
            best = candidate
            best_delta = delta
    if best is not None:
        audit.update(
            {
                "join_method": "symbol_time",
                "join_quality": "bounded",
                "join_delta_ms": best_delta,
                "request_id": stringify(best.get("request_id")) or "",
                "request_ts_ms": to_int(best.get("request_ts_ms")) or to_int(best.get("ts_ms")) or "",
                "request_event_type": stringify(best.get("event_type")) or "",
                "trace_id": stringify(best.get("trace_id")) or "",
                "source_line": best.get("_source_line") or "",
            }
        )
        return best, audit
    return None, audit


def sidecar_only_exit(entry: CanonicalEntry, runtime: ScenarioRuntime) -> tuple[ExitEvent, dict[str, Any]]:
    request, audit = _pick_sidecar_request(entry, runtime)
    if request is None:
        return (
            ExitEvent(
                reason="sidecar_request_missing",
                ts_ms=None,
                price=None,
                source="trade_lifecycle",
                support_quality="unresolved",
            ),
            {"request_join_audit": audit},
        )
    request_ts_ms = to_int(request.get("request_ts_ms")) or to_int(request.get("ts_ms"))
    if request_ts_ms is None:
        return (
            ExitEvent(
                reason="sidecar_request_missing_timestamp",
                ts_ms=None,
                price=None,
                source="trade_lifecycle",
                support_quality="unresolved",
            ),
            {"request_join_audit": audit},
        )
    series = runtime.candles_by_symbol.get(entry.symbol)
    if series is None:
        return (
            ExitEvent(
                reason="sidecar_candle_missing",
                ts_ms=None,
                price=None,
                source="1m_candles",
                support_quality="unresolved",
            ),
            {"request_join_audit": audit},
        )
    next_candle_idx = bisect_right(series.timestamps, _ceil_to_minute_close_ts(request_ts_ms))
    if next_candle_idx >= len(series.rows):
        return (
            ExitEvent(
                reason="sidecar_next_candle_missing",
                ts_ms=None,
                price=None,
                source="1m_candles",
                support_quality="unresolved",
            ),
            {"request_join_audit": audit},
        )
    candle = series.rows[next_candle_idx]
    return (
        ExitEvent(
            reason="sidecar_close_requested",
            ts_ms=int(candle["timestamp"]),
            price=float(candle["open"]),
            source="sidecar_request_next_candle_open",
            support_quality="high",
        ),
        {"request_join_audit": audit},
    )


def materialize_trade_result(
    scenario_id: str,
    entry: CanonicalEntry,
    runtime: ScenarioRuntime,
    exit_event: ExitEvent,
    extras: dict[str, Any],
) -> dict[str, Any]:
    metrics = _trade_metrics(entry, runtime, exit_event)
    row = {
        "scenario_id": scenario_id,
        "entry_id": entry.entry_id,
        "lifecycle_id": entry.lifecycle_id,
        "rid": entry.rid,
        "symbol": entry.symbol,
        "side": entry.side,
        "strategy_id": entry.strategy_id,
        "entry_origin": entry.entry_origin,
        "regime_at_entry": entry.regime_at_entry,
        "entry_ts_ms": entry.entry_ts_ms,
        "entry_time_iso": entry.entry_time_iso,
        "entry_price": entry.entry_price,
        "qty": entry.qty,
        "leverage": entry.leverage,
        "exit_reason": exit_event.reason,
        "exit_source": exit_event.source,
        "support_quality": exit_event.support_quality,
        "tp_price": extras.get("tp_price", ""),
        "sl_price": extras.get("sl_price", ""),
        "allow_regime_flip_exits": extras.get("allow_regime_flip_exits", ""),
        "notes": "|".join(entry.notes),
    }
    row.update(metrics)
    return row
