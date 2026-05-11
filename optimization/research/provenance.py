from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _jsonify(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonify(item) for item in value]
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        try:
            return _jsonify(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            return _jsonify(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return _jsonify(vars(value))
        except Exception:
            pass
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonify(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def get_value_by_path(payload: Dict[str, Any], path: str) -> Any:
    current: Any = payload
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return _jsonify(current)


def remove_runtime_trial(payload: Dict[str, Any]) -> Dict[str, Any]:
    cloned = json.loads(json.dumps(_jsonify(payload), ensure_ascii=False))
    runtime = (((cloned.get("system_meta") or {}).get("runtime") or {}))
    if isinstance(runtime, dict):
        runtime.pop("research_trial", None)
    return cloned


def extract_config_payload(config: Any) -> Dict[str, Any]:
    if isinstance(config, dict):
        return remove_runtime_trial(config)
    if hasattr(config, "model_dump") and callable(getattr(config, "model_dump")):
        return remove_runtime_trial(config.model_dump())
    return remove_runtime_trial(_jsonify(config))


def extract_strategy_slice(
    config_payload: Dict[str, Any],
    *,
    strategy_id: str,
    strategy_symbol: str,
) -> Dict[str, Any]:
    strategies = config_payload.get("strategies") or {}
    strategy_block = strategies.get(strategy_id) if isinstance(strategies, dict) else {}
    assets = strategy_block.get("assets") if isinstance(strategy_block, dict) else {}
    asset_slice = assets.get(strategy_symbol) if isinstance(assets, dict) else None
    return _jsonify(asset_slice or {})


def collect_effective_values(config_payload: Dict[str, Any], expected_changed_paths: List[str]) -> Dict[str, Any]:
    return {path: get_value_by_path(config_payload, path) for path in expected_changed_paths}


def write_manifest(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonify(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class ResearchTrialRequest:
    trial_id: str
    arm_id: str
    trial_params_json: Dict[str, Any] = field(default_factory=dict)
    expected_changed_paths: List[str] = field(default_factory=list)
    parent_anchor: Optional[str] = None
    anchor_overrides: Optional[Dict[str, Any]] = None
    strategy_id: str = "aurora"
    strategy_symbol: str = "ETHUSDT"


@dataclass
class ResearchTrialMaterialization:
    manifest_path: Path
    payload: Dict[str, Any]


def build_trial_payload(
    *,
    config: Any,
    overlay: Dict[str, Any],
    request: ResearchTrialRequest,
    proxy_universe: Dict[str, Any],
    fail_closed_on_scoring_fallback: bool,
    anchor_effective_config_hash: Optional[str] = None,
    anchor_effective_strategy_slice_hash: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> Dict[str, Any]:
    config_payload = extract_config_payload(config)
    strategy_slice = extract_strategy_slice(
        config_payload,
        strategy_id=request.strategy_id,
        strategy_symbol=request.strategy_symbol,
    )
    effective_changed_values = collect_effective_values(config_payload, request.expected_changed_paths)
    preflight_passed = rejection_reason is None
    return {
        "manifest_version": "1.0.0",
        "trial_id": request.trial_id,
        "arm_id": request.arm_id,
        "trial_params_json": _jsonify(request.trial_params_json),
        "expected_changed_paths": list(request.expected_changed_paths),
        "effective_changed_values": effective_changed_values,
        "overlay_hash": sha256_hex(overlay),
        "effective_config_hash": sha256_hex(config_payload),
        "effective_strategy_slice_hash": sha256_hex(strategy_slice),
        "proxy_universe": _jsonify(proxy_universe),
        "fail_closed_on_scoring_fallback": bool(fail_closed_on_scoring_fallback),
        "run_id": None,
        "parent_anchor": request.parent_anchor,
        "timestamp": utc_now_iso(),
        "anchor_effective_config_hash": anchor_effective_config_hash,
        "anchor_effective_strategy_slice_hash": anchor_effective_strategy_slice_hash,
        "preflight_passed": preflight_passed,
        "rejection_reason": rejection_reason,
        "execution_status": "preflight_passed" if preflight_passed else "preflight_rejected",
    }


def build_materialization(
    *,
    manifest_dir: Path,
    config: Any,
    overlay: Dict[str, Any],
    request: ResearchTrialRequest,
    proxy_universe: Dict[str, Any],
    fail_closed_on_scoring_fallback: bool,
    anchor_effective_config_hash: Optional[str] = None,
    anchor_effective_strategy_slice_hash: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> ResearchTrialMaterialization:
    manifest_path = manifest_dir / f"{request.trial_id}.json"
    payload = build_trial_payload(
        config=config,
        overlay=overlay,
        request=request,
        proxy_universe=proxy_universe,
        fail_closed_on_scoring_fallback=fail_closed_on_scoring_fallback,
        anchor_effective_config_hash=anchor_effective_config_hash,
        anchor_effective_strategy_slice_hash=anchor_effective_strategy_slice_hash,
        rejection_reason=rejection_reason,
    )
    payload["manifest_path"] = str(manifest_path)
    write_manifest(manifest_path, payload)
    return ResearchTrialMaterialization(manifest_path=manifest_path, payload=payload)


def update_materialization(
    manifest_path: Path,
    current_payload: Dict[str, Any],
    **updates: Any,
) -> Dict[str, Any]:
    merged = dict(current_payload)
    for key, value in updates.items():
        merged[key] = _jsonify(value)
    write_manifest(manifest_path, merged)
    return merged