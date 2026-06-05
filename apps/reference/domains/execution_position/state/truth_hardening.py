from __future__ import annotations

import json
import logging
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.utils import BoundedEventDeduper

LOG = logging.getLogger(
    "apps.reference.domains.execution_position.truth_hardening"
)

TERMINAL_IDENTITY_CACHE_SCHEMA_VERSION = "1.0.0"
TERMINAL_IDENTITY_CACHE_STATE_TYPE = "execution_terminal_identity_cache_v1"
TERMINAL_IDENTITY_CACHE_KIND = "exact_terminal_fill_identity_dedupe_seed"
TERMINAL_IDENTITY_CACHE_TRUTH_CLASS = "cache_only"
TERMINAL_IDENTITY_CACHE_DEFAULT_PATH = "logs/execution_terminal_identity_cache_v1.json"
TERMINAL_IDENTITY_CACHE_LEGACY_PATH = "logs/execution_truth_warm_state_v1.json"
TERMINAL_IDENTITY_CACHE_LEGACY_STATE_TYPE = "execution_truth_warm_state_v1"


@dataclass(frozen=True)
class TradeExecutedDecision:
    suppress: bool
    key: Optional[str]
    reason: str
    exact_identity: bool
    identity_quality: str
    trade_id_present: bool
    degraded_identity: bool
    warm_state_hit: bool = False
    warm_state_miss: bool = False
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class CloseGuardDecision:
    suppress: bool
    key: Optional[str]
    reason: str


@dataclass
class _CloseGuardEntry:
    key: str
    position_signature: str
    requested_qty: str
    ts_ms: int
    rid: Optional[str] = None


@dataclass(frozen=True)
class TradeExecutedIdentity:
    key: Optional[str]
    symbol: Optional[str]
    order_id: Optional[str]
    client_order_id: Optional[str]
    identity_quality: str
    exact_identity: bool
    degraded_identity: bool
    trade_id_present: bool
    missing_fields: tuple[str, ...]


@dataclass
class _WarmStateEntry:
    key: str
    ts_ms: int
    symbol: str
    order_id: str
    client_order_id: str
    identity_quality: str


@dataclass(frozen=True)
class WarmStateLoadResult:
    status: str
    path: Optional[str]
    configured_path: Optional[str] = None
    legacy_alias_path: Optional[str] = None
    compatibility_mode: str = "configured_path"
    truth_class: str = TERMINAL_IDENTITY_CACHE_TRUTH_CLASS
    authoritative: bool = False
    cache_kind: str = TERMINAL_IDENTITY_CACHE_KIND
    loaded_entries: int = 0
    skipped_expired: int = 0
    skipped_invalid: int = 0
    skipped_non_exact: int = 0
    failure: Optional[str] = None


