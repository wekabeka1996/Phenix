from __future__ import annotations

import json
import logging
import hashlib
import subprocess
import shutil
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

LOG = logging.getLogger(__name__)


def _repo_root() -> Path:
    # backtest_engine/ -> repo root
    return Path(__file__).resolve().parents[1]


def _safe_git_sha() -> Optional[str]:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_repo_root()),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out or None
    except Exception:
        return None


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(
        _to_jsonable(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _hash_file_sha256(path: Path) -> Optional[str]:
    try:
        if not path.exists() or not path.is_file():
            return None
        return _sha256_hex(path.read_bytes())
    except Exception:
        return None


def _collect_config_files() -> list[dict[str, Any]]:
    base = _repo_root() / "config" / "aurora"
    candidates = [
        base / "system.yaml",
        base / "trading.yaml",
        base / "regime.yaml",
        base / "domains.yaml",
        base / "instruments.yaml",
        base / "strategies.yaml",
        base / "observability.yaml",
        base / "strategies" / "aurora.yaml",
    ]
    out: list[dict[str, Any]] = []
    for p in candidates:
        h = _hash_file_sha256(p)
        if h is None:
            continue
        try:
            rel = p.resolve().relative_to(_repo_root().resolve())
            rel_str = str(rel)
        except Exception:
            rel_str = str(p)
        out.append({"path": rel_str.replace('\\\\', '/'), "sha256": h})
    out.sort(key=lambda x: str(x.get("path") or ""))
    return out


def _get_nested(d: Any, path: list[str]) -> Any:
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _fail(msg: str) -> None:
    raise RuntimeError(msg)


def _config_dir_from_runtime_config(config: Any) -> Path:
    """Fail-closed: resolve config directory used for this run."""
    # Pydantic AuroraConfig path
    try:
        rt = getattr(getattr(getattr(config, "system_meta", None), "runtime", None), "config_dir", None)
        if isinstance(rt, str) and rt:
            return Path(rt)
    except Exception:
        pass

    # Dict fallback (tests)
    if isinstance(config, dict):
        rt = _get_nested(config, ["system_meta", "runtime", "config_dir"])
        if isinstance(rt, str) and rt:
            return Path(rt)

    _fail("Run bundle fail-closed: missing system_meta.runtime.config_dir")
    raise AssertionError("unreachable")


def _resolved_config_dict(config: Any) -> dict[str, Any]:
    if isinstance(config, dict):
        return config
    if hasattr(config, "model_dump") and callable(getattr(config, "model_dump")):
        out = config.model_dump()
        return out if isinstance(out, dict) else {"raw": _to_jsonable(out)}
    return {"raw": _to_jsonable(config)}


def _extract_assignments(resolved_config: dict[str, Any]) -> dict[str, list[str]]:
    """Best-effort: derive per-symbol strategy assignments from resolved config."""
    assignments: dict[str, list[str]] = {}
    # Primary SSOT: strategies_registry.assignments
    sr = resolved_config.get("strategies_registry")
    if isinstance(sr, dict):
        raw = sr.get("assignments")
        if isinstance(raw, dict):
            for sym, lst in raw.items():
                if isinstance(sym, str) and isinstance(lst, list):
                    strategies = [str(x) for x in lst if isinstance(x, str) and x]
                    assignments[sym] = strategies

    # Compatibility fallback: instruments.<sym>.strategies (if present in some configs)
    if not assignments:
        inst = resolved_config.get("instruments")
        if isinstance(inst, dict):
            for sym, spec in inst.items():
                if not isinstance(sym, str):
                    continue
                if not isinstance(spec, dict):
                    continue
                lst = spec.get("strategies")
                if isinstance(lst, list):
                    strategies = [str(x) for x in lst if isinstance(x, str) and x]
                    if strategies:
                        assignments[sym] = strategies

    return assignments


def _active_strategies_from_assignments(assignments: dict[str, list[str]]) -> list[str]:
    s: set[str] = set()
    for lst in assignments.values():
        for x in lst:
            if isinstance(x, str) and x:
                s.add(x)
    return sorted(s)


def _read_bytes_fail_closed(path: Path, *, label: str) -> bytes:
    if not path.exists() or not path.is_file():
        _fail(f"Run bundle fail-closed: missing required {label}: {path}")
    return path.read_bytes()


def _write_bytes(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _sha256_hex(data)


def save_backtest_run_bundle(
    *,
    run_id: str,
    report: dict[str, Any],
    config: Any,
    reports_root: Path,
) -> Path:
    """Persist a reproducible run bundle under reports/backtests/<run_id>/.

    Fail-closed rules:
    - If a strategy is declared active by resolved assignments, its YAML must exist.
    - Required SSOT YAML files must exist.
    - git sha must be resolvable.
    """
    if not isinstance(run_id, str) or not run_id:
        _fail("Run bundle fail-closed: run_id must be non-empty str")

    git_sha = _safe_git_sha()
    if not isinstance(git_sha, str) or not git_sha:
        _fail("Run bundle fail-closed: unable to resolve git SHA")

    config_dir = _config_dir_from_runtime_config(config)
    resolved = _resolved_config_dict(config)
    assignments = _extract_assignments(resolved)
    active_strategies = _active_strategies_from_assignments(assignments)

    bundle_dir = (reports_root / run_id)
    # deterministic overwrite for repeated runs with same run_id
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # --- Write result + resolved_config (canonical JSON) ---
    result_sha = _write_bytes(bundle_dir / "result.json", _canonical_json_bytes(report))
    resolved_sha = _write_bytes(bundle_dir / "resolved_config.json", _canonical_json_bytes(resolved))

    # --- Copy SSOT YAML files that influence the run (fail-closed) ---
    ssot_dir = bundle_dir / "config" / "ssot"
    ssot_required = [
        ("system.yaml", "system.yaml"),
        ("trading.yaml", "trading.yaml"),
        ("regime.yaml", "regime.yaml"),
        ("instruments.yaml", "instruments.yaml"),
        ("strategies.yaml", "strategies.yaml"),
    ]
    ssot_optional = [
        ("execution.yaml", "execution.yaml"),
    ]

    saved_files: list[dict[str, Any]] = []
    saved_files.append({"path": "result.json", "sha256": result_sha})
    saved_files.append({"path": "resolved_config.json", "sha256": resolved_sha})

    for src_name, dst_name in ssot_required:
        src = config_dir / src_name
        data = _read_bytes_fail_closed(src, label=f"SSOT config file {src_name}")
        sha = _write_bytes(ssot_dir / dst_name, data)
        saved_files.append({"path": f"config/ssot/{dst_name}", "sha256": sha})

    for src_name, dst_name in ssot_optional:
        src = config_dir / src_name
        if src.exists() and src.is_file():
            data = src.read_bytes()
            sha = _write_bytes(ssot_dir / dst_name, data)
            saved_files.append({"path": f"config/ssot/{dst_name}", "sha256": sha})

    # --- Copy strategy YAMLs used by this run (fail-closed on declared usage) ---
    strategy_src_dir = config_dir / "strategies"
    strategy_out_dir = bundle_dir / "config"
    strategy_id_to_bundle_name = {
        "aurora": "aurora.yaml",
        "mean_reversion": "mean_reversion.yaml",
    }
    for strategy_id, bundle_name in strategy_id_to_bundle_name.items():
        if strategy_id in active_strategies:
            src = strategy_src_dir / f"{strategy_id}.yaml"
            data = _read_bytes_fail_closed(src, label=f"strategy config strategies/{strategy_id}.yaml")
            sha = _write_bytes(strategy_out_dir / bundle_name, data)
            saved_files.append({"path": f"config/{bundle_name}", "sha256": sha})

    # Deterministic ordering
    saved_files.sort(key=lambda x: str(x.get("path") or ""))

    # config_hash: based ONLY on config artifacts (not manifest.json)
    config_files_for_hash = [
        f for f in saved_files
        if isinstance(f, dict) and isinstance(f.get("path"), str) and f["path"].startswith("config/")
    ] + [
        f for f in saved_files
        if isinstance(f, dict) and f.get("path") == "resolved_config.json"
    ]
    config_files_for_hash.sort(key=lambda x: str(x.get("path") or ""))
    config_hash_material = {
        "files": config_files_for_hash,
    }
    config_hash = _sha256_hex(_canonical_json_bytes(config_hash_material))

    manifest = {
        "run_id": run_id,
        "git_sha": git_sha,
        "config_hash": config_hash,
        "config_hash_algo": "sha256",
        "saved_files": saved_files,
        "active_strategies": active_strategies,
        "assignments": assignments,
    }
    try:
        runtime = getattr(getattr(config, "system_meta", None), "runtime", None)
        trial = getattr(runtime, "research_trial", None)
        if trial is not None:
            if hasattr(trial, "model_dump"):
                trial_payload = _to_jsonable(trial.model_dump())
            else:
                trial_payload = _to_jsonable(trial)
            if isinstance(trial_payload, dict) and not trial_payload.get("run_id"):
                trial_payload["run_id"] = run_id
            manifest["search_provenance"] = trial_payload
    except Exception:
        pass
    _write_bytes(bundle_dir / "manifest.json", _canonical_json_bytes(manifest))

    return bundle_dir


def _to_jsonable(value: Any, *, _seen: set[int] | None = None, _depth: int = 0) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if _seen is None:
        _seen = set()
    if _depth > 25:
        return str(value)
    obj_id = id(value)
    if obj_id in _seen:
        return "<cycle>"
    _seen.add(obj_id)
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v, _seen=_seen, _depth=_depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v, _seen=_seen, _depth=_depth + 1) for v in value]
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            return _to_jsonable(value.model_dump(), _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            maybe = value.to_dict()
            if isinstance(maybe, dict):
                return _to_jsonable(maybe, _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    if is_dataclass(value):
        try:
            return _to_jsonable(asdict(value), _seen=_seen, _depth=_depth + 1)
        except Exception:
            pass
    return str(value)


def _iso_from_ts_ms(ts_ms: Optional[int]) -> Optional[str]:
    if ts_ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def parse_order_log_jsonl(path: Path) -> Tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Parses OrderLoggerV1 JSONL into a list and some useful indices.
    Indices returned:
      - placed_by_order_id: {order_id: entry}
      - cancelled_by_order_id: {order_id: entry}
      - rejected_by_rid: {rid: [entries]}
    """
    entries: list[dict[str, Any]] = []
    placed_by_order_id: dict[str, dict[str, Any]] = {}
    cancelled_by_order_id: dict[str, dict[str, Any]] = {}
    rejected_by_rid: dict[str, list[dict[str, Any]]] = {}

    if not path or not path.exists():
        return entries, {
            "placed_by_order_id": placed_by_order_id,
            "cancelled_by_order_id": cancelled_by_order_id,
            "rejected_by_rid": rejected_by_rid,
        }

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                LOG.debug("Failed to parse order log line %s in %s", line_no, path)
                continue
            if not isinstance(obj, dict):
                continue
            entries.append(obj)
            ev = obj.get("event_type")
            if ev == "ORDER_PLACED":
                oid = obj.get("order_id")
                if isinstance(oid, str) and oid:
                    placed_by_order_id[oid] = obj
            elif ev == "ORDER_CANCELLED":
                oid = obj.get("order_id")
                if isinstance(oid, str) and oid:
                    cancelled_by_order_id[oid] = obj
            elif ev == "ORDER_REJECTED":
                rid = obj.get("rid")
                if isinstance(rid, str) and rid:
                    rejected_by_rid.setdefault(rid, []).append(obj)

    return entries, {
        "placed_by_order_id": placed_by_order_id,
        "cancelled_by_order_id": cancelled_by_order_id,
        "rejected_by_rid": rejected_by_rid,
    }


def _classify_close_reason(*, order_meta: dict[str, Any] | None, client_order_id: str | None, flip: bool) -> str:
    if flip:
        return "FLIP"
    t = str((order_meta or {}).get("type") or "").upper()
    if t == "STOP_MARKET":
        return "SL"
    if t == "TAKE_PROFIT_MARKET":
        return "TP"
    cid = (client_order_id or "").upper()
    if cid.startswith("SL-"):
        return "SL"
    if cid.startswith("TP-"):
        return "TP"
    if bool((order_meta or {}).get("closePosition")) or bool((order_meta or {}).get("reduceOnly")):
        return "EXIT"
    return "UNKNOWN"


def _summarize_open_mode(*, order_meta: dict[str, Any] | None, fill_role: str | None) -> str:
    om = order_meta or {}
    t = str(om.get("type") or "UNKNOWN").upper()
    tif = str(om.get("timeInForce") or "GTC").upper()
    role = str(fill_role or "").upper()
    parts = [t]
    if t == "LIMIT":
        parts.append(f"TIF={tif}")
        if tif == "GTX":
            parts.append("POST_ONLY")
    if role:
        parts.append(role)
    return "|".join(parts)


def _extract_strategies_registry(config: Any) -> dict[str, Any]:
    sr = getattr(config, "strategies_registry", None)
    if sr is None:
        return {"present": False}
    dumped = None
    if hasattr(sr, "model_dump") and callable(getattr(sr, "model_dump")):
        try:
            dumped = sr.model_dump()
        except Exception:
            dumped = None
    if dumped is None and isinstance(sr, dict):
        dumped = sr
    if not isinstance(dumped, dict):
        dumped = {"raw": str(sr)}
    # keep only SSOT-level keys (avoid accidental huge dumps if models change)
    out: dict[str, Any] = {"present": True}
    for k in ("version", "assignments", "arbitration"):
        if k in dumped:
            out[k] = dumped.get(k)
    return _to_jsonable(out)


def _extract_backtest_config_snapshot(config: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    cfg_dict: dict[str, Any] = {}
    try:
        if isinstance(config, dict):
            cfg_dict = config
        elif hasattr(config, "model_dump") and callable(getattr(config, "model_dump")):
            cfg_dict = config.model_dump()  # type: ignore[assignment]
    except Exception:
        cfg_dict = {}

    # Repro anchors
    out["git_sha"] = _safe_git_sha()
    out["config_files"] = _collect_config_files()
    try:
        out["trading_mode"] = getattr(config, "trading_mode", None)
    except Exception:
        pass

    # Resolved minimal slices for reproducibility.
    try:
        btc = _get_nested(cfg_dict, ["strategies", "aurora", "assets", "BTCUSDT"])
        regime_slice = {
            "basis_tf_sec": cfg_dict.get("basis_tf_sec"),
            "uncertain_cutoff": cfg_dict.get("uncertain_cutoff"),
            "liveness_factor": cfg_dict.get("liveness_factor"),
            "models": cfg_dict.get("models"),
        }
        out["resolved_config"] = {
            "strategies": {"aurora": {"assets": {"BTCUSDT": btc}}},
            "regime.yaml": regime_slice,
        }
    except Exception:
        pass

    try:
        bt = getattr(getattr(config, "trading", None), "backtest", None)
        if bt is not None and hasattr(bt, "model_dump"):
            out["trading.backtest"] = _to_jsonable(bt.model_dump())
        elif bt is not None:
            out["trading.backtest"] = _to_jsonable(bt)
    except Exception:
        pass

    try:
        runtime = getattr(getattr(config, "system_meta", None), "runtime", None)
        proxy = getattr(runtime, "research_proxy", None)
        if proxy is not None:
            if hasattr(proxy, "model_dump"):
                out["system_meta.runtime.research_proxy"] = _to_jsonable(proxy.model_dump())
            else:
                out["system_meta.runtime.research_proxy"] = _to_jsonable(proxy)
    except Exception:
        pass

    try:
        runtime = getattr(getattr(config, "system_meta", None), "runtime", None)
        trial = getattr(runtime, "research_trial", None)
        if trial is not None:
            if hasattr(trial, "model_dump"):
                out["system_meta.runtime.research_trial"] = _to_jsonable(trial.model_dump())
            else:
                out["system_meta.runtime.research_trial"] = _to_jsonable(trial)
    except Exception:
        pass

    try:
        ex = getattr(getattr(config, "trading", None), "execution", None)
        if ex is not None and hasattr(ex, "model_dump"):
            out["trading.execution"] = _to_jsonable(ex.model_dump())
        elif ex is not None:
            out["trading.execution"] = _to_jsonable(ex)
    except Exception:
        pass

    # Deterministic hash of reproducibility-critical snapshot fields.
    try:
        material = {
            "config_files": out.get("config_files"),
            "resolved_config": out.get("resolved_config"),
        }
        out["config_hash"] = _sha256_hex(
            json.dumps(_to_jsonable(material), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        out["config_hash_algo"] = "sha256"
    except Exception:
        pass

    return out


def build_backtest_report(
    *,
    run_id: str,
    config: Any,
    results: Any,
    engine: Any,
    start_date: datetime | date,
    end_date: datetime | date,
    symbols: list[str],
    timeframe: str,
    initial_balance: float,
    regimes: dict[str, Any],
    features: dict[str, Any],
    trade_intents: list[dict[str, Any]] | None = None,
    order_log_path: str | None = None,
    pipeline: dict[str, Any] | None = None,
    scoring_telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    broker = getattr(engine, "broker", None)

    # --- Parse order log (optional, but gives rid<->order_id + cancel reasons) ---
    order_log_entries: list[dict[str, Any]] = []
    indices: dict[str, Any] = {"placed_by_order_id": {}, "cancelled_by_order_id": {}, "rejected_by_rid": {}}
    order_log_file = Path(order_log_path) if order_log_path else None
    if order_log_file is not None:
        order_log_entries, indices = parse_order_log_jsonl(order_log_file)

    placed_by_order_id: dict[str, dict[str, Any]] = indices.get("placed_by_order_id", {}) or {}
    cancelled_by_order_id: dict[str, dict[str, Any]] = indices.get("cancelled_by_order_id", {}) or {}

    # --- trade intents index: rid -> intent ---
    trade_intents = trade_intents or []
    intent_by_rid: dict[str, dict[str, Any]] = {}
    strategy_by_rid: dict[str, str] = {}
    intent_by_idempotent_key: dict[str, dict[str, Any]] = {}
    for item in trade_intents:
        if not isinstance(item, dict):
            continue
        rid = item.get("rid")
        if not isinstance(rid, str) or not rid:
            continue
        intent_by_rid[rid] = item
        strat = item.get("strategy")
        if isinstance(strat, str) and strat:
            strategy_by_rid[rid] = strat
        idem = item.get("idempotent_key")
        if isinstance(idem, str) and idem:
            intent_by_idempotent_key[idem] = item

    # --- broker orders/fills ---
    broker_orders_raw: dict[str, Any] = getattr(broker, "_orders", {}) or {}
    order_meta_raw: dict[str, dict[str, Any]] = getattr(broker, "_order_meta", {}) or {}
    fills_raw: list[dict[str, Any]] = getattr(broker, "_fills", []) or []

    fills_by_order_id: dict[str, list[dict[str, Any]]] = {}
    for f in fills_raw:
        if not isinstance(f, dict):
            continue
        oid = f.get("orderId") or f.get("order_id") or f.get("orderId".lower())
        if isinstance(oid, str) and oid:
            fills_by_order_id.setdefault(oid, []).append(f)

    # normalize fill ordering per order
    for oid, lst in list(fills_by_order_id.items()):
        lst.sort(key=lambda x: _safe_int(x.get("timestamp")) or 0)
        fills_by_order_id[oid] = lst

    rid_by_order_id: dict[str, str] = {}
    for oid, ev in placed_by_order_id.items():
        rid = ev.get("rid")
        if isinstance(rid, str) and rid:
            rid_by_order_id[oid] = rid

    # --- Build "orders" section ---
    orders: list[dict[str, Any]] = []
    for oid, o in broker_orders_raw.items():
        order_obj = o
        try:
            symbol = getattr(order_obj, "symbol", None)
            side = getattr(order_obj, "side", None)
            status = getattr(order_obj, "status", None)
            client_order_id = getattr(order_obj, "client_order_id", None)
            qty = getattr(order_obj, "quantity", None)
            filled_qty = getattr(order_obj, "filled_qty", None)
            price = getattr(order_obj, "price", None)
            created_ts_ms = getattr(order_obj, "timestamp_ms", None)
        except Exception:
            symbol = side = status = client_order_id = qty = filled_qty = price = created_ts_ms = None

        meta = order_meta_raw.get(oid, {}) if isinstance(order_meta_raw, dict) else {}
        cancel_ev = cancelled_by_order_id.get(oid)
        placed_ev = placed_by_order_id.get(oid)
        fills = fills_by_order_id.get(oid, [])
        last_fill = fills[-1] if fills else None

        rid = rid_by_order_id.get(oid)
        strategy = strategy_by_rid.get(rid) if rid else None

        order_record: dict[str, Any] = {
            "order_id": str(oid),
            "client_order_id": str(client_order_id) if client_order_id is not None else None,
            "symbol": str(symbol) if symbol is not None else None,
            "side": str(side) if side is not None else None,
            "status": str(status) if status is not None else None,
            "created_ts_ms": _safe_int(created_ts_ms),
            "created_iso_utc": _iso_from_ts_ms(_safe_int(created_ts_ms)),
            "requested_price": _safe_float(price),
            "requested_qty": _safe_float(qty),
            "filled_qty": _safe_float(filled_qty),
            "meta": _to_jsonable(meta),
            "rid": rid,
            "strategy": strategy,
        }

        if placed_ev and isinstance(placed_ev, dict):
            order_record["source"] = {
                "order_logger": {
                    "event_type": "ORDER_PLACED",
                    "reservation_id": placed_ev.get("reservation_id"),
                    "metadata": _to_jsonable(placed_ev.get("metadata")),
                }
            }
            # Best-effort link order -> intent via idempotent_key/corr_id (more stable than rid).
            try:
                corr_id = placed_ev.get("reservation_id")
                if corr_id is None:
                    md = placed_ev.get("metadata")
                    if isinstance(md, dict):
                        corr_id = md.get("corr_id")
                if isinstance(corr_id, str) and corr_id and corr_id in intent_by_idempotent_key:
                    it = intent_by_idempotent_key[corr_id]
                    order_record["intent_rid"] = it.get("rid")
                    order_record["intent_market_regime"] = it.get("market_regime") or it.get("regime")
                    if not order_record.get("strategy"):
                        s = it.get("strategy")
                        if isinstance(s, str) and s:
                            order_record["strategy"] = s
            except Exception:
                pass

        if cancel_ev and isinstance(cancel_ev, dict):
            order_record["cancel"] = {
                "reason": cancel_ev.get("reason"),
                "context": cancel_ev.get("context"),
                "ts_ms": _safe_int(cancel_ev.get("timestamp")),
                "iso_utc": _iso_from_ts_ms(_safe_int(cancel_ev.get("timestamp"))),
            }

        if last_fill and isinstance(last_fill, dict):
            order_record["fill"] = {
                "ts_ms": _safe_int(last_fill.get("timestamp")),
                "iso_utc": _iso_from_ts_ms(_safe_int(last_fill.get("timestamp"))),
                "price": _safe_float(last_fill.get("price")),
                "qty": _safe_float(last_fill.get("quantity")),
                "role": last_fill.get("role"),
                "fee": _safe_float(last_fill.get("fee")),
                "fee_asset": last_fill.get("fee_asset"),
            }
            order_record["open_mode"] = _summarize_open_mode(
                order_meta=meta if isinstance(meta, dict) else None,
                fill_role=last_fill.get("role"),
            )
        else:
            order_record["open_mode"] = _summarize_open_mode(
                order_meta=meta if isinstance(meta, dict) else None,
                fill_role=None,
            )

        orders.append(order_record)

    orders.sort(key=lambda x: (x.get("created_ts_ms") or 0, str(x.get("order_id") or "")))

    orders_by_id = {str(o.get("order_id")): o for o in orders if isinstance(o, dict) and o.get("order_id")}

    # --- Build "trades" section from fills ---
    fills_all: list[dict[str, Any]] = [f for f in fills_raw if isinstance(f, dict)]
    fills_all.sort(key=lambda x: _safe_int(x.get("timestamp")) or 0)

    trades: list[dict[str, Any]] = []
    pos_state: dict[str, dict[str, Any]] = {}

    # fallback: config strategies assignments per symbol
    assignments: dict[str, Any] = {}
    try:
        sr = getattr(config, "strategies_registry", None)
        assignments = getattr(sr, "assignments", {}) if sr is not None else {}
        if hasattr(assignments, "model_dump"):
            assignments = assignments.model_dump()  # type: ignore[assignment]
    except Exception:
        assignments = {}

    for f in fills_all:
        symbol = f.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            continue

        oid = f.get("orderId")
        if not isinstance(oid, str) or not oid:
            continue

        side = str(f.get("side") or "").upper()
        qty = _safe_float(f.get("quantity")) or 0.0
        price = _safe_float(f.get("price")) or 0.0
        ts_ms = _safe_int(f.get("timestamp")) or 0
        fee = _safe_float(f.get("fee")) or 0.0

        signed_qty = qty if side == "BUY" else -qty
        st = pos_state.setdefault(
            symbol,
            {
                "qty": 0.0,
                "avg_entry": 0.0,
                "trade": None,
            },
        )
        curr_qty = float(st["qty"])
        curr_entry = float(st["avg_entry"])

        order_rec = orders_by_id.get(oid, {})
        meta = (order_rec.get("meta") if isinstance(order_rec, dict) else None) or {}
        if not isinstance(meta, dict):
            meta = {}
        client_order_id = order_rec.get("client_order_id") if isinstance(order_rec, dict) else None

        # If flat and opening a new position
        if abs(curr_qty) < 1e-12:
            rid = rid_by_order_id.get(oid)
            strategy = strategy_by_rid.get(rid) if rid else None
            if strategy is None:
                # fallback: first assigned strategy for symbol (if any)
                ids = assignments.get(symbol)
                if isinstance(ids, list) and ids and isinstance(ids[0], str):
                    strategy = ids[0]
            intent_rid = None
            market_regime = None
            if isinstance(order_rec, dict):
                intent_rid = order_rec.get("intent_rid")
                market_regime = order_rec.get("intent_market_regime")
            if market_regime is None and rid and rid in intent_by_rid:
                market_regime = (intent_by_rid.get(rid) or {}).get("market_regime")
            st["trade"] = {
                "rid": rid,
                "intent_rid": intent_rid,
                "strategy": strategy,
                "market_regime": market_regime,
                "symbol": symbol,
                "entry": {
                    "order_id": oid,
                    "client_order_id": client_order_id,
                    "ts_ms": ts_ms,
                    "iso_utc": _iso_from_ts_ms(ts_ms),
                    "side": "LONG" if signed_qty > 0 else "SHORT",
                    "price": price,
                    "qty": qty,
                    "open_mode": order_rec.get("open_mode") if isinstance(order_rec, dict) else None,
                    "order_meta": meta,
                },
                "fees_usdt": fee,
                "entry_value_usdt": abs(qty * price),
                "pnl_usdt": 0.0,
                "qty_signed": signed_qty,
                "avg_entry": price if qty > 0 else 0.0,
                "fills": [
                    {
                        "order_id": oid,
                        "ts_ms": ts_ms,
                        "iso_utc": _iso_from_ts_ms(ts_ms),
                        "side": side,
                        "qty": qty,
                        "price": price,
                        "fee": fee,
                    }
                ],
            }
            st["qty"] = signed_qty
            st["avg_entry"] = price if qty > 0 else 0.0
            continue

        # Adjust average entry if increasing in same direction
        if (curr_qty > 0 and signed_qty > 0) or (curr_qty < 0 and signed_qty < 0):
            new_qty = curr_qty + signed_qty
            if abs(new_qty) > 1e-12:
                st["avg_entry"] = ((abs(curr_qty) * curr_entry) + (abs(signed_qty) * price)) / abs(new_qty)
            st["qty"] = new_qty
            tr = st.get("trade")
            if isinstance(tr, dict):
                tr["fees_usdt"] = float(tr.get("fees_usdt") or 0.0) + fee
                tr["fills"].append(
                    {
                        "order_id": oid,
                        "ts_ms": ts_ms,
                        "iso_utc": _iso_from_ts_ms(ts_ms),
                        "side": side,
                        "qty": qty,
                        "price": price,
                        "fee": fee,
                    }
                )
                tr["qty_signed"] = float(tr.get("qty_signed") or 0.0) + signed_qty
                tr["avg_entry"] = float(st["avg_entry"])
            continue

        # Reducing or flipping
        closed_qty = min(abs(curr_qty), abs(signed_qty))
        realized = 0.0
        if closed_qty > 0:
            if curr_qty > 0:
                realized = (price - curr_entry) * closed_qty
            else:
                realized = (curr_entry - price) * closed_qty

        new_qty = curr_qty + signed_qty
        flip = (curr_qty > 0 and new_qty < 0) or (curr_qty < 0 and new_qty > 0)

        tr = st.get("trade")
        if isinstance(tr, dict):
            tr["fees_usdt"] = float(tr.get("fees_usdt") or 0.0) + fee
            tr["pnl_usdt"] = float(tr.get("pnl_usdt") or 0.0) + realized
            tr["fills"].append(
                {
                    "order_id": oid,
                    "ts_ms": ts_ms,
                    "iso_utc": _iso_from_ts_ms(ts_ms),
                    "side": side,
                    "qty": qty,
                    "price": price,
                    "fee": fee,
                }
            )

        # If position is closed (to flat) OR flipped, close current trade
        if abs(new_qty) < 1e-12 or flip:
            if isinstance(tr, dict):
                close_reason = _classify_close_reason(order_meta=meta, client_order_id=client_order_id, flip=flip)
                entry = tr.get("entry") if isinstance(tr.get("entry"), dict) else {}
                entry_price = _safe_float(entry.get("price")) or 0.0
                pnl = float(tr.get("pnl_usdt") or 0.0)
                fees = float(tr.get("fees_usdt") or 0.0)
                net_pnl = pnl - fees
                pnl_pct = (net_pnl / abs(float(tr.get("entry_value_usdt") or 0.0))) * 100.0 if float(tr.get("entry_value_usdt") or 0.0) else None
                trades.append(
                    _to_jsonable(
                        {
                            "rid": tr.get("rid"),
                            "intent_rid": tr.get("intent_rid"),
                            "strategy": tr.get("strategy"),
                            "market_regime": tr.get("market_regime"),
                            "symbol": symbol,
                            "side": entry.get("side"),
                            "entry": entry,
                            "exit": {
                                "order_id": oid,
                                "client_order_id": client_order_id,
                                "ts_ms": ts_ms,
                                "iso_utc": _iso_from_ts_ms(ts_ms),
                                "price": price,
                                "qty": closed_qty,
                                "open_mode": order_rec.get("open_mode") if isinstance(order_rec, dict) else None,
                                "order_meta": meta,
                            },
                            "close_reason": close_reason,
                            "pnl_usdt_gross": pnl,
                            "fees_usdt": fees,
                            "pnl_usdt_net": net_pnl,
                            "pnl_pct_net": pnl_pct,
                            "fills": tr.get("fills"),
                        }
                    )
                )

            # reset trade on flip/flat
            st["trade"] = None

        # Update position after close
        st["qty"] = new_qty
        if abs(new_qty) < 1e-12:
            st["avg_entry"] = 0.0
            st["qty"] = 0.0
        elif flip:
            # Remaining qty becomes a new position at current price
            remaining = abs(new_qty)
            rid = rid_by_order_id.get(oid)  # best-effort (usually None for bracket closes)
            strategy = strategy_by_rid.get(rid) if rid else None
            if strategy is None:
                ids = assignments.get(symbol)
                if isinstance(ids, list) and ids and isinstance(ids[0], str):
                    strategy = ids[0]
            st["trade"] = {
                "rid": rid,
                "strategy": strategy,
                "symbol": symbol,
                "entry": {
                    "order_id": oid,
                    "client_order_id": client_order_id,
                    "ts_ms": ts_ms,
                    "iso_utc": _iso_from_ts_ms(ts_ms),
                    "side": "LONG" if new_qty > 0 else "SHORT",
                    "price": price,
                    "qty": remaining,
                    "open_mode": order_rec.get("open_mode") if isinstance(order_rec, dict) else None,
                    "order_meta": meta,
                    "opened_by": "FLIP",
                },
                "fees_usdt": fee,
                "entry_value_usdt": abs(remaining * price),
                "pnl_usdt": 0.0,
                "qty_signed": new_qty,
                "avg_entry": price,
                "fills": [
                    {
                        "order_id": oid,
                        "ts_ms": ts_ms,
                        "iso_utc": _iso_from_ts_ms(ts_ms),
                        "side": side,
                        "qty": qty,
                        "price": price,
                        "fee": fee,
                    }
                ],
            }
            st["avg_entry"] = price
        # else: reduced but still same side -> entry stays same

    open_trades: list[dict[str, Any]] = []
    for sym, st in pos_state.items():
        tr = st.get("trade")
        if isinstance(tr, dict):
            open_trades.append(_to_jsonable(tr))

    # End-of-backtest positions snapshot (raw broker state)
    positions_end: list[dict[str, Any]] = []
    try:
        pos_map = getattr(broker, "_positions", {}) or {}
        if isinstance(pos_map, dict):
            for _, pos in pos_map.items():
                try:
                    amt = _safe_float(getattr(pos, "position_amount", None))
                except Exception:
                    amt = None
                if amt is None or abs(amt) < 1e-12:
                    continue
                positions_end.append(
                    _to_jsonable(
                        {
                            "symbol": getattr(pos, "symbol", None),
                            "position_side": getattr(pos, "position_side", None),
                            "side": getattr(pos, "side", None),
                            "position_amount": amt,
                            "entry_price": _safe_float(getattr(pos, "entry_price", None)),
                            "mark_price": _safe_float(getattr(pos, "mark_price", None)),
                            "unrealized_profit": _safe_float(getattr(pos, "unrealized_profit", None)),
                            "leverage": getattr(pos, "leverage", None),
                            "margin_type": getattr(pos, "margin_type", None),
                            "update_time_ms": _safe_int(getattr(pos, "update_time_ms", None)),
                            "update_time_iso_utc": _iso_from_ts_ms(_safe_int(getattr(pos, "update_time_ms", None))),
                        }
                    )
                )
    except Exception:
        positions_end = []

    # --- Summaries ---
    orders_summary: dict[str, Any] = {
        "total_orders": len(orders),
        "filled_orders": int(sum(1 for o in orders if isinstance(o, dict) and isinstance(o.get("fill"), dict))),
        "cancelled_orders": int(sum(1 for o in orders if isinstance(o, dict) and isinstance(o.get("cancel"), dict))),
        "open_orders": int(sum(1 for o in orders if isinstance(o, dict) and o.get("status") == "ACCEPTED")),
        "orders_by_type": {},
    }
    by_type: dict[str, int] = {}
    for o in orders:
        if not isinstance(o, dict):
            continue
        meta = o.get("meta")
        t = str((meta or {}).get("type") or "UNKNOWN").upper() if isinstance(meta, dict) else "UNKNOWN"
        by_type[t] = int(by_type.get(t, 0)) + 1
    orders_summary["orders_by_type"] = by_type

    trade_summary: dict[str, Any] = {
        "total_trades_reconstructed": len(trades),
        "open_trades": len(open_trades),
        "close_reason_counts": {},
    }
    crc: dict[str, int] = {}
    for t in trades:
        if not isinstance(t, dict):
            continue
        r = str(t.get("close_reason") or "UNKNOWN")
        crc[r] = int(crc.get(r, 0)) + 1
    trade_summary["close_reason_counts"] = crc

    def _date_or_dt_to_iso(v: datetime | date) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return datetime.combine(v, datetime.min.time(), tzinfo=timezone.utc).isoformat()

    report_data: dict[str, Any] = {
        "report_version": "2.2.0",
        "run_id": run_id,
        "metadata": {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "start_date": _date_or_dt_to_iso(start_date),
            "end_date": _date_or_dt_to_iso(end_date),
            "symbols": symbols,
            "timeframe": timeframe,
            "initial_balance": float(initial_balance),
            "strategies_active": sorted(set([s for s in strategy_by_rid.values() if isinstance(s, str) and s])),
        },
        "metrics": _to_jsonable(asdict(results) if is_dataclass(results) else results),
        "strategies": {
            "registry": _extract_strategies_registry(config),
            "intents_total": len(trade_intents),
            "intents_by_strategy": {},
        },
        "intents": trade_intents,
        "orders": orders,
        "orders_summary": orders_summary,
        "fills": _to_jsonable(fills_all),
        "trades": trades,
        "trades_summary": trade_summary,
        "open_trades": open_trades,
        "positions_end": positions_end,
        "regimes": _to_jsonable(regimes),
        "regime_log": _to_jsonable((regimes or {}).get("regime_log", [])),
        "features": _to_jsonable(features),
        "pipeline": _to_jsonable(pipeline or {}),
        "scoring_telemetry": _to_jsonable(scoring_telemetry or {}),
        "artifacts": {
            "order_log_jsonl": str(order_log_file) if order_log_file is not None else None,
        },
        "config_snapshot": _to_jsonable(_extract_backtest_config_snapshot(config)),
        "notes": [
            "times are UTC ISO based on simulated ts_ms where available",
            "close_reason classification is derived from broker order type/clientOrderId and flip detection",
        ],
    }

    try:
        runtime = getattr(getattr(config, "system_meta", None), "runtime", None)
        proxy = getattr(runtime, "research_proxy", None)
        if proxy is not None:
            if hasattr(proxy, "model_dump"):
                report_data["proxy_universe"] = _to_jsonable(proxy.model_dump())
            else:
                report_data["proxy_universe"] = _to_jsonable(proxy)
    except Exception:
        pass

    try:
        runtime = getattr(getattr(config, "system_meta", None), "runtime", None)
        trial = getattr(runtime, "research_trial", None)
        if trial is not None:
            if hasattr(trial, "model_dump"):
                trial_payload = _to_jsonable(trial.model_dump())
            else:
                trial_payload = _to_jsonable(trial)
            if isinstance(trial_payload, dict) and not trial_payload.get("run_id"):
                trial_payload["run_id"] = run_id
            report_data["search_provenance"] = trial_payload
    except Exception:
        pass

    try:
        stress_params = getattr(broker, "applied_stress_params", None)
        funding_ledger = getattr(broker, "funding_ledger", None)
        if isinstance(stress_params, dict):
            funding_total = 0.0
            if isinstance(funding_ledger, list):
                for rec in funding_ledger:
                    if not isinstance(rec, dict):
                        continue
                    try:
                        funding_total += float(rec.get("cash_delta", 0.0) or 0.0)
                    except Exception:
                        continue
            report_data["execution_stress"] = {
                "applied_params": _to_jsonable(stress_params),
                "funding_events": int(len(funding_ledger)) if isinstance(funding_ledger, list) else 0,
                "funding_cash_delta_total": float(funding_total),
            }
    except Exception:
        pass

    # Backtest-only cashflow simulation (profit withdrawals)
    try:
        w = getattr(engine, "capital_withdrawals", None)
        if isinstance(w, list) and w:
            report_data["capital_withdrawals"] = _to_jsonable(w)
    except Exception:
        pass
    
    # ALPHA-SEARCH: Add shadow mode metrics if plugin was active
    try:
        alpha_plugin = getattr(engine, "alpha_search_plugin", None)
        if alpha_plugin is not None and hasattr(alpha_plugin, "get_summary"):
            report_data["alpha_search"] = _to_jsonable(alpha_plugin.get_summary())
    except Exception as e:
        LOG.debug(f"No AlphaSearch metrics: {e}")

    by_strategy: dict[str, int] = {}
    for item in trade_intents:
        if not isinstance(item, dict):
            continue
        s = item.get("strategy")
        if not isinstance(s, str) or not s:
            s = "UNKNOWN"
        by_strategy[s] = int(by_strategy.get(s, 0)) + 1
    report_data["strategies"]["intents_by_strategy"] = by_strategy

    if not report_data["metadata"].get("strategies_active"):
        # fallback to config assignments if no intents were emitted
        try:
            active: set[str] = set()
            for _, ids in (assignments or {}).items():
                if isinstance(ids, list):
                    for sid in ids:
                        if isinstance(sid, str) and sid:
                            active.add(sid)
            report_data["metadata"]["strategies_active"] = sorted(active)
        except Exception:
            pass

    return _to_jsonable(report_data)
