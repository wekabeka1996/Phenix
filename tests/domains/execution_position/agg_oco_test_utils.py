"""Shared helpers for aggregated OCO ExecPosFSM test harnesses."""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable

import apps.reference.domains.execution_position.fsm as execpos_mod
from apps.reference.services.order_guardian import BracketSetMeta


class StubOrderGuardian:
    """Lightweight stand-in for OrderGuardian used in tests."""

    def __init__(self, *_: Any, **__: Any) -> None:
        self._bracket_sets: list[BracketSetMeta] = []
        self.register_calls: list[Dict[str, Any]] = []
        self.known_symbols: set[str] = set()

    def update_known_symbols(self, symbols: Iterable[str]) -> None:
        for symbol in symbols or []:
            self.known_symbols.add(str(symbol).upper())

    def register_bracket_set(self, **kwargs: Any) -> BracketSetMeta:
        meta = BracketSetMeta(
            bracket_set_id=str(
                kwargs.get(
                    "bracket_set_id") or f"stub-{len(self._bracket_sets) + 1}"
            ),
            symbol=str(kwargs.get("symbol") or "UNKNOWN").upper(),
            side=str(kwargs.get("side") or "LONG").upper(),
            sl_order_id=kwargs.get("sl_order_id"),
            tp_order_id=kwargs.get("tp_order_id"),
            created_ts=float(kwargs.get("created_ts") or time.time()),
            version=len(self._bracket_sets),
        )
        self._bracket_sets.append(meta)
        self.register_calls.append(dict(kwargs))
        return meta

    def clear_bracket_set_for_position(self, *, symbol: str, side: str) -> None:
        symbol_upper = symbol.upper()
        side_upper = side.upper()
        self._bracket_sets = [
            meta
            for meta in self._bracket_sets
            if not (meta.symbol == symbol_upper and meta.side == side_upper)
        ]

    def list_bracket_sets(self) -> list[BracketSetMeta]:
        return list(self._bracket_sets)

    async def cleanup_orphans(self, *_: Any, **__: Any) -> int:  # pragma: no cover - async stub
        return 0

    async def reconcile_symbol(self, *_: Any, **__: Any) -> None:  # pragma: no cover - async stub
        return None


class StubWatchdog:
    """Test stub for OrderTimeoutWatchdog that avoids background work."""

    def __init__(self, *_: Any, **__: Any) -> None:
        self.started = False

    def ensure_started(self, *_: Any, **__: Any) -> None:
        self.started = True

    def set_hooks(self, *_: Any, **__: Any) -> None:
        return None

    def track_order_placed(self, *_: Any, **__: Any) -> None:
        return None

    def on_order_ack(self, *_: Any, **__: Any) -> None:
        return None


def aggregated_only_config(symbol: str) -> Dict[str, Any]:
    symbol_upper = symbol.upper()
    return {
        "trading": {
            "instruments": {
                symbol_upper: {
                    "tick_size": "0.01",
                    "step_size": "0.001",
                    "min_qty": "0.001",
                    "min_notional": "5",
                }
            },
            "execution": {
                "cooldown_ms": 0,
                "guard_enabled": False,
                "manage": {
                    "mode": "aggregated_only",
                    "auto": True,
                    "orphan_monitor": {
                        "enabled": False,
                        "run_on_startup": False,
                        "periodic_interval_sec": 300,
                        "min_order_age_sec": 0,
                        "batch_cancel_limit": 50,
                        "rate_limit_per_min": 120,
                    },
                    "quick_profit": {
                        "enabled": False,
                        "target_usd": "5",
                        "mode": "fixed_usd",
                        "priority": "highest",
                        "ignore_other_rules": False,
                    },
                    "brackets": {
                        "enable": True,
                        "working_type_default": "MARK_PRICE",
                        "price_protect": False,
                        "keep_single_bracket_set": True,
                        "sl": {"fixed_bps": 50},
                        "tp": {"fixed_bps": 100},
                        "offset_bps": 5,
                        "aggregated_oco": {
                            "enabled": True,
                            "aggregated_only_mode": True,
                            "recalc_on_scale_in": True,
                            "recalc_on_partial_close": True,
                            "ttl_protect_new_bracket_ms": 0,
                            "allow_unprotected_position": False,
                            "watchdog": {
                                "enabled": False,
                                "interval_sec": 5,
                                "auto_heal_orphans": True,
                            },
                        },
                    },
                    "guardian": {
                        "unified": True,
                        "emit_tidy_event": True,
                        "poll_interval_ms": 0,
                        "cleanup_ttl_ms": 6000,
                        "symbol_cooldown_ms": 100,
                    },
                    "watchdog": {
                        "ack_ttl_ms": 8000,
                        "fill_ttl_ms": 30000,
                        "check_interval_ms": 1000,
                        "source": "test",
                    },
                    "positions": {
                        "ws_snapshot": {
                            "enabled": True,
                            "max_age_ms": 1500,
                            "rest_fallback_enabled": True,
                        }
                    },
                },
            },
        },
    }


def make_execpos(monkeypatch: Any, symbol: str = "SOLUSDT") -> execpos_mod.ExecPosFSM:
    """Create ExecPosFSM wired for aggregated-only tests with patched deps."""

    monkeypatch.setattr(execpos_mod, "OrderGuardian",
                        lambda *a, **k: StubOrderGuardian(*a, **k))
    monkeypatch.setattr(execpos_mod, "OrderTimeoutWatchdog",
                        lambda *a, **k: StubWatchdog(*a, **k))
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_guardian_start", lambda self: None)
    monkeypatch.setattr(execpos_mod.ExecPosFSM,
                        "_schedule_fsm_cleanup_loop", lambda self: None)

    config = aggregated_only_config(symbol)
    return execpos_mod.ExecPosFSM(config=config, fsm=None, shadow_mode=True)
