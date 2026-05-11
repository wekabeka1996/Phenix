from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from optimization.backtest_interface import BacktestAdapter, ResearchProxySpec, StageResult
from optimization.objectives import AlphaMetrics, RegimeStabilityMetrics
from optimization.research.provenance import ResearchTrialRequest


def build_strategy_proxy_spec(
    *,
    label: str,
    strategy_id: str,
    tradable_symbols: List[str],
    context_symbols: Optional[List[str]] = None,
) -> ResearchProxySpec:
    tracked_symbols = list(dict.fromkeys([*(tradable_symbols or []), *((context_symbols or []))]))
    assignments = {str(symbol): [str(strategy_id)] for symbol in tradable_symbols}
    return ResearchProxySpec(
        label=label,
        tracked_symbols=[str(symbol) for symbol in tracked_symbols],
        tradable_symbols=[str(symbol) for symbol in tradable_symbols],
        context_symbols=[str(symbol) for symbol in (context_symbols or [])],
        strategy_assignments=assignments,
    )


@dataclass(frozen=True)
class ResearchHarnessConfig:
    config_dir: Path
    proxy: ResearchProxySpec
    fail_on_scoring_fallback: bool = False
    trial_artifacts_dir: Optional[Path] = None


class ResearchHarnessRunner:
    """Strict-config-compatible research runner for proxy-universe backtests."""

    def __init__(self, *, config: ResearchHarnessConfig):
        self.config = config
        self.adapter = BacktestAdapter(
            config_dir=config.config_dir,
            research_proxy=config.proxy,
            fail_on_scoring_fallback=config.fail_on_scoring_fallback,
            trial_artifacts_dir=config.trial_artifacts_dir,
        )

    def run_stage0(
        self,
        overrides: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trial_request: Optional[ResearchTrialRequest] = None,
    ) -> Tuple[RegimeStabilityMetrics, StageResult]:
        return self.adapter.run_stage0(
            overrides,
            start_date=start_date,
            end_date=end_date,
            trial_request=trial_request,
        )

    def run_stage1(
        self,
        overrides: Dict[str, Any],
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        trial_request: Optional[ResearchTrialRequest] = None,
    ) -> Tuple[AlphaMetrics, StageResult]:
        return self.adapter.run_stage1(
            overrides,
            start_date=start_date,
            end_date=end_date,
            trial_request=trial_request,
        )