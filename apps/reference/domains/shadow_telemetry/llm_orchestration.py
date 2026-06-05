from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from apps.reference.domains.shadow_telemetry.contracts import (
    MarketContextPacketV1,
    TradingDecisionV1,
)
from apps.reference.domains.shadow_telemetry.trading_read_models import (
    TradingReadModelService,
)


LOG = logging.getLogger("apps.reference.domains.shadow_telemetry.llm_orchestration")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class MarketContextCollector:
    """Builds normalized market-context packets from live read models."""

    def __init__(self, read_models: TradingReadModelService) -> None:
        self.read_models = read_models

    def collect_packet(
        self,
        *,
        symbol: str,
        tf_sec: int = 300,
        packet_kind: str = "fast",
        context_symbols: Optional[Iterable[str]] = None,
        lifecycle_id: Optional[str] = None,
    ) -> MarketContextPacketV1:
        latest = self.read_models.get_context_latest(symbol=symbol, tf_sec=tf_sec)
        overview_symbols = [str(item).upper() for item in (context_symbols or []) if str(item).strip()]
        market_overview = self.read_models.get_market_overview(
            symbols=overview_symbols,
            tf_sec=tf_sec,
        ) if overview_symbols else None
        position = self.read_models.get_position(lifecycle_id) if lifecycle_id else None
        packet = MarketContextPacketV1(
            packet_kind=packet_kind,
            symbol=str(symbol).upper(),
            tf_sec=tf_sec,
            snapshot=latest.get("snapshot"),
            risk_gate=latest.get("risk_gate") or {},
            active_positions=latest.get("active_positions") or [],
            recent_rejections=latest.get("recent_rejections") or [],
            recent_decisions=latest.get("recent_decisions") or [],
            market_overview=market_overview,
            lifecycle_id=lifecycle_id,
            provenance={
                **(latest.get("provenance") or {}),
                "collector": "MarketContextCollector",
                "packet_kind": packet_kind,
                "context_symbols": overview_symbols,
                "focus_position_found": bool(position) if lifecycle_id else False,
            },
        )
        return packet


class DecisionCoordinator:
    """Validates and persists typed trading decisions against runtime permissions."""

    def __init__(
        self,
        *,
        project_root: Path,
        execution_permissions: Optional[Dict[str, bool]] = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.execution_permissions = {
            "allow_open": True,
            "allow_close": True,
            "allow_bracket_amend": True,
            **(execution_permissions or {}),
        }

    @property
    def packets_path(self) -> Path:
        return self.project_root / "logs" / "shadow_telemetry" / "market_context_packets_v1.jsonl"

    @property
    def decisions_path(self) -> Path:
        return self.project_root / "logs" / "shadow_telemetry" / "trading_decisions_v1.jsonl"

    def persist_packet(self, packet: MarketContextPacketV1) -> Dict[str, Any]:
        payload = packet.model_dump(mode="json")
        _append_jsonl(self.packets_path, payload)
        return payload

    def validate_decision(self, decision: TradingDecisionV1) -> None:
        if decision.action == "OPEN_INTENT" and not self.execution_permissions["allow_open"]:
            raise ValueError("OPEN_INTENT is disabled by execution_permissions.allow_open=false")
        if decision.action == "CLOSE_POSITION" and not self.execution_permissions["allow_close"]:
            raise ValueError("CLOSE_POSITION is disabled by execution_permissions.allow_close=false")
        if decision.action == "AMEND_BRACKETS" and not self.execution_permissions["allow_bracket_amend"]:
            raise ValueError(
                "AMEND_BRACKETS is disabled by execution_permissions.allow_bracket_amend=false"
            )

    def persist_decision(self, decision: TradingDecisionV1) -> Dict[str, Any]:
        self.validate_decision(decision)
        payload = decision.model_dump(mode="json")
        _append_jsonl(self.decisions_path, payload)
        return payload


class PositionGuardian:
    """Builds focused guardian packets around an active lifecycle."""

    def __init__(
        self,
        *,
        collector: MarketContextCollector,
        coordinator: DecisionCoordinator,
    ) -> None:
        self.collector = collector
        self.coordinator = coordinator

    def collect_guardian_packet(
        self,
        *,
        symbol: str,
        lifecycle_id: str,
        tf_sec: int = 300,
        context_symbols: Optional[Iterable[str]] = None,
    ) -> MarketContextPacketV1:
        packet = self.collector.collect_packet(
            symbol=symbol,
            tf_sec=tf_sec,
            packet_kind="guardian",
            context_symbols=context_symbols,
            lifecycle_id=lifecycle_id,
        )
        self.coordinator.persist_packet(packet)
        return packet
