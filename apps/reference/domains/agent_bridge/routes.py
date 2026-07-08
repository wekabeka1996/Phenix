from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Query

from .reducer import AgentFeedReducer, DEFAULT_MAX_TOKENS, MAX_SYMBOLS, MIN_MAX_TOKENS
from .scenario_memory import (
    MAX_QUERY_TOKENS,
    MAX_SUMMARY_TOKENS,
    QueryType,
    ScenarioMemoryStore,
)
from .agent_intent_dry_run import AgentIntentDryRunLedger, ArchiveIntegrityError, QueryScope


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

    memory = ScenarioMemoryStore(project_root)
    intent_ledger = AgentIntentDryRunLedger(
        project_root / "ops" / "agent_bridge" / "agent_intents"
    )

    def reducer() -> AgentFeedReducer:
        return AgentFeedReducer(
            project_root=project_root,
            snapshot_store=snapshot_store_provider() if snapshot_store_provider else None,
            execution_position=execution_position_provider() if execution_position_provider else None,
            scenario_memory_store=memory,
        )

    @app.get("/agent-memory/v0/health")
    def agent_memory_health():
        index = memory.build_index()
        return {
            "schema_version": "scenario-memory-health/v0",
            "read_only": True,
            "status": "ready" if index.validation_status == "valid" else "degraded",
            "review_count": index.review_count,
            "completed_count": index.completed_count,
            "unresolved_count": index.unresolved_count,
            "validation_status": index.validation_status,
            "errors": index.validation_errors,
        }

    @app.get("/agent-intent/v0/health")
    def agent_intent_health():
        stats = intent_ledger.stats()
        return {
            "schema_version": "agent-intent-dry-run-health/v0",
            "read_only": True,
            "mode": "dry_run_no_execution",
            "record_count": stats.valid_records,
            "submitted_count": stats.submitted_count,
            "exchange_touched_count": stats.exchange_touched_count,
            "malformed_rows": stats.malformed_rows,
            "partial_lines": stats.partial_lines,
            "status": "ready" if stats.conflicting_duplicate_rows == 0 else "degraded",
        }

    @app.get("/agent-intent/v0/latest")
    def agent_intent_latest(
        scope: QueryScope = Query("active"),
        limit: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0, le=100_000),
    ):
        try:
            return intent_ledger.query(scope=scope, limit=limit, offset=offset)
        except ArchiveIntegrityError as exc:
            raise HTTPException(status_code=503, detail={"error": "archive_integrity_failed", "diagnostics": exc.diagnostics}) from exc

    @app.get("/agent-intent/v0/query")
    def agent_intent_query(
        symbol: Optional[str] = Query(default=None, min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$"),
        scope: QueryScope = Query("active"),
        status: Optional[str] = Query(default=None, min_length=3, max_length=64, pattern=r"^dry_run_[a-z_]+$"),
        action: Optional[str] = Query(default=None, min_length=3, max_length=32, pattern=r"^[A-Z_]+$"),
        limit: int = Query(10, ge=1, le=100),
        offset: int = Query(0, ge=0, le=100_000),
    ):
        try:
            result = intent_ledger.query(
                scope=scope, symbol=symbol, status=status, action=action,
                limit=limit, offset=offset,
            )
        except ArchiveIntegrityError as exc:
            raise HTTPException(status_code=503, detail={"error": "archive_integrity_failed", "diagnostics": exc.diagnostics}) from exc
        return {**result, "symbol": symbol, "status": status, "action": action}

    @app.get("/agent-intent/v0/stats")
    def agent_intent_stats():
        return intent_ledger.stats().model_dump(mode="json", exclude_none=True)

    @app.get("/agent-intent/v0/archives")
    def agent_intent_archives():
        return intent_ledger.archives()

    @app.get("/agent-intent/v0/archive-stats")
    def agent_intent_archive_stats():
        stats = intent_ledger.stats()
        return {
            "schema_version": "agent-intent-dry-run-archive-stats/v0", "read_only": True,
            "archive_count": stats.archive_count,
            "archive_valid_records": stats.archive_valid_records,
            "archive_bytes": stats.archive_bytes,
            "archive_integrity_errors": stats.archive_integrity_errors,
        }

    @app.get("/agent-intent/v0/manifest-index")
    def agent_intent_manifest_index():
        return intent_ledger.rebuild_manifest_index(persist=False)

    @app.get("/agent-intent/v0/manifest-chain")
    def agent_intent_manifest_chain():
        index = intent_ledger.rebuild_manifest_index(persist=False)
        return {
            "schema_version": "agent-intent-dry-run-manifest-chain/v0", "read_only": True,
            "chain_verdict": index["chain_verdict"], "chain_counts": index["chain_counts"],
            "items": index["archive_manifests"], "diagnostics": index["diagnostics"],
            "index_source_hash": index["index_source_hash"],
        }

    @app.get("/agent-memory/v0/index")
    def agent_memory_index():
        index = memory.build_index()
        if index.validation_status == "invalid":
            raise HTTPException(status_code=503, detail=index.validation_errors or ["scenario memory ledger unavailable"])
        return index.model_dump(mode="json", exclude_none=True)

    @app.get("/agent-memory/v0/query")
    def agent_memory_query(
        query_type: QueryType = Query("latest"),
        symbol: Optional[str] = Query(default=None, min_length=2, max_length=32, pattern=r"^[A-Z0-9_-]+$"),
        horizon: Optional[str] = Query(default=None, min_length=2, max_length=32),
        scenario: Optional[str] = Query(default=None, min_length=2, max_length=64),
        packet_id: Optional[str] = Query(default=None, min_length=8, max_length=128, pattern=r"^afp_[0-9a-f]+$"),
        limit: int = Query(5, ge=1, le=20),
        max_tokens: int = Query(MAX_QUERY_TOKENS, ge=100, le=MAX_QUERY_TOKENS),
    ):
        try:
            return memory.query(
                query_type=query_type,
                symbol=symbol,
                horizon=horizon,
                scenario=scenario,
                packet_id=packet_id,
                limit=limit,
                max_tokens=max_tokens,
            ).model_dump(mode="json", exclude_none=True)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/agent-memory/v0/summary")
    def agent_memory_summary(
        symbols: str = Query(..., min_length=2, max_length=256),
        max_tokens: int = Query(MAX_SUMMARY_TOKENS, ge=100, le=MAX_SUMMARY_TOKENS),
    ):
        symbol_list = list(dict.fromkeys(part.strip().upper() for part in symbols.split(",") if part.strip()))
        if not symbol_list or len(symbol_list) > MAX_SYMBOLS:
            raise HTTPException(status_code=422, detail=f"between 1 and {MAX_SYMBOLS} symbols are required")
        try:
            return memory.summary(symbol_list, max_tokens=max_tokens).model_dump(mode="json", exclude_none=True)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

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

    @app.get("/agent-session-context/v0/{session_id}")
    def agent_session_context(session_id: str):
        from .session_context_read_model import SessionContextReadModel
        # Cockpit memory is located under tools/deepseek-terminal-agent/.agent_memory/
        memory_path = project_root / "tools" / "deepseek-terminal-agent" / ".agent_memory"
        reader = SessionContextReadModel(memory_root=memory_path)
        try:
            context = reader.load_context(session_id)
            return context.model_dump(mode="json")
        except FileNotFoundError as exc:
            # Differentiate between missing store/sessions (503) and specific session missing (404)
            msg = str(exc)
            if "Memory root directory does not exist" in msg or "Sessions directory does not exist" in msg:
                raise HTTPException(
                    status_code=503,
                    detail=f"Cockpit memory store is unavailable: {msg}"
                ) from exc
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

