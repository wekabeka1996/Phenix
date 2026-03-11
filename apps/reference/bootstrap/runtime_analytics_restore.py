from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    StrategyAnalyticsRestoreSnapshot,
    cold_restore_status,
    invalidated_restore_status,
    make_strategy_restore_snapshot,
    partial_restore_status,
    restored_restore_status,
)


@dataclass(frozen=True)
class StartupAnalyticsRestoreReport:
    updated_at: int | None
    source: str
    snapshots: Mapping[str, StrategyAnalyticsRestoreSnapshot]

    def get_snapshot(
        self,
        strategy_id: str,
        symbol: str,
    ) -> StrategyAnalyticsRestoreSnapshot | None:
        return self.snapshots.get(_snapshot_key(strategy_id, symbol))

    def to_payload(self) -> dict[str, object]:
        rollup_counts: dict[str, int] = {}
        scope_state_counts: dict[str, int] = {}
        for snapshot in self.snapshots.values():
            rollup_key = snapshot.rollup_state.value
            rollup_counts[rollup_key] = rollup_counts.get(rollup_key, 0) + 1
            for count_key, count_value in snapshot.counts.items():
                scope_state_counts[count_key] = scope_state_counts.get(count_key, 0) + int(count_value)
        return {
            "updated_at": self.updated_at,
            "source": self.source,
            "snapshot_count": len(self.snapshots),
            "rollup_counts": rollup_counts,
            "scope_state_counts": scope_state_counts,
            "snapshots": {
                key: snapshot.to_payload()
                for key, snapshot in self.snapshots.items()
            },
        }


def _snapshot_key(strategy_id: str, symbol: str) -> str:
    return f"{str(strategy_id)}:{str(symbol).upper()}"


