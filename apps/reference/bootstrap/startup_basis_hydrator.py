"""Startup basis bars hydrator — seeds FE feature buffers from Binance historical data.

STARTUP-BASIS-HYDRATION: Called during startup warmup gate window to inject historical
closed bars into BarAggregator (WARMUP_IMPORT source mode), which feeds FE feature
buffers. Pairing with seed_startup_bars() on each handler seeds the cold-start counter.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from apps.reference.contracts.runtime_analytics_restore import (
    RuntimeAnalyticsRestoreScope,
    RuntimeAnalyticsRestoreState,
    lookup_restore_status,
)

if TYPE_CHECKING:
    from apps.reference.domains.market_data.bar_aggregator import BarAggregator

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Structured lifecycle event helpers for bootstrap observability
# ---------------------------------------------------------------------------


def _emit_bootstrap_lifecycle(event_name: str, **fields: object) -> None:
    """Emit a structured bootstrap lifecycle log line.

    All events are logged at INFO to the ``startup_basis_hydrator`` logger so
    they land in the operator-visible startup log regardless of sink routing.
    The payload is JSON so it is machine-parseable for post-mortem analysis.
    """
    payload = {
        "event": event_name,
        "ts_ms": int(time.time() * 1000),
        **{k: v for k, v in fields.items() if v is not None},
    }
    LOG.info(
        "BOOTSTRAP_LIFECYCLE %s %s",
        event_name,
        json.dumps(payload, ensure_ascii=False, default=str),
    )


@dataclass(frozen=True)
class StartupBasisSeedRecord:
    strategy_id: str
    symbol: str
    timeframe_sec: int
    required_bars: int
    seeded_bars: int
    source: str

    def to_payload(self) -> dict[str, object]:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timeframe_sec": int(self.timeframe_sec),
            "required_bars": int(self.required_bars),
            "seeded_bars": int(self.seeded_bars),
            "source": self.source,
        }


def hydrate_basis_bars(
    aggregator: "BarAggregator",
    symbol: str,
    tf_sec: int,
    n_bars: int,
    fetch_result: Any,
) -> int:
    """Inject historical closed bars from fetch_result into BarAggregator.

    Args:
        aggregator: BarAggregator instance (None-safe — returns 0)
        symbol: Trading symbol e.g. "BTCUSDT"
        tf_sec: Timeframe in seconds (e.g. 300 for 5m, 900 for 15m)
        n_bars: Max bars to inject (takes last n_bars from fetch result)
        fetch_result: BackfillResult from PillarBackfillService.fetch_candles()

    Returns:
        Number of bars successfully injected.
    """
    from apps.reference.domains.feature_engineering.bar_resampler import Bar

    if aggregator is None:
        LOG.warning(
            "hydrate_basis_bars: bar_aggregator is None, skipping sym=%s tf=%d",
            symbol, tf_sec,
        )
        return 0

    if fetch_result is None or not getattr(fetch_result, "success", False):
        LOG.warning(
            "hydrate_basis_bars: fetch_result not successful sym=%s tf=%d error=%s",
            symbol, tf_sec, getattr(fetch_result, "error", "no_result"),
        )
        return 0

    candles = getattr(fetch_result, "candles", None) or []
    candles_to_import = candles[-n_bars:]  # most recent n_bars
    tf_ms = tf_sec * 1000
    count = 0

    for candle in candles_to_import:
        try:
            start_ts_ms = int(candle.open_time_ms)
            # end_ts_ms = close_boundary - 1 (matches CanonicalBarIdentity invariant)
            end_ts_ms = start_ts_ms + tf_ms - 1
            bar = Bar(
                symbol=symbol,
                timeframe_sec=tf_sec,
                open=Decimal(str(candle.open)),
                high=Decimal(str(candle.high)),
                low=Decimal(str(candle.low)),
                close=Decimal(str(candle.close)),
                volume=Decimal(str(candle.volume)),
                trade_count=1,  # Binance klines API does not expose per-bar trade count
                start_ts_ms=start_ts_ms,
                end_ts_ms=end_ts_ms,
            )
            aggregator.inject_historical_bar(bar)
            count += 1
        except Exception as exc:
            LOG.warning(
                "hydrate_basis_bars: failed to inject bar sym=%s ts=%s err=%s",
                symbol, getattr(candle, "open_time_ms", "?"), exc,
            )

    LOG.info(
        "hydrate_basis_bars: injected %d/%d bars sym=%s tf=%ds",
        count, len(candles_to_import), symbol, tf_sec,
    )
    return count


def _unwrap_seedable_handler(handler_raw: Any) -> Any:
    return getattr(handler_raw, "handler", handler_raw)


def _seed_handler_counter(
    *,
    strategy_id: str,
    symbol: str,
    tf_sec: int,
    required_bars: int,
    seeded_bars: int,
    source: str,
    started_strategy_handlers: dict[str, Any] | None,
) -> StartupBasisSeedRecord | None:
    if seeded_bars <= 0:
        return None
    handler_raw = (started_strategy_handlers or {}).get(strategy_id)
    if handler_raw is None:
        LOG.warning(
            "STARTUP_BASIS_SEED_SKIPPED strategy=%s symbol=%s tf=%ds "
            "reason=handler_missing required=%d",
            strategy_id,
            symbol,
            tf_sec,
            required_bars,
        )
        return None

    handler = _unwrap_seedable_handler(handler_raw)
    if not hasattr(handler, "seed_startup_bars"):
        LOG.warning(
            "STARTUP_BASIS_SEED_SKIPPED strategy=%s symbol=%s tf=%ds "
            "reason=seed_method_missing required=%d",
            strategy_id,
            symbol,
            tf_sec,
            required_bars,
        )
        return None

    handler.seed_startup_bars(symbol, seeded_bars)
    record = StartupBasisSeedRecord(
        strategy_id=strategy_id,
        symbol=symbol,
        timeframe_sec=tf_sec,
        required_bars=required_bars,
        seeded_bars=seeded_bars,
        source=source,
    )
    _emit_bootstrap_lifecycle(
        "STARTUP_BASIS_SEEDED",
        strategy=strategy_id,
        symbol=symbol,
        tf_sec=tf_sec,
        bars_required=required_bars,
        bars_seeded=seeded_bars,
        source=source,
    )
    LOG.info(
        "STARTUP_BASIS_SEEDED strategy=%s symbol=%s tf=%ds seeded=%d/%d source=%s",
        strategy_id,
        symbol,
        tf_sec,
        seeded_bars,
        required_bars,
        source,
    )
    return record


def execute_startup_basis_hydration(
    *,
    hydration_plan: Any,
    restore_report: Any,
    started_strategy_handlers: dict[str, Any] | None,
    bar_aggregator: "BarAggregator" | None,
    backfill_adapter: Any,
    guardian_runtime: Any,
) -> dict[str, object]:
    from apps.reference.domains.feature_engineering.pillar_backfill import (
        PillarBackfillService,
    )

    _emit_bootstrap_lifecycle(
        "STARTUP_BASIS_EXECUTOR_START",
        hydration_plan_present=hydration_plan is not None,
        bar_aggregator_present=bar_aggregator is not None,
        backfill_adapter_present=backfill_adapter is not None,
        guardian_runtime_present=guardian_runtime is not None,
        handlers_available=sorted((started_strategy_handlers or {}).keys()),
    )

    if hydration_plan is None:
        _emit_bootstrap_lifecycle(
            "STARTUP_BASIS_EXECUTOR_DONE",
            outcome="skipped",
            reason="hydration_plan_missing",
        )
        return {
            "imports": {},
            "seeded": [],
            "skipped": ["hydration_plan_missing"],
        }

    import_needs: dict[tuple[str, int], int] = {}
    seed_requirements: list[tuple[str, str, int, int]] = []

    for plan in hydration_plan.plans.values():
        seed_action = any(
            action.action == "SEED_HANDLER_BASIS_COUNTER"
            for action in plan.actions
        )
        replay_action = any(
            action.action == "RESTORE_OR_REPLAY_BASIS_BARS"
            for action in plan.actions
        )
        if seed_action:
            seed_requirements.append(
                (
                    str(plan.strategy_id),
                    str(plan.symbol),
                    int(plan.requirement.basis_tf_sec),
                    int(plan.requirement.basis_required_bars),
                )
            )
        if replay_action:
            key = (str(plan.symbol), int(plan.requirement.basis_tf_sec))
            import_needs[key] = max(
                import_needs.get(key, 0),
                int(plan.requirement.basis_required_bars),
            )

    imported_counts: dict[tuple[str, int], int] = {}
    skipped: list[str] = []

    if import_needs:
        if bar_aggregator is None or backfill_adapter is None:
            skipped.append("basis_import_prerequisites_missing")
            LOG.warning(
                "STARTUP_BASIS_IMPORT_SKIPPED reason=prerequisites_missing "
                "bar_aggregator=%s backfill_adapter=%s",
                bar_aggregator,
                backfill_adapter,
            )
        else:
            basis_service = PillarBackfillService(backfill_adapter)
            _BASIS_IMPORT_MAX_ATTEMPTS = 3
            _BASIS_IMPORT_RETRY_DELAY_SEC = 2.0
            for (symbol, tf_sec), required_bars in import_needs.items():
                _imported = 0
                _last_error: str | None = None
                _attempt = 0
                for _attempt in range(1, _BASIS_IMPORT_MAX_ATTEMPTS + 1):
                    try:
                        fetch_result = guardian_runtime.run(
                            basis_service.fetch_candles(
                                symbol, tf_sec, required_bars),
                            timeout=60.0,
                        )
                        _imported = hydrate_basis_bars(
                            bar_aggregator,
                            symbol,
                            tf_sec,
                            required_bars,
                            fetch_result,
                        )
                        _last_error = getattr(fetch_result, "error", None)
                        if _imported > 0:
                            break
                        if _attempt < _BASIS_IMPORT_MAX_ATTEMPTS:
                            LOG.warning(
                                "STARTUP_BASIS_IMPORT_RETRY symbol=%s tf=%ds "
                                "imported=0/%d attempt=%d/%d error=%s — retrying in %.1fs",
                                symbol, tf_sec, required_bars,
                                _attempt, _BASIS_IMPORT_MAX_ATTEMPTS,
                                _last_error, _BASIS_IMPORT_RETRY_DELAY_SEC,
                            )
                            time.sleep(_BASIS_IMPORT_RETRY_DELAY_SEC)
                    except Exception as exc:
                        _last_error = str(exc)
                        if _attempt < _BASIS_IMPORT_MAX_ATTEMPTS:
                            LOG.warning(
                                "STARTUP_BASIS_IMPORT_RETRY symbol=%s tf=%ds "
                                "attempt=%d/%d error=%s — retrying in %.1fs",
                                symbol, tf_sec,
                                _attempt, _BASIS_IMPORT_MAX_ATTEMPTS,
                                exc, _BASIS_IMPORT_RETRY_DELAY_SEC,
                            )
                            time.sleep(_BASIS_IMPORT_RETRY_DELAY_SEC)
                            continue
                        skipped.append(f"basis_import_failed:{symbol}:{tf_sec}")
                        LOG.error(
                            "STARTUP_BASIS_IMPORT_FAILED symbol=%s tf=%ds error=%s",
                            symbol, tf_sec, exc, exc_info=True,
                        )

                imported_counts[(symbol, tf_sec)] = _imported
                if _imported > 0:
                    _emit_bootstrap_lifecycle(
                        "STARTUP_BASIS_IMPORTED",
                        symbol=symbol,
                        tf_sec=tf_sec,
                        bars_required=required_bars,
                        bars_imported=_imported,
                        attempts=_attempt,
                        success=True,
                    )
                    LOG.info(
                        "STARTUP_BASIS_IMPORTED symbol=%s tf=%ds imported=%d/%d attempts=%d",
                        symbol, tf_sec, _imported, required_bars, _attempt,
                    )
                else:
                    _emit_bootstrap_lifecycle(
                        "STARTUP_BASIS_IMPORT_EXHAUSTED",
                        symbol=symbol,
                        tf_sec=tf_sec,
                        bars_required=required_bars,
                        attempts=_BASIS_IMPORT_MAX_ATTEMPTS,
                        last_error=_last_error,
                    )
                    skipped.append(
                        f"basis_import_exhausted:{symbol}:{tf_sec}")
                    LOG.warning(
                        "STARTUP_BASIS_IMPORT_EXHAUSTED symbol=%s tf=%ds "
                        "required=%d attempts=%d last_error=%s",
                        symbol, tf_sec, required_bars,
                        _BASIS_IMPORT_MAX_ATTEMPTS, _last_error,
                    )

    seeded_records: list[StartupBasisSeedRecord] = []
    for strategy_id, symbol, tf_sec, required_bars in seed_requirements:
        imported_key = (symbol, tf_sec)
        seeded_bars = 0
        source = ""

        if imported_key in imported_counts:
            seeded_bars = min(
                int(imported_counts[imported_key]), required_bars)
            source = "startup_replay_import"
        else:
            snapshot = None
            if restore_report is not None and hasattr(restore_report, "get_snapshot"):
                snapshot = restore_report.get_snapshot(strategy_id, symbol)
            status = lookup_restore_status(
                snapshot, RuntimeAnalyticsRestoreScope.BARS)
            if status is not None and status.state == RuntimeAnalyticsRestoreState.RESTORED:
                seeded_bars = required_bars
                source = "restore_snapshot_bars"

        if seeded_bars <= 0:
            skipped.append(
                f"basis_seed_skipped:{strategy_id}:{symbol}:{tf_sec}")
            LOG.warning(
                "STARTUP_BASIS_SEED_SKIPPED strategy=%s symbol=%s tf=%ds "
                "reason=no_seed_source required=%d",
                strategy_id,
                symbol,
                tf_sec,
                required_bars,
            )
            continue

        record = _seed_handler_counter(
            strategy_id=strategy_id,
            symbol=symbol,
            tf_sec=tf_sec,
            required_bars=required_bars,
            seeded_bars=seeded_bars,
            source=source,
            started_strategy_handlers=started_strategy_handlers,
        )
        if record is not None:
            seeded_records.append(record)

    # Emit per-strategy readiness state after seeding
    _seeded_lookup: dict[tuple[str, str, int], int] = {}
    _seeded_source_lookup: dict[tuple[str, str, int], str] = {}
    for rec in seeded_records:
        _seeded_lookup[(rec.strategy_id, rec.symbol,
                        rec.timeframe_sec)] = rec.seeded_bars
        _seeded_source_lookup[(rec.strategy_id, rec.symbol,
                               rec.timeframe_sec)] = rec.source
    readiness_states: list[dict[str, object]] = []
    for strategy_id, symbol, tf_sec, required_bars in seed_requirements:
        seeded = _seeded_lookup.get((strategy_id, symbol, tf_sec), 0)
        ready = seeded >= required_bars
        seed_source = _seeded_source_lookup.get((strategy_id, symbol, tf_sec))
        readiness_payload = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe_sec": tf_sec,
            "required_bars": required_bars,
            "seeded_bars": seeded,
            "imported_bars": imported_counts.get((symbol, tf_sec), 0),
            "ready": ready,
            "block_reason": None if ready else f"INSUFFICIENT_SEED:{seeded}/{required_bars}",
            "seed_source": seed_source,
        }
        readiness_states.append(readiness_payload)
        _emit_bootstrap_lifecycle(
            "STRATEGY_READINESS_STATE",
            strategy=strategy_id,
            symbol=symbol,
            tf_sec=tf_sec,
            bars_required=required_bars,
            bars_seeded=seeded,
            bars_imported=imported_counts.get((symbol, tf_sec), 0),
            ready=ready,
            block_reason=readiness_payload["block_reason"],
            seed_source=seed_source,
        )

    result = {
        "imports": {
            f"{symbol}:{tf_sec}": imported_count
            for (symbol, tf_sec), imported_count in imported_counts.items()
        },
        "seeded": [record.to_payload() for record in seeded_records],
        "readiness": readiness_states,
        "skipped": skipped,
    }

    _emit_bootstrap_lifecycle(
        "STARTUP_BASIS_EXECUTOR_DONE",
        outcome="completed",
        imports_count=len(imported_counts),
        seeded_count=len(seeded_records),
        skipped_count=len(skipped),
        skipped_reasons=skipped[:10] if skipped else [],
    )

    return result
