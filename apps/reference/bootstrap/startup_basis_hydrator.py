"""Startup basis bars hydrator — seeds FE feature buffers from Binance historical data.

STARTUP-BASIS-HYDRATION: Called during startup warmup gate window to inject historical
closed bars into BarAggregator (WARMUP_IMPORT source mode), which feeds FE feature
buffers. Pairing with seed_startup_bars() on each handler seeds the cold-start counter.
"""
from __future__ import annotations

import logging
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

    if hydration_plan is None:
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
            for (symbol, tf_sec), required_bars in import_needs.items():
                try:
                    fetch_result = guardian_runtime.run(
                        basis_service.fetch_candles(symbol, tf_sec, required_bars),
                        timeout=60.0,
                    )
                    imported_counts[(symbol, tf_sec)] = hydrate_basis_bars(
                        bar_aggregator,
                        symbol,
                        tf_sec,
                        required_bars,
                        fetch_result,
                    )
                    LOG.info(
                        "STARTUP_BASIS_IMPORTED symbol=%s tf=%ds imported=%d/%d success=%s",
                        symbol,
                        tf_sec,
                        imported_counts[(symbol, tf_sec)],
                        required_bars,
                        bool(fetch_result and getattr(fetch_result, "success", False)),
                    )
                except Exception as exc:
                    skipped.append(f"basis_import_failed:{symbol}:{tf_sec}")
                    LOG.error(
                        "STARTUP_BASIS_IMPORT_FAILED symbol=%s tf=%ds error=%s",
                        symbol,
                        tf_sec,
                        exc,
                        exc_info=True,
                    )

    seeded_records: list[StartupBasisSeedRecord] = []
    for strategy_id, symbol, tf_sec, required_bars in seed_requirements:
        imported_key = (symbol, tf_sec)
        seeded_bars = 0
        source = ""

        if imported_key in imported_counts:
            seeded_bars = min(int(imported_counts[imported_key]), required_bars)
            source = "startup_replay_import"
        else:
            snapshot = None
            if restore_report is not None and hasattr(restore_report, "get_snapshot"):
                snapshot = restore_report.get_snapshot(strategy_id, symbol)
            status = lookup_restore_status(snapshot, RuntimeAnalyticsRestoreScope.BARS)
            if status is not None and status.state == RuntimeAnalyticsRestoreState.RESTORED:
                seeded_bars = required_bars
                source = "restore_snapshot_bars"

        if seeded_bars <= 0:
            skipped.append(f"basis_seed_skipped:{strategy_id}:{symbol}:{tf_sec}")
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

    return {
        "imports": {
            f"{symbol}:{tf_sec}": imported_count
            for (symbol, tf_sec), imported_count in imported_counts.items()
        },
        "seeded": [record.to_payload() for record in seeded_records],
        "skipped": skipped,
    }
