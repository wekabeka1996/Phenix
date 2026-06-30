from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Query

from .reducer import AgentFeedReducer, DEFAULT_MAX_TOKENS, MAX_SYMBOLS, MIN_MAX_TOKENS


def register_agent_feed_routes(
    app: FastAPI,
    *,
    project_root: Path,
    snapshot_store_provider: Optional[Callable[[], Any | None]] = None,
    execution_position_provider: Optional[Callable[[], Any | None]] = None,
) -> None:
    """Register the isolated GET-only v0 bridge on an existing FastAPI host."""

    existing = {getattr(route, "path", None) for route in getattr(app, "routes", [])}
    if "/agent-feed/v0/packet" in existing:
        return

    def reducer() -> AgentFeedReducer:
        return AgentFeedReducer(
            project_root=project_root,
            snapshot_store=snapshot_store_provider() if snapshot_store_provider else None,
            execution_position=execution_position_provider() if execution_position_provider else None,
        )

    @app.get("/agent-feed/v0/health")
    def agent_feed_health():
        return reducer().health().model_dump(mode="json")

    @app.get("/agent-feed/v0/sources")
    def agent_feed_sources():
        return {
            "schema_version": "agent-feed-sources/v0",
            "read_only": True,
            "items": [item.model_dump(mode="json") for item in reducer().source_inventory()],
        }

    @app.get("/agent-feed/v0/execution-readiness")
    def agent_feed_execution_readiness(
        symbols: str = Query(..., min_length=2, max_length=256),
    ):
        symbol_list = list(
            dict.fromkeys(part.strip().upper() for part in symbols.split(",") if part.strip())
        )
        if not symbol_list or len(symbol_list) > MAX_SYMBOLS:
            raise HTTPException(status_code=422, detail=f"between 1 and {MAX_SYMBOLS} symbols are required")
        return reducer().execution_readiness(symbols=symbol_list).model_dump(mode="json", exclude_none=True)

    @app.get("/agent-feed/v0/packet")
    def agent_feed_packet(
        symbols: str = Query(..., min_length=2, max_length=256),
        max_tokens: int = Query(DEFAULT_MAX_TOKENS, ge=MIN_MAX_TOKENS, le=DEFAULT_MAX_TOKENS),
        tf_sec: int = Query(300, ge=1, le=86_400),
    ):
        symbol_list = list(
            dict.fromkeys(part.strip().upper() for part in symbols.split(",") if part.strip())
        )
        if not symbol_list:
            raise HTTPException(status_code=422, detail="at least one symbol is required")
        if len(symbol_list) > MAX_SYMBOLS:
            raise HTTPException(status_code=422, detail=f"at most {MAX_SYMBOLS} symbols are allowed")
        try:
            packet = reducer().build_packet(symbols=symbol_list, max_tokens=max_tokens, tf_sec=tf_sec)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if packet.budget.estimated_tokens > packet.budget.max_tokens_requested:
            raise HTTPException(status_code=503, detail="bounded packet could not satisfy requested token budget")
        return packet.model_dump(mode="json", exclude_none=True)
