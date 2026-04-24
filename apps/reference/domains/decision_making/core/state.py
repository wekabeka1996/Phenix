from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from apps.reference.core.time.clock import Clock


def _new_symbol_states() -> dict[str, dict[str, Any]]:
    return defaultdict(lambda: {"features": None, "risk": None})


def _new_shared_state() -> dict[str, Any]:
    return {
        "latest_portfolio": None,
        "latest_regime": None,
        "latest_warmup": None,
        "latest_structural_regime_by_symbol": {},
        "latest_structural_warmup_by_symbol": {},
        "cached_equity_free_usdt": None,
        "cached_equity_cross_usdt": None,
        "exposure_cache": None,
        "exposure_cache_timestamp": 0.0,
    }


def _new_qos_state() -> dict[str, dict[str, Any]]:
    return defaultdict(
        lambda: {
            "last_exposure_block": 0.0,
            "symbol_cooldowns": {},
            "symbol_intent_counts": defaultdict(
                lambda: {"count": 0, "window_start": 0.0}
            ),
        }
    )


@dataclass
class DMState:
    """Raw mutable state containers owned by the DecisionMaking facade."""

    symbol_states: dict[str, dict[str, Any]]
    shared_state: dict[str, Any]
    per_symbol_regimes: dict[str, dict[str, Any]]
    system_stress_states: dict[str, str]
    side_intent_window: dict[str, dict[str, list]]
    pending_flips: dict[str, dict[str, Any]]
    arb_window_winner: dict[str, tuple]
    arb_signal_buffer: dict[str, tuple]
    qos_state: dict[str, dict[str, Any]]
    qos_next_allowed_ts: dict[str, dict[str, Any]]
    intents_seen_total: int
    intents_blocked_total: int
    last_alert_check_time: float
    last_bar_index: dict[str, int]
    behavior_state: dict[str, str]

    @classmethod
    def new(cls, clock: Clock) -> "DMState":
        return cls(
            symbol_states=_new_symbol_states(),
            shared_state=_new_shared_state(),
            per_symbol_regimes={},
            system_stress_states={},
            side_intent_window={},
            pending_flips={},
            arb_window_winner={},
            arb_signal_buffer={},
            qos_state=_new_qos_state(),
            qos_next_allowed_ts=defaultdict(dict),
            intents_seen_total=0,
            intents_blocked_total=0,
            last_alert_check_time=clock.now_sec(),
            last_bar_index={},
            behavior_state={},
        )