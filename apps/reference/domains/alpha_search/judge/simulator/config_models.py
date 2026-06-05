"""Strict config models for the offline judge simulator."""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


LeverageSource = Literal["none", "instruments_yaml"]
QtyNormalization = Literal["raw", "instrument_step_size"]
MinNotionalPolicy = Literal["fail_closed", "skip"]


class EconomicsConfig(BaseModel):
    """PKG-3 economics / notional contract for Judge USD ROI computation.

    Authority: JUDGE_REPLAY_AND_FINANCIAL_VALIDATION plan §10 PKG-3.

    Presence semantics (hard contract):
      * If this block is OMITTED from `config/judge_simulator.yaml`, USD ROI
        metrics are DISABLED ("pct_only" mode). No hidden default notional.
      * If this block is PRESENT, USD ROI metrics are computed and the
        materializer (PKG-1) MUST record the source pointers and resolved
        values in `outcomes_manifest.json`.

    Units / semantics:
      notional_usd_per_trade : quote-currency notional per simulated trade.
                               Required when block is present.
      leverage_source        : "none"            → USD ROI is raw (no margin ROI).
                               "instruments_yaml" → per-symbol leverage looked up
                                 from `config/aurora/instruments.yaml` under
                                 `instruments.<SYMBOL>.execution.target_leverage`.
      qty_normalization      : "raw"                  → qty = notional/entry_price (Decimal).
                               "instrument_step_size" → reuse production
                                 qty_normalizer (LOT_SIZE / MIN_QTY / MIN_NOTIONAL).
      min_notional_policy    : "fail_closed" → outcomes whose normalized qty
                                 fails min_qty/min_notional are SKIPPED with
                                 a dedicated skip_reason (NO bump-up).
                               "skip" → equivalent to fail_closed (kept as an
                                 explicit alias for documentation).
      roi_usd_targets        : list of absolute USD profit thresholds to track
                               (e.g., [5.0, 8.0] for the +5/+8 USD diagnostic).
      instruments_config_path: SSOT path for per-symbol precision and leverage.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    notional_usd_per_trade: float = Field(..., gt=0.0)
    leverage_source: LeverageSource = "none"
    qty_normalization: QtyNormalization = "instrument_step_size"
    min_notional_policy: MinNotionalPolicy = "fail_closed"
    roi_usd_targets: List[float] = Field(default_factory=list)
    instruments_config_path: str = Field(
        default="config/aurora/instruments.yaml", min_length=1
    )

    @field_validator("roi_usd_targets")
    @classmethod
    def _targets_non_negative(cls, value: List[float]) -> List[float]:
        for v in value:
            if v <= 0:
                raise ValueError(
                    "roi_usd_targets entries must be > 0 (USD profit threshold)"
                )
        return value


class SimulatorConfig(BaseModel):
    """Phase 5 Package 5A simulator configuration.

    This config is intentionally independent from JudgeCortexConfig and is
    used only by the offline simulator foundation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    judge_logs_path: str = Field(..., min_length=1)
    outcome_data_path: str = Field(..., min_length=1)
    calibration_dataset_path: str = Field(..., min_length=1)
    summary_report_path: str = Field(..., min_length=1)
    fee_per_cycle_bps: float = Field(default=25.0, ge=0.0)
    slippage_pct: float = Field(default=0.1, ge=0.0)
    economics: Optional[EconomicsConfig] = None

    @field_validator(
        "judge_logs_path",
        "outcome_data_path",
        "calibration_dataset_path",
        "summary_report_path",
    )
    @classmethod
    def path_must_be_non_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("path fields must be a non-empty string")
        return value

    @property
    def usd_roi_enabled(self) -> bool:
        """True iff the PKG-3 economics block is present (USD ROI computable)."""
        return self.economics is not None
