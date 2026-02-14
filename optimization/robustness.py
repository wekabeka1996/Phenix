"""
optimization/robustness.py — Stage 2 robustness validation.

Walk-Forward, Block Bootstrap, Execution Stress, and Cold Holdout gate.
"""

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Walk-Forward Validator
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardFold:
    """A single train/gap/test split defined by indices."""
    fold_id: int
    train_start: int
    train_end: int
    gap_start: int
    gap_end: int
    test_start: int
    test_end: int


@dataclass
class WalkForwardResult:
    """Result of a single Walk-Forward fold."""
    fold_id: int
    train_sharpe: float = 0.0
    test_sharpe: float = 0.0
    train_mdd_pct: float = 0.0
    test_mdd_pct: float = 0.0
    test_roi_pct: float = 0.0


class WalkForwardValidator:
    """
    Rolling Walk-Forward validation as defined in the concept doc.

    Split: Train 60% / Gap 10% / Test 30% (configurable).
    Rolls forward by test_size each fold.
    """

    def __init__(
        self,
        *,
        train_pct: float = 0.60,
        gap_pct: float = 0.10,
        test_pct: float = 0.30,
        n_folds: int = 3,
    ):
        assert abs(train_pct + gap_pct + test_pct - 1.0) < 1e-6, \
            f"Splits must sum to 1.0, got {train_pct + gap_pct + test_pct}"
        self.train_pct = train_pct
        self.gap_pct = gap_pct
        self.test_pct = test_pct
        self.n_folds = n_folds

    def generate_folds(self, total_bars: int) -> List[WalkForwardFold]:
        """
        Generate rolling Walk-Forward folds.

        For each fold, the window slides forward by test_size bars.
        Train size stays constant; each fold tests on fresh data.

        Returns:
            List of WalkForwardFold with index ranges
        """
        if total_bars < 10:
            LOG.warning(f"Too few bars ({total_bars}) for Walk-Forward")
            return []

        window_size = total_bars  # First fold uses entire dataset
        train_size = int(window_size * self.train_pct)
        gap_size = int(window_size * self.gap_pct)
        test_size = int(window_size * self.test_pct)

        # Adjust for rounding
        remainder = total_bars - (train_size + gap_size + test_size)
        train_size += remainder  # Give remainder to train

        folds = []
        for fold_id in range(self.n_folds):
            offset = fold_id * test_size
            t_start = offset
            t_end = offset + train_size
            g_start = t_end
            g_end = g_start + gap_size
            te_start = g_end
            te_end = te_start + test_size

            if te_end > total_bars:
                LOG.info(f"Fold {fold_id}: test_end ({te_end}) > total_bars ({total_bars}), stopping")
                break

            folds.append(WalkForwardFold(
                fold_id=fold_id,
                train_start=t_start,
                train_end=t_end,
                gap_start=g_start,
                gap_end=g_end,
                test_start=te_start,
                test_end=te_end,
            ))

        LOG.info(f"Generated {len(folds)} Walk-Forward folds from {total_bars} bars")
        return folds


# ---------------------------------------------------------------------------
# Block Bootstrap
# ---------------------------------------------------------------------------

@dataclass
class BootstrapResult:
    """Aggregated Block Bootstrap results."""
    n_resamples: int = 0
    pnl_samples: List[float] = field(default_factory=list)
    sharpe_samples: List[float] = field(default_factory=list)
    pnl_positive_pct: float = 0.0      # % of samples with PnL > 0
    sharpe_mean: float = 0.0
    sharpe_p5: float = 0.0             # 5th percentile Sharpe
    sharpe_p95: float = 0.0            # 95th percentile Sharpe


class BlockBootstrap:
    """
    Block Bootstrap resampling of trade returns.

    Preserves autocorrelation by resampling contiguous blocks
    instead of individual observations.
    """

    def __init__(
        self,
        *,
        n_resamples: int = 100,
        block_size: int = 30,
        confidence_level: float = 0.95,
        seed: Optional[int] = None,
    ):
        self.n_resamples = n_resamples
        self.block_size = block_size
        self.confidence_level = confidence_level
        self.rng = random.Random(seed)

    def resample(self, returns: List[float]) -> BootstrapResult:
        """
        Perform Block Bootstrap on a returns series.

        Args:
            returns: List of per-bar or per-trade returns

        Returns:
            BootstrapResult with distribution statistics
        """
        n = len(returns)
        if n < self.block_size:
            LOG.warning(f"Returns ({n}) shorter than block_size ({self.block_size})")
            return BootstrapResult()

        pnl_samples = []
        sharpe_samples = []

        for _ in range(self.n_resamples):
            # Build resampled series from random blocks
            resampled = []
            while len(resampled) < n:
                start = self.rng.randint(0, n - self.block_size)
                resampled.extend(returns[start:start + self.block_size])
            resampled = resampled[:n]  # Trim to original length

            # Compute PnL and Sharpe for this resample
            pnl = sum(resampled)
            pnl_samples.append(pnl)

            mean_r = sum(resampled) / len(resampled)
            if len(resampled) >= 2:
                var_r = sum((r - mean_r) ** 2 for r in resampled) / (len(resampled) - 1)
                std_r = math.sqrt(var_r) if var_r > 0 else 0.0
                sharpe = mean_r / std_r if std_r > 1e-12 else 0.0
            else:
                sharpe = 0.0
            sharpe_samples.append(sharpe)

        # Aggregate
        pnl_positive_pct = sum(1 for p in pnl_samples if p > 0) / max(len(pnl_samples), 1)

        sorted_sharpe = sorted(sharpe_samples)
        p5_idx = int(len(sorted_sharpe) * 0.05)
        p95_idx = int(len(sorted_sharpe) * 0.95)

        return BootstrapResult(
            n_resamples=self.n_resamples,
            pnl_samples=pnl_samples,
            sharpe_samples=sharpe_samples,
            pnl_positive_pct=pnl_positive_pct,
            sharpe_mean=sum(sharpe_samples) / max(len(sharpe_samples), 1),
            sharpe_p5=sorted_sharpe[p5_idx] if sorted_sharpe else 0.0,
            sharpe_p95=sorted_sharpe[p95_idx] if sorted_sharpe else 0.0,
        )