class ExecutionTruthHardening:
    """
    Narrow pre-stabilization runtime hardening for execution truth.

    Scope:
    - shared dedupe seam for EVT:TRADE_EXECUTED
    - source-boundary repeated CMD:CLOSE suppression
    - non-CMD DEC:CLOSE execution-path suppression
    - bounded cache-only continuity for recent exact terminal fill identities

    This object is intentionally bounded and fail-open. It is not a new SSOT.
    """

    def __init__(
        self,
        *,
        fill_dedup_max_size: int,
        fill_dedup_ttl_ms: int,
        close_guard_ttl_ms: int,
        warm_state_enabled: bool,
        warm_state_storage_path: Optional[str],
        warm_state_max_entries: int,
    ) -> None:
        self.fill_dedup_max_size = int(fill_dedup_max_size)
        self.fill_dedup_ttl_ms = int(fill_dedup_ttl_ms)
        self.close_guard_ttl_ms = int(close_guard_ttl_ms)
        self.warm_state_enabled = bool(warm_state_enabled)
        self.warm_state_max_entries = int(warm_state_max_entries)
        self.warm_state_storage_path = (
            Path(warm_state_storage_path)
            if self.warm_state_enabled and warm_state_storage_path
            else None
        )
        self._fill_deduper = BoundedEventDeduper(
            max_size=self.fill_dedup_max_size,
            ttl_ms=self.fill_dedup_ttl_ms,
        )
        self._close_guard: dict[str, _CloseGuardEntry] = {}
        self._warm_state_entries: OrderedDict[str,
                                              _WarmStateEntry] = OrderedDict()
        self._warm_seeded_fill_keys: set[str] = set()
        self._lock = RLock()
        self._last_warm_state_load_result = WarmStateLoadResult(
            status="not_attempted",
            path=str(
                self.warm_state_storage_path) if self.warm_state_storage_path else None,
            configured_path=str(
                self.warm_state_storage_path) if self.warm_state_storage_path else None,
            legacy_alias_path=(
                str(self._legacy_warm_state_alias_path())
                if self._legacy_warm_state_alias_path() is not None
                else None
            ),
            compatibility_mode=(
                "legacy_configured_path"
                if self._uses_legacy_warm_state_path()
                else "configured_path"
            ),
        )

    def evaluate_trade_executed(
        self,
        payload: dict[str, Any],
        *,
        order_index: Any = None,
    ) -> TradeExecutedDecision:
        identity = resolve_trade_executed_identity(
            payload, order_index=order_index)
        key = identity.key
        if key is None:
            return TradeExecutedDecision(
                suppress=False,
                key=None,
                reason="fill_identity_insufficient_fail_open",
                exact_identity=identity.exact_identity,
                identity_quality=identity.identity_quality,
                trade_id_present=identity.trade_id_present,
                degraded_identity=identity.degraded_identity,
                missing_fields=identity.missing_fields,
            )

        now_ms = get_clock().now_ms()
        warm_state_hit = False
        warm_state_miss = False
        with self._lock:
            self._fill_deduper.prune(now_ms)
            self._prune_warm_state(now_ms)
            warm_seeded = key in self._warm_seeded_fill_keys

            if self._fill_deduper.seen(key):
                warm_state_hit = warm_seeded
                if warm_seeded:
                    self._warm_seeded_fill_keys.discard(key)
                if identity.exact_identity:
                    self._remember_exact_terminal_identity_unlocked(
                        identity, now_ms)
                return TradeExecutedDecision(
                    suppress=True,
                    key=key,
                    reason=(
                        "duplicate_trade_executed_seeded_terminal_identity"
                        if warm_state_hit
                        else "duplicate_trade_executed_same_fill_identity"
                    ),
                    exact_identity=identity.exact_identity,
                    identity_quality=identity.identity_quality,
                    trade_id_present=identity.trade_id_present,
                    degraded_identity=identity.degraded_identity,
                    warm_state_hit=warm_state_hit,
                    missing_fields=identity.missing_fields,
                )

            self._fill_deduper.add(key, now_ms)

            if identity.exact_identity:
                warm_state_miss = self._warm_state_active() and not warm_seeded
                self._remember_exact_terminal_identity_unlocked(
                    identity, now_ms)

        return TradeExecutedDecision(
            suppress=False,
            key=key,
            reason="fill_identity_first_seen",
            exact_identity=identity.exact_identity,
            identity_quality=identity.identity_quality,
            trade_id_present=identity.trade_id_present,
            degraded_identity=identity.degraded_identity,
            warm_state_miss=warm_state_miss,
            missing_fields=identity.missing_fields,
        )

    def peek_trade_executed(
        self,
        payload: dict[str, Any],
        *,
        order_index: Any = None,
    ) -> TradeExecutedDecision:
        """Inspect whether a trade-executed identity was already seen.

        This is a read-only probe over the shared fill deduper. It never seeds
        a new identity and therefore is safe for late duplicate checks at
        ingress boundaries.
        """
        identity = resolve_trade_executed_identity(
            payload, order_index=order_index)
        key = identity.key
        if key is None:
            return TradeExecutedDecision(
                suppress=False,
                key=None,
                reason="fill_identity_insufficient_fail_open",
                exact_identity=identity.exact_identity,
                identity_quality=identity.identity_quality,
                trade_id_present=identity.trade_id_present,
                degraded_identity=identity.degraded_identity,
                missing_fields=identity.missing_fields,
            )

        now_ms = get_clock().now_ms()
        with self._lock:
            self._fill_deduper.prune(now_ms)
            self._prune_warm_state(now_ms)
            warm_seeded = key in self._warm_seeded_fill_keys
            seen = self._fill_deduper.seen(key)

        return TradeExecutedDecision(
            suppress=seen,
            key=key,
            reason=(
                "duplicate_trade_executed_seeded_terminal_identity"
                if seen and warm_seeded
                else "duplicate_trade_executed_same_fill_identity"
                if seen
                else "fill_identity_not_seen"
            ),
            exact_identity=identity.exact_identity,
            identity_quality=identity.identity_quality,
            trade_id_present=identity.trade_id_present,
            degraded_identity=identity.degraded_identity,
            warm_state_hit=seen and warm_seeded,
            missing_fields=identity.missing_fields,
        )

    def evaluate_close_command(
        self,
        *,
        symbol: str,
        requested_qty: Any,
        position_signature: Optional[str],
        rid: Optional[str],
    ) -> CloseGuardDecision:
        return self._evaluate_close_guard(
            scope="cmd_close",
            symbol=symbol,
            requested_qty=requested_qty,
            position_signature=position_signature,
            rid=rid,
        )

    def evaluate_non_cmd_close_decision(
        self,
        *,
        symbol: str,
        requested_qty: Any,
        position_signature: Optional[str],
        rid: Optional[str],
    ) -> CloseGuardDecision:
        return self._evaluate_close_guard(
            scope="non_cmd_dec_close",
            symbol=symbol,
            requested_qty=requested_qty,
            position_signature=position_signature,
            rid=rid,
        )

    def observe_portfolio_state(self, *, symbol: str, position_signature: Optional[str]) -> None:
        normalized_symbol = str(symbol or "").upper()
        if not normalized_symbol:
            return

        signature = str(position_signature or "UNKNOWN")
        now_ms = get_clock().now_ms()
        with self._lock:
            self._prune_close_guard(now_ms)
            scoped_keys = [
                storage_key
                for storage_key in self._close_guard.keys()
                if storage_key.endswith(f":{normalized_symbol}")
            ]
            if signature == "UNKNOWN":
                return
            for storage_key in scoped_keys:
                current = self._close_guard.get(storage_key)
                if current is None:
                    continue
                if current.position_signature == signature:
                    continue
                if signature == "FLAT:0":
                    scope = storage_key.split(":", 1)[0]
                    current.position_signature = signature
                    current.key = (
                        f"{scope}:{normalized_symbol}:position={signature}:"
                        f"qty={current.requested_qty}"
                    )
                    current.ts_ms = now_ms
                    continue
                self._close_guard.pop(storage_key, None)

    def load_warm_state(self) -> WarmStateLoadResult:
        configured_path = self.warm_state_storage_path
        configured_path_text = str(
            configured_path) if configured_path else None
        legacy_alias_path = self._legacy_warm_state_alias_path()
        legacy_alias_text = str(
            legacy_alias_path) if legacy_alias_path else None
        if not self._warm_state_active():
            result = WarmStateLoadResult(
                status="disabled",
                path=configured_path_text,
                configured_path=configured_path_text,
                legacy_alias_path=legacy_alias_text,
                compatibility_mode="disabled",
            )
            self._last_warm_state_load_result = result
            return result

        path = configured_path
        assert path is not None

        load_path = path
        compatibility_mode = (
            "legacy_configured_path"
            if self._uses_legacy_warm_state_path()
            else "configured_path"
        )
        if not load_path.exists() and legacy_alias_path is not None and legacy_alias_path.exists():
            load_path = legacy_alias_path
            compatibility_mode = "legacy_path_alias"
        elif not load_path.exists():
            result = WarmStateLoadResult(
                status="empty",
                path=str(path),
                configured_path=str(path),
                legacy_alias_path=legacy_alias_text,
                compatibility_mode=compatibility_mode,
            )
            self._last_warm_state_load_result = result
            return result

        try:
            with open(load_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            result = WarmStateLoadResult(
                status="empty",
                path=str(path),
                configured_path=str(path),
                legacy_alias_path=legacy_alias_text,
                compatibility_mode=compatibility_mode,
            )
            self._last_warm_state_load_result = result
            return result
        except Exception as exc:
            LOG.warning(
                "Execution terminal identity cache load failed: %s", exc)
            result = WarmStateLoadResult(
                status="load_failed",
                path=str(load_path),
                configured_path=str(path),
                legacy_alias_path=legacy_alias_text,
                compatibility_mode=compatibility_mode,
                failure=f"{type(exc).__name__}:{exc}",
            )
            self._last_warm_state_load_result = result
            return result

        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            result = WarmStateLoadResult(
                status="load_failed",
                path=str(load_path),
                configured_path=str(path),
                legacy_alias_path=legacy_alias_text,
                compatibility_mode=compatibility_mode,
                failure="ValueError:invalid_warm_state_entries",
            )
            self._last_warm_state_load_result = result
            return result

        loaded = 0
        skipped_expired = 0
        skipped_invalid = 0
        skipped_non_exact = 0
        now_ms = get_clock().now_ms()
        with self._lock:
            self._warm_state_entries.clear()
            self._warm_seeded_fill_keys.clear()
            for item in raw_entries:
                if not isinstance(item, dict):
                    skipped_invalid += 1
                    continue

                key = _first_non_empty_str(item, "key")
                symbol = _first_non_empty_str(item, "symbol")
                order_id = _first_non_empty_str(item, "order_id")
                client_order_id = _first_non_empty_str(item, "client_order_id")
                identity_quality = _first_non_empty_str(
                    item, "identity_quality")
                ts_ms = _coerce_int(item.get("ts_ms"))

                if (
                    key is None
                    or symbol is None
                    or order_id is None
                    or client_order_id is None
                    or ts_ms is None
                ):
                    skipped_invalid += 1
                    continue

                if identity_quality != "order_lifecycle_contract_identity":
                    skipped_non_exact += 1
                    continue

                if (now_ms - ts_ms) > self.fill_dedup_ttl_ms:
                    skipped_expired += 1
                    continue

                entry = _WarmStateEntry(
                    key=key,
                    ts_ms=ts_ms,
                    symbol=symbol,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    identity_quality=identity_quality,
                )
                self._warm_state_entries[key] = entry
                self._warm_seeded_fill_keys.add(key)
                self._fill_deduper.add(key, ts_ms)
                loaded += 1

            self._prune_warm_state(now_ms)
            self._fill_deduper.prune(now_ms)

        result = WarmStateLoadResult(
            status="loaded" if loaded > 0 else "empty",
            path=str(load_path),
            configured_path=str(path),
            legacy_alias_path=legacy_alias_text,
            compatibility_mode=compatibility_mode,
            loaded_entries=loaded,
            skipped_expired=skipped_expired,
            skipped_invalid=skipped_invalid,
            skipped_non_exact=skipped_non_exact,
        )
        self._last_warm_state_load_result = result
        return result

    def _warm_state_active(self) -> bool:
        return (
            self.warm_state_enabled
            and self.warm_state_storage_path is not None
            and self.warm_state_max_entries > 0
        )

    def _uses_legacy_warm_state_path(self) -> bool:
        return (
            self.warm_state_storage_path is not None
            and self.warm_state_storage_path.name == Path(TERMINAL_IDENTITY_CACHE_LEGACY_PATH).name
        )

    def _legacy_warm_state_alias_path(self) -> Optional[Path]:
        if self.warm_state_storage_path is None or self._uses_legacy_warm_state_path():
            return None
        if self.warm_state_storage_path.name != Path(TERMINAL_IDENTITY_CACHE_DEFAULT_PATH).name:
            return None
        legacy_path = self.warm_state_storage_path.with_name(
            Path(TERMINAL_IDENTITY_CACHE_LEGACY_PATH).name
        )
        return legacy_path if legacy_path != self.warm_state_storage_path else None

    def cache_status_snapshot(self) -> dict[str, Any]:
        result = self._last_warm_state_load_result
        return {
            "legacy_config_key": "event_dedup.warm_state",
            "truth_class": TERMINAL_IDENTITY_CACHE_TRUTH_CLASS,
            "authoritative": False,
            "cache_kind": TERMINAL_IDENTITY_CACHE_KIND,
            "status": str(result.status or "not_attempted"),
            "configured_path": result.configured_path,
            "active_path": result.path,
            "legacy_alias_path": result.legacy_alias_path,
            "compatibility_mode": str(result.compatibility_mode or "configured_path"),
            "entries_loaded": int(result.loaded_entries),
        }

    def _remember_exact_terminal_identity_unlocked(
        self,
        identity: TradeExecutedIdentity,
        now_ms: int,
    ) -> None:
        if not self._warm_state_active():
            return
        if not identity.exact_identity:
            return
        if (
            identity.key is None
            or identity.symbol is None
            or identity.order_id is None
            or identity.client_order_id is None
        ):
            return

        entry = _WarmStateEntry(
            key=identity.key,
            ts_ms=now_ms,
            symbol=identity.symbol,
            order_id=identity.order_id,
            client_order_id=identity.client_order_id,
            identity_quality=identity.identity_quality,
        )
        self._warm_state_entries[identity.key] = entry
        self._warm_state_entries.move_to_end(identity.key)
        self._prune_warm_state(now_ms)
        self._persist_warm_state_unlocked(now_ms)

    def _persist_warm_state_unlocked(self, now_ms: int) -> None:
        if not self._warm_state_active():
            return

        path = self.warm_state_storage_path
        assert path is not None
        payload = {
            "schema_version": TERMINAL_IDENTITY_CACHE_SCHEMA_VERSION,
            "state_type": TERMINAL_IDENTITY_CACHE_STATE_TYPE,
            "truth_class": TERMINAL_IDENTITY_CACHE_TRUTH_CLASS,
            "authoritative": False,
            "cache_kind": TERMINAL_IDENTITY_CACHE_KIND,
            "generated_at_ms": int(now_ms),
            "retention_ms": int(self.fill_dedup_ttl_ms),
            "max_entries": int(self.warm_state_max_entries),
            "compatibility": {
                "legacy_state_type": TERMINAL_IDENTITY_CACHE_LEGACY_STATE_TYPE,
                "legacy_storage_path_alias": TERMINAL_IDENTITY_CACHE_LEGACY_PATH,
                "legacy_config_key": "event_dedup.warm_state",
            },
            "entries": [
                {
                    "key": entry.key,
                    "ts_ms": entry.ts_ms,
                    "symbol": entry.symbol,
                    "order_id": entry.order_id,
                    "client_order_id": entry.client_order_id,
                    "identity_quality": entry.identity_quality,
                }
                for entry in self._warm_state_entries.values()
            ],
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp.replace(path)
        except Exception as exc:
            LOG.warning(
                "Execution terminal identity cache persist failed: %s", exc)

    def _prune_warm_state(self, now_ms: int) -> None:
        while self._warm_state_entries:
            first_key = next(iter(self._warm_state_entries))
            first_entry = self._warm_state_entries[first_key]
            if (now_ms - first_entry.ts_ms) > self.fill_dedup_ttl_ms:
                self._warm_state_entries.popitem(last=False)
                self._warm_seeded_fill_keys.discard(first_key)
            else:
                break

        while len(self._warm_state_entries) > self.warm_state_max_entries:
            evict_key, _ = self._warm_state_entries.popitem(last=False)
            self._warm_seeded_fill_keys.discard(evict_key)

    def _prune_close_guard(self, now_ms: int) -> None:
        expired = [
            symbol
            for symbol, entry in self._close_guard.items()
            if (now_ms - entry.ts_ms) > self.close_guard_ttl_ms
        ]
        for symbol in expired:
            self._close_guard.pop(symbol, None)

    def _evaluate_close_guard(
        self,
        *,
        scope: str,
        symbol: str,
        requested_qty: Any,
        position_signature: Optional[str],
        rid: Optional[str],
    ) -> CloseGuardDecision:
        normalized_symbol = str(symbol or "").upper()
        if not normalized_symbol:
            return CloseGuardDecision(
                suppress=False,
                key=None,
                reason="close_guard_missing_symbol_fail_open",
            )

        now_ms = get_clock().now_ms()
        normalized_qty = normalize_close_qty(requested_qty)
        signature = str(position_signature or "UNKNOWN")
        storage_key = f"{scope}:{normalized_symbol}"
        with self._lock:
            self._prune_close_guard(now_ms)

            if signature == "UNKNOWN":
                if not rid:
                    return CloseGuardDecision(
                        suppress=False,
                        key=None,
                        reason="close_guard_unknown_position_without_rid_fail_open",
                    )
                key = (
                    f"{scope}:{normalized_symbol}:unknown_position:"
                    f"rid={rid}:qty={normalized_qty}"
                )
            else:
                key = (
                    f"{scope}:{normalized_symbol}:position={signature}:"
                    f"qty={normalized_qty}"
                )

            current = self._close_guard.get(storage_key)
            if current and current.key == key:
                age_ms = now_ms - current.ts_ms
                if age_ms <= self.close_guard_ttl_ms:
                    return CloseGuardDecision(
                        suppress=True,
                        key=key,
                        reason=(
                            "duplicate_cmd_close_same_effective_state"
                            if scope == "cmd_close"
                            else "duplicate_non_cmd_dec_close_same_effective_state"
                        ),
                    )

            self._close_guard[storage_key] = _CloseGuardEntry(
                key=key,
                position_signature=signature,
                requested_qty=normalized_qty,
                ts_ms=now_ms,
                rid=str(rid) if rid not in (None, "") else None,
            )

        return CloseGuardDecision(
            suppress=False,
            key=key,
            reason=(
                "close_guard_accepted"
                if scope == "cmd_close"
                else "non_cmd_close_guard_accepted"
            ),
        )


def build_trade_executed_key(payload: dict[str, Any]) -> Optional[str]:
    return resolve_trade_executed_identity(payload).key


def resolve_trade_executed_identity(
    payload: dict[str, Any],
    *,
    order_index: Any = None,
) -> TradeExecutedIdentity:
    symbol = str(payload.get("symbol") or payload.get(
        "instrument") or "").upper()
    order_id = _first_non_empty_str(
        payload,
        "orderId",
        "order_id",
        "exchangeOrderId",
        "exchange_order_id",
    )
    client_order_id = _first_non_empty_str(
        payload, "clientOrderId", "client_order_id")
    lifecycle_id = _first_non_empty_str(
        payload, "lifecycle_id", "idempotent_key")
    rid = _first_non_empty_str(payload, "rid")
    trade_id = _first_non_empty_str(payload, "tradeId", "trade_id")

    if order_index is not None and order_id:
        try:
            ref = order_index.get(exchangeOrderId=str(order_id))
        except Exception:
            ref = None
        if ref is None and client_order_id:
            try:
                ref = order_index.get(clientOrderId=str(client_order_id))
            except Exception:
                ref = None
        if ref is not None:
            client_order_id = client_order_id or getattr(
                ref, "clientOrderId", None)
            lifecycle_id = lifecycle_id or getattr(ref, "idempotent_key", None)
            rid = rid or getattr(ref, "rid", None)

    missing_fields = []
    if not symbol:
        missing_fields.append("symbol")
    if not order_id:
        missing_fields.append("order_id")

    if not symbol or not order_id:
        return TradeExecutedIdentity(
            key=None,
            symbol=symbol or None,
            order_id=order_id,
            client_order_id=client_order_id,
            identity_quality="insufficient_identity_fail_open",
            exact_identity=False,
            degraded_identity=True,
            trade_id_present=bool(trade_id),
            missing_fields=tuple(missing_fields),
        )

    # FILL-PIPELINE-FIX-AUDIT: trade_id suffix for partial fill dedup.
    # Each Binance partial fill has a unique trade_id ("t"), so including it
    # in the key allows multiple fills for the same order to pass through.
    # When trade_id is absent (e.g. REST polling), key stays backward-compatible.
    _tid_suffix = f":trade_id={trade_id}" if trade_id else ""

    if client_order_id:
        return TradeExecutedIdentity(
            key=(
                f"trade_executed:{symbol}:order_id={order_id}:"
                f"client_order_id={client_order_id}{_tid_suffix}"
            ),
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
            identity_quality="order_lifecycle_contract_identity",
            exact_identity=True,
            degraded_identity=False,
            trade_id_present=bool(trade_id),
            missing_fields=(),
        )

    anchor = lifecycle_id or rid
    if anchor:
        return TradeExecutedIdentity(
            key=(
                f"trade_executed:{symbol}:order_id={order_id}:"
                f"lifecycle_anchor={anchor}{_tid_suffix}"
            ),
            symbol=symbol,
            order_id=order_id,
            client_order_id=client_order_id,
            identity_quality="lifecycle_anchor_identity_degraded",
            exact_identity=False,
            degraded_identity=True,
            trade_id_present=bool(trade_id),
            missing_fields=("client_order_id",),
        )

    return TradeExecutedIdentity(
        key=f"trade_executed:{symbol}:order_id={order_id}{_tid_suffix}",
        symbol=symbol,
        order_id=order_id,
        client_order_id=client_order_id,
        identity_quality="order_only_identity_degraded",
        exact_identity=False,
        degraded_identity=True,
        trade_id_present=bool(trade_id),
        missing_fields=("client_order_id", "lifecycle_id", "rid"),
    )


def build_position_signature(portfolio_payload: dict[str, Any], symbol: str) -> Optional[str]:
    if not symbol:
        return None
    positions = portfolio_payload.get("positions")
    if not isinstance(positions, list):
        return "UNKNOWN"

    symbol_upper = str(symbol).upper()
    for pos in positions:
        if not isinstance(pos, dict):
            continue
        if str(pos.get("symbol") or "").upper() != symbol_upper:
            continue
        qty = _to_decimal(pos.get("net_position") or pos.get("positionAmt"))
        if qty is None:
            return "UNKNOWN"
        if abs(qty) <= Decimal("1e-9"):
            return "FLAT:0"
        side = "LONG" if qty > 0 else "SHORT"
        return f"{side}:{normalize_decimal_str(abs(qty))}"

    return "FLAT:0"


def normalize_close_qty(value: Any) -> str:
    normalized = normalize_decimal_str(value)
    return normalized if normalized is not None else "FULL"


def normalize_decimal_str(value: Any) -> Optional[str]:
    dec = _to_decimal(value)
    if dec is None:
        return None
    text = format(dec, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-0"):
        return "0"
    return text


def attach_execution_truth_hardening(
    fsm: Any,
    config: Any,
) -> Optional[ExecutionTruthHardening]:
    existing = getattr(fsm, "_execution_truth_hardening", None)
    if isinstance(existing, ExecutionTruthHardening):
        return existing

    resolved = resolve_execution_truth_hardening_config(config)
    if resolved is None:
        return None

    hardening = ExecutionTruthHardening(**resolved)
    setattr(fsm, "_execution_truth_hardening", hardening)
    journal = getattr(fsm, "_shadow_journal", None)
    is_bus_owner = hasattr(fsm, "emit") and hasattr(fsm, "listen")

    if journal is not None:
        try:
            journal.record_transition(
                event_name="RESTORE:EXECUTION_TRUTH_HARDENING_RESET",
                source_component="execution_truth_hardening",
                source_path="restore:execution_truth_hardening_reset",
                event_origin_type="restore",
                truth_owner="ExecutionTruthHardening",
                payload={
                    "restore_marker": True,
                    "terminal_identity_cache_truth_class": TERMINAL_IDENTITY_CACHE_TRUTH_CLASS,
                    "terminal_identity_cache_authoritative": False,
                    "terminal_identity_cache_persistence": (
                        TERMINAL_IDENTITY_CACHE_KIND
                        if is_bus_owner and hardening._warm_state_active()
                        else "process_local_only"
                    ),
                    "close_guard_persistence": "process_local_only",
                    "restart_behavior": (
                        "state_reset_before_cache_seed"
                        if is_bus_owner and hardening._warm_state_active()
                        else "state_reset_on_attach"
                    ),
                    "fill_dedup_entries": 0,
                    "close_guard_entries": 0,
                    "cache_owner": "FSMCore" if is_bus_owner else "non_bus_owner",
                },
                restore_marker=True,
                notes=[
                    "process_local_only_state",
                    (
                        "cache_seed_capable"
                        if is_bus_owner and hardening._warm_state_active()
                        else "cache_seed_not_loaded_here"
                    ),
                    "restart_reset_explicit",
                ],
            )
        except Exception:
            LOG.debug(
                "Failed to record execution truth hardening reset", exc_info=True)

    if is_bus_owner:
        load_result = hardening.load_warm_state()
        _record_warm_state_load_outcome(journal, load_result, hardening)

    return hardening


def get_execution_truth_hardening(owner: Any) -> Optional[ExecutionTruthHardening]:
    direct = getattr(owner, "_execution_truth_hardening", None)
    if isinstance(direct, ExecutionTruthHardening):
        return direct
    for attr in ("fsm", "_fsm"):
        parent = getattr(owner, attr, None)
        direct = getattr(parent, "_execution_truth_hardening", None)
        if isinstance(direct, ExecutionTruthHardening):
            return direct
    return None


def resolve_execution_truth_hardening_config(config: Any) -> Optional[dict[str, Any]]:
    try:
        exec_pos = getattr(getattr(config, "domains", None),
                           "execution_position", None)
        event_dedup = getattr(exec_pos, "event_dedup", None)
        trading_exec = getattr(
            getattr(config, "trading", None), "execution", None)
        warm_state_cfg = getattr(event_dedup, "warm_state", None)

        fill_dedup_max_size = _coerce_int(
            getattr(event_dedup, "max_size", None))
        fill_dedup_ttl_ms = _coerce_int(getattr(event_dedup, "ttl_ms", None))
        close_guard_ttl_ms = _coerce_int(
            getattr(trading_exec, "anti_race_close_ms", None))

        if (
            fill_dedup_max_size is None
            or fill_dedup_ttl_ms is None
            or close_guard_ttl_ms is None
        ):
            raise ValueError(
                "execution truth hardening requires event_dedup.max_size, "
                "event_dedup.ttl_ms, and trading.execution.anti_race_close_ms"
            )

        warm_state_enabled = bool(getattr(warm_state_cfg, "enabled", True))
        warm_state_storage_path = getattr(
            warm_state_cfg,
            "storage_path",
            TERMINAL_IDENTITY_CACHE_DEFAULT_PATH,
        )
        warm_state_max_entries = _coerce_int(
            getattr(warm_state_cfg, "max_entries", None))
        if warm_state_max_entries is None:
            raise ValueError(
                "execution truth hardening requires event_dedup.warm_state.max_entries"
            )

        return {
            "fill_dedup_max_size": fill_dedup_max_size,
            "fill_dedup_ttl_ms": fill_dedup_ttl_ms,
            "close_guard_ttl_ms": close_guard_ttl_ms,
            "warm_state_enabled": warm_state_enabled,
            "warm_state_storage_path": (
                str(warm_state_storage_path)
                if warm_state_storage_path not in (None, "")
                else None
            ),
            "warm_state_max_entries": warm_state_max_entries,
        }
    except Exception as exc:
        LOG.error("Execution truth hardening disabled: %s", exc)
        return None


def _record_warm_state_load_outcome(
    journal: Any,
    load_result: WarmStateLoadResult,
    hardening: ExecutionTruthHardening,
) -> None:
    if load_result.status == "loaded":
        LOG.info(
            "Execution terminal identity cache loaded: entries=%s path=%s",
            load_result.loaded_entries,
            load_result.path,
        )
    elif load_result.status == "empty":
        LOG.info(
            "Execution terminal identity cache empty start: path=%s", load_result.path)
    elif load_result.status == "load_failed":
        LOG.warning(
            "Execution terminal identity cache load failed: path=%s failure=%s",
            load_result.path,
            load_result.failure,
        )

    if journal is None:
        return

    try:
        if load_result.status == "loaded":
            journal.record_transition(
                event_name="CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_LOADED",
                source_component="execution_truth_hardening",
                source_path="cache:execution_terminal_identity_cache",
                event_origin_type="cache",
                truth_owner="ExecutionTruthHardening",
                restore_marker=False,
                payload={
                    "truth_class": load_result.truth_class,
                    "authoritative": load_result.authoritative,
                    "cache_kind": load_result.cache_kind,
                    "configured_path": load_result.configured_path,
                    "active_path": load_result.path,
                    "legacy_alias_path": load_result.legacy_alias_path,
                    "compatibility_mode": load_result.compatibility_mode,
                    "entries_loaded": load_result.loaded_entries,
                    "skipped_expired": load_result.skipped_expired,
                    "skipped_invalid": load_result.skipped_invalid,
                    "skipped_non_exact": load_result.skipped_non_exact,
                    "retention_ms": hardening.fill_dedup_ttl_ms,
                    "max_entries": hardening.warm_state_max_entries,
                },
                notes=["cache_only_seed_loaded", "terminal_fill_exact_only"],
            )
        elif load_result.status == "empty":
            journal.record_transition(
                event_name="CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_EMPTY",
                source_component="execution_truth_hardening",
                source_path="cache:execution_terminal_identity_cache",
                event_origin_type="cache",
                truth_owner="ExecutionTruthHardening",
                restore_marker=False,
                payload={
                    "truth_class": load_result.truth_class,
                    "authoritative": load_result.authoritative,
                    "cache_kind": load_result.cache_kind,
                    "configured_path": load_result.configured_path,
                    "active_path": load_result.path,
                    "legacy_alias_path": load_result.legacy_alias_path,
                    "compatibility_mode": load_result.compatibility_mode,
                    "entries_loaded": 0,
                    "retention_ms": hardening.fill_dedup_ttl_ms,
                    "max_entries": hardening.warm_state_max_entries,
                },
                notes=["cache_only_empty_start", "terminal_fill_exact_only"],
            )
        elif load_result.status == "load_failed":
            journal.record_transition(
                event_name="CACHE:EXECUTION_TERMINAL_IDENTITY_CACHE_LOAD_FAILED",
                source_component="execution_truth_hardening",
                source_path="cache:execution_terminal_identity_cache",
                event_origin_type="cache",
                truth_owner="ExecutionTruthHardening",
                restore_marker=False,
                payload={
                    "truth_class": load_result.truth_class,
                    "authoritative": load_result.authoritative,
                    "cache_kind": load_result.cache_kind,
                    "configured_path": load_result.configured_path,
                    "active_path": load_result.path,
                    "legacy_alias_path": load_result.legacy_alias_path,
                    "compatibility_mode": load_result.compatibility_mode,
                    "failure": load_result.failure,
                    "entries_loaded": 0,
                    "retention_ms": hardening.fill_dedup_ttl_ms,
                    "max_entries": hardening.warm_state_max_entries,
                },
                notes=["cache_only_load_failed", "fail_open_empty_seed"],
            )
    except Exception:
        LOG.debug("Failed to record warm-state load outcome", exc_info=True)


def _coerce_int(value: Any) -> Optional[int]:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _first_non_empty_str(mapping: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return str(value)
    return None