def _extract_assignments(config: Any) -> dict[str, list[str]]:
    assignments_raw = getattr(getattr(config, "strategies_registry", None), "assignments", None)
    if not isinstance(assignments_raw, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for symbol, strategy_ids in assignments_raw.items():
        if not isinstance(strategy_ids, list):
            continue
        clean_ids = [str(strategy_id) for strategy_id in strategy_ids if str(strategy_id)]
        if clean_ids:
            normalized[str(symbol).upper()] = clean_ids
    return normalized


def _has_open_position(position: Any) -> bool:
    if not isinstance(position, Mapping):
        return False
    qty_raw = (
        position.get("quantity")
        if "quantity" in position
        else position.get("qty")
    )
    try:
        return abs(Decimal(str(qty_raw or 0))) > Decimal("0")
    except Exception:
        return False


def _normalize_scope_status(
    *,
    state: str,
    why: Iterable[str] | str | None,
    updated_at: int | None,
    source: str,
    evidence_ref: str | None,
):
    state_normalized = str(state or "").strip().upper()
    if state_normalized == "RESTORED":
        return restored_restore_status(
            why=why,
            updated_at=updated_at,
            source=source,
            evidence_ref=evidence_ref,
        )
    if state_normalized == "PARTIAL":
        return partial_restore_status(
            why=why,
            updated_at=updated_at,
            source=source,
            evidence_ref=evidence_ref,
        )
    if state_normalized == "INVALIDATED_DUE_TO_GAP":
        return invalidated_restore_status(
            why=why,
            updated_at=updated_at,
            source=source,
            evidence_ref=evidence_ref,
        )
    return cold_restore_status(
        why=why,
        updated_at=updated_at,
        source=source,
        evidence_ref=evidence_ref,
    )


def _parse_explicit_restore_payload(snapshot_data: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(snapshot_data, Mapping):
        return {}
    analytics_restore = snapshot_data.get("analytics_restore")
    if not isinstance(analytics_restore, Mapping):
        return {}

    snapshots_raw = analytics_restore.get("snapshots")
    parsed: dict[str, dict[str, Any]] = {}

    if isinstance(snapshots_raw, Mapping):
        for key, value in snapshots_raw.items():
            if isinstance(value, Mapping):
                parsed[str(key)] = dict(value)
        return parsed

    if isinstance(snapshots_raw, list):
        for item in snapshots_raw:
            if not isinstance(item, Mapping):
                continue
            strategy_id = str(item.get("strategy_id") or "")
            symbol = str(item.get("symbol") or "").upper()
            if strategy_id and symbol:
                parsed[_snapshot_key(strategy_id, symbol)] = dict(item)
    return parsed


def _build_default_snapshot(
    *,
    strategy_id: str,
    symbol: str,
    updated_at: int | None,
    source: str,
    snapshot_loaded: bool,
    has_open_position: bool,
    strategy_local_hint: Mapping[str, Any] | None = None,
) -> StrategyAnalyticsRestoreSnapshot:
    execution_status = (
        restored_restore_status(
            why=["execution_snapshot_loaded"],
            updated_at=updated_at,
            source="execution_position:startup_restore",
            evidence_ref=f"execution:{symbol}:{updated_at}",
        )
        if snapshot_loaded
        else cold_restore_status(
            why=["execution_restore_missing"],
            updated_at=updated_at,
            source="execution_position:startup_restore",
            evidence_ref=f"execution:{symbol}:{updated_at}",
        )
    )

    strategy_local_status = cold_restore_status(
        why=["strategy_local_restore_missing"],
        updated_at=updated_at,
        source=f"decision_making:{strategy_id}",
        evidence_ref=f"strategy_local:{strategy_id}:{symbol}:{updated_at}",
    )
    if isinstance(strategy_local_hint, Mapping):
        strategy_local_status = _normalize_scope_status(
            state=str(strategy_local_hint.get("state") or "COLD"),
            why=strategy_local_hint.get("why") if isinstance(strategy_local_hint.get("why"), str) else strategy_local_hint.get("why"),
            updated_at=(
                int(strategy_local_hint["updated_at"])
                if strategy_local_hint.get("updated_at") is not None
                else updated_at
            ),
            source=str(strategy_local_hint.get("source") or f"decision_making:{strategy_id}"),
            evidence_ref=(
                str(strategy_local_hint.get("evidence_ref"))
                if strategy_local_hint.get("evidence_ref") is not None
                else f"strategy_local:{strategy_id}:{symbol}:{updated_at}"
            ),
        )

    scopes = {
        RuntimeAnalyticsRestoreScope.BARS.value: cold_restore_status(
            why=["bars_restore_missing"],
            updated_at=updated_at,
            source="market_data:startup_restore",
            evidence_ref=f"bars:{symbol}:{updated_at}",
        ),
        RuntimeAnalyticsRestoreScope.PARTIAL_BAR.value: cold_restore_status(
            why=["partial_bar_restore_missing"],
            updated_at=updated_at,
            source="market_data:startup_restore",
            evidence_ref=f"partial_bar:{symbol}:{updated_at}",
        ),
        RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_LAST_BAR.value: cold_restore_status(
            why=["fe_last_bar_restore_missing"],
            updated_at=updated_at,
            source="feature_engineering:startup_restore",
            evidence_ref=f"fe_last_bar:{symbol}:{updated_at}",
        ),
        RuntimeAnalyticsRestoreScope.FEATURE_ENGINEERING_CACHE.value: cold_restore_status(
            why=["fe_cache_restore_missing"],
            updated_at=updated_at,
            source="feature_engineering:startup_restore",
            evidence_ref=f"fe_cache:{symbol}:{updated_at}",
        ),
        RuntimeAnalyticsRestoreScope.REGIME_DETECTOR_STATE.value: cold_restore_status(
            why=["regime_restore_missing"],
            updated_at=updated_at,
            source="regime_detector:startup_restore",
            evidence_ref=f"regime:{symbol}:{updated_at}",
        ),
        RuntimeAnalyticsRestoreScope.PILLAR_STATE.value: cold_restore_status(
            why=["pillar_restore_missing"],
            updated_at=updated_at,
            source="feature_engineering:startup_restore",
            evidence_ref=f"pillars:{symbol}:{updated_at}",
        ),
        RuntimeAnalyticsRestoreScope.DECISION_CACHE.value: cold_restore_status(
            why=["decision_cache_restore_missing"],
            updated_at=updated_at,
            source="decision_making:startup_restore",
            evidence_ref=f"decision_cache:{strategy_id}:{symbol}:{updated_at}",
        ),
        RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value: strategy_local_status,
        RuntimeAnalyticsRestoreScope.EXECUTION_STATE.value: execution_status,
    }
    return make_strategy_restore_snapshot(
        strategy_id=strategy_id,
        symbol=symbol,
        updated_at=updated_at,
        scopes=scopes,
        source=source,
        has_open_position=has_open_position,
    )


def _build_snapshot_from_explicit_payload(
    *,
    strategy_id: str,
    symbol: str,
    updated_at: int | None,
    source: str,
    has_open_position: bool,
    payload: Mapping[str, Any],
) -> StrategyAnalyticsRestoreSnapshot:
    scopes_payload = payload.get("scopes")
    scopes: dict[str, Any] = {}
    if isinstance(scopes_payload, Mapping):
        for scope_name, raw_status in scopes_payload.items():
            if not isinstance(raw_status, Mapping):
                continue
            scopes[str(scope_name)] = _normalize_scope_status(
                state=str(raw_status.get("state") or "COLD"),
                why=raw_status.get("why"),
                updated_at=(
                    int(raw_status["updated_at"])
                    if raw_status.get("updated_at") is not None
                    else updated_at
                ),
                source=str(raw_status.get("source") or source),
                evidence_ref=(
                    str(raw_status.get("evidence_ref"))
                    if raw_status.get("evidence_ref") is not None
                    else None
                ),
            )

    for required_scope in RuntimeAnalyticsRestoreScope:
        scopes.setdefault(
            required_scope.value,
            cold_restore_status(
                why=[f"{required_scope.value}_restore_missing"],
                updated_at=updated_at,
                source=str(payload.get("source") or source),
                evidence_ref=f"{required_scope.value}:{strategy_id}:{symbol}:{updated_at}",
            ),
        )

    return make_strategy_restore_snapshot(
        strategy_id=strategy_id,
        symbol=symbol,
        updated_at=(
            int(payload["updated_at"])
            if payload.get("updated_at") is not None
            else updated_at
        ),
        scopes=scopes,
        source=str(payload.get("source") or source),
        has_open_position=has_open_position,
        blocking_reason_chain=payload.get("blocking_reason_chain"),
    )


def build_startup_analytics_restore_report(
    *,
    config: Any,
    snapshot_data: Mapping[str, Any] | None,
    positions: Mapping[str, Any] | None,
    strategy_handlers: Mapping[str, Any] | None = None,
    snapshot_loaded: bool,
    updated_at: int | None,
    source: str = "startup:analytics_restore",
) -> StartupAnalyticsRestoreReport:
    assignments = _extract_assignments(config)
    positions = positions if isinstance(positions, Mapping) else {}
    explicit = _parse_explicit_restore_payload(snapshot_data)
    strategy_handlers = strategy_handlers if isinstance(strategy_handlers, Mapping) else {}

    snapshots: dict[str, StrategyAnalyticsRestoreSnapshot] = {}
    for symbol, strategy_ids in assignments.items():
        position = positions.get(symbol)
        has_open_position = _has_open_position(position)
        for strategy_id in strategy_ids:
            key = _snapshot_key(strategy_id, symbol)
            explicit_payload = explicit.get(key)
            if isinstance(explicit_payload, Mapping):
                snapshots[key] = _build_snapshot_from_explicit_payload(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    updated_at=updated_at,
                    source=source,
                    has_open_position=has_open_position,
                    payload=explicit_payload,
                )
                continue

            strategy_local_hint = None
            handler = strategy_handlers.get(str(strategy_id))
            describe_fn = getattr(handler, "describe_runtime_analytics_restore", None)
            if callable(describe_fn):
                try:
                    raw_hint = describe_fn(symbol)
                except Exception:
                    raw_hint = None
                if isinstance(raw_hint, Mapping):
                    strategy_local_hint = raw_hint.get(
                        RuntimeAnalyticsRestoreScope.STRATEGY_LOCAL_STATE.value,
                        raw_hint,
                    )

            snapshots[key] = _build_default_snapshot(
                strategy_id=strategy_id,
                symbol=symbol,
                updated_at=updated_at,
                source=source,
                snapshot_loaded=snapshot_loaded,
                has_open_position=has_open_position,
                strategy_local_hint=strategy_local_hint,
            )

    return StartupAnalyticsRestoreReport(
        updated_at=updated_at,
        source=source,
        snapshots=snapshots,
    )