# ---------------------------------------------------------------------------
# Execution Stress Test
# ---------------------------------------------------------------------------

@dataclass
class StressTestResult:
    """Result of execution stress testing."""
    original_sharpe: float = 0.0
    stressed_sharpe: float = 0.0
    sharpe_degradation: float = 0.0
    original_pnl: float = 0.0
    stressed_pnl: float = 0.0


class ExecutionStress:
    """
    Execution Stress Test — inject random latency, slippage, and fee distortions.

    Simulates worst-case execution conditions to check strategy survival.
    """

    def __init__(
        self,
        *,
        latency_ms_range: Tuple[int, int] = (50, 500),
        slippage_bps_range: Tuple[int, int] = (1, 10),
        fee_multiplier_range: Tuple[float, float] = (1.0, 1.5),
        funding_bps_per_day_range: Tuple[float, float] = (0.0, 0.0),
        seed: Optional[int] = None,
    ):
        self.latency_ms_range = latency_ms_range
        self.slippage_bps_range = slippage_bps_range
        self.fee_multiplier_range = fee_multiplier_range
        self.funding_bps_per_day_range = funding_bps_per_day_range
        self.rng = random.Random(seed)

    def sample_overrides(self, *, seed: Optional[int] = None) -> Dict[str, Any]:
        """Sample one execution-stress override set for a full backtest rerun."""
        rng = random.Random(seed) if seed is not None else self.rng
        return {
            "fee_mult": float(rng.uniform(*self.fee_multiplier_range)),
            "slippage_bps": float(rng.uniform(*self.slippage_bps_range)),
            "latency_ms": int(rng.randint(int(self.latency_ms_range[0]), int(self.latency_ms_range[1]))),
            "funding_bps_per_day": float(rng.uniform(*self.funding_bps_per_day_range)),
        }

    def apply_stress_to_returns(self, returns: List[float]) -> List[float]:
        """
        Apply random execution costs to a returns series.

        Each return is reduced by a random slippage + fee cost.
        """
        stressed = []
        for r in returns:
            slippage_bps = self.rng.uniform(*self.slippage_bps_range)
            fee_mult = self.rng.uniform(*self.fee_multiplier_range)

            # Slippage reduces return on both sides (entry + exit)
            cost = (slippage_bps / 10000) * 2 * fee_mult
            stressed.append(r - cost)

        return stressed


# ---------------------------------------------------------------------------
# Cold Holdout Gate
# ---------------------------------------------------------------------------

@dataclass
class HoldoutResult:
    """Result of the cold holdout go/no-go gate."""
    passed: bool = False
    sharpe: float = 0.0
    mdd_pct: float = 0.0
    mdd_p90_pct: float = 0.0   # 90th percentile MDD from bootstrap
    roi_pct: float = 0.0
    reason: str = ""


class ColdHoldoutGate:
    """
    Final go/no-go gate on data never seen during optimization.

    The holdout period (last N months) is completely isolated from
    Stage 0, Stage 1, and Stage 2. Only one run is performed.
    """

    def __init__(
        self,
        *,
        min_sharpe: float = 1.0,
        max_mdd_p90_pct: float = 25.0,
    ):
        self.min_sharpe = min_sharpe
        self.max_mdd_p90_pct = max_mdd_p90_pct

    def evaluate(
        self,
        sharpe: float,
        mdd_pct: float,
        mdd_p90_pct: float = 0.0,
        roi_pct: float = 0.0,
    ) -> HoldoutResult:
        """
        Evaluate holdout results against acceptance criteria.

        Returns:
            HoldoutResult with pass/fail and reason
        """
        reasons = []

        if sharpe < self.min_sharpe:
            reasons.append(f"Sharpe {sharpe:.3f} < {self.min_sharpe}")

        if mdd_p90_pct > self.max_mdd_p90_pct:
            reasons.append(f"MDD(p90) {mdd_p90_pct:.1f}% > {self.max_mdd_p90_pct}%")

        passed = len(reasons) == 0
        reason = " | ".join(reasons) if reasons else "All criteria passed"

        result = HoldoutResult(
            passed=passed,
            sharpe=sharpe,
            mdd_pct=mdd_pct,
            mdd_p90_pct=mdd_p90_pct,
            roi_pct=roi_pct,
            reason=reason,
        )

        if passed:
            LOG.info(f"✅ HOLDOUT GATE PASSED: Sharpe={sharpe:.3f}, MDD(p90)={mdd_p90_pct:.1f}%")
        else:
            LOG.warning(f"❌ HOLDOUT GATE FAILED: {reason}")

        return result
