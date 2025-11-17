"""SSOT v1.0 canonical configuration schema.

DEPRECATED: v1 monolith config, kept for historical reference.

This module defines the frozen Pydantic models that describe the
single-source-of-truth (SSOT) contract for trading configuration data.
The structure mirrors resolver outputs and enforces compatibility rules
(documented in `config_contract_map.md`).

The schema is additive-only: new fields must default to safe values and
respect existing behaviours. Legacy aliases are exposed via Pydantic
`alias` attributes so that historical YAML keys remain readable without
violating the SSOT design.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _decimal_from_any(value: Any, default: Decimal) -> Decimal:
    try:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
    except Exception:
        return default


def _non_negative_int(value: Any, default: int) -> int:
    try:
        candidate = int(value)
        return candidate if candidate >= 0 else default
    except Exception:
        return default


class BracketSideModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    fixed_bps: Decimal = Field(default=Decimal("50"))

    @field_validator("fixed_bps", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Decimal:
        return _decimal_from_any(value, Decimal("50"))


class BracketsRetryModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    backoff_ms: List[int] = Field(default_factory=lambda: [120, 250, 400])
    max_attempts: int = Field(default=3)
    fallback_to_limit: bool = Field(default=True)

    @field_validator("backoff_ms", mode="before")
    @classmethod
    def _clean_backoff(cls, value: Any) -> List[int]:
        if isinstance(value, (list, tuple)):
            cleaned = [int(v) for v in value if isinstance(
                v, (int, float)) and int(v) > 0]
            return cleaned or [120, 250, 400]
        if value is None:
            return [120, 250, 400]
        try:
            candidate = int(value)
            return [candidate] if candidate > 0 else [120, 250, 400]
        except Exception:
            return [120, 250, 400]

    @field_validator("max_attempts", mode="before")
    @classmethod
    def _positive_attempts(cls, value: Any) -> int:
        candidate = _non_negative_int(value, 3)
        return max(candidate, 1)


class ManageBracketsModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    enable: bool = Field(default=False)
    oco_emulation: bool = Field(default=False)
    working_type_default: str = Field(default="MARK_PRICE")
    price_protect: bool = Field(default=False)
    keep_single_bracket_set: bool = Field(default=True)
    atomic_close: bool = Field(default=True)
    bracket_tracking: bool = Field(default=True)
    sl: Optional[BracketSideModel] = Field(default=None)
    tp: Optional[BracketSideModel] = Field(default=None)
    retry: BracketsRetryModel = Field(default_factory=BracketsRetryModel)


class OrphanMonitorModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=True)
    run_on_startup: bool = Field(default=True)
    periodic_interval_sec: int = Field(default=300)
    min_order_age_sec: int = Field(default=0)
    batch_cancel_limit: int = Field(default=50)
    rate_limit_per_min: int = Field(default=120)


class QuickProfitModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = Field(default=False)
    mode: str = Field(default="fixed_usd")
    target_usd: Decimal = Field(default=Decimal("2.0"))
    priority: str = Field(default="highest")
    ignore_other_rules: bool = Field(default=False)

    @field_validator("target_usd", mode="before")
    @classmethod
    def _coerce_target(cls, value: Any) -> Decimal:
        return _decimal_from_any(value, Decimal("2.0"))


class TrailingModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    enable: bool = Field(default=False)
    activation_profit_atr_k: float = Field(default=1.0)
    cooldown_sec: float = Field(default=0.0)
    step_bps: Decimal = Field(default=Decimal("0"))

    @field_validator("step_bps", mode="before")
    @classmethod
    def _coerce_step(cls, value: Any) -> Decimal:
        return _decimal_from_any(value, Decimal("0"))


class EmergencyModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    enable: bool = Field(default=False)
    emergency_sl_bps: Decimal = Field(default=Decimal("100"))
    wait_mode_bars: int = Field(default=2)

    @field_validator("emergency_sl_bps", mode="before")
    @classmethod
    def _coerce_sl(cls, value: Any) -> Decimal:
        return _decimal_from_any(value, Decimal("100"))


class GuardianModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    unified: bool = Field(default=True)
    emit_tidy_event: bool = Field(default=True)
    poll_interval_ms: int = Field(default=500, alias="poll_interval_ms")
    cleanup_ttl_ms: int = Field(default=6000)
    symbol_cooldown_ms: int = Field(default=4000)

    @field_validator("poll_interval_ms", "cleanup_ttl_ms", "symbol_cooldown_ms", mode="before")
    @classmethod
    # type: ignore[override]
    def _ensure_non_negative(cls, value: Any, info) -> int:
        default_map = {
            "poll_interval_ms": 500,
            "cleanup_ttl_ms": 6000,
            "symbol_cooldown_ms": 4000,
        }
        default = default_map.get(info.field_name, 0)
        return _non_negative_int(value, default)


class WatchdogModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    ack_ttl_ms: int = Field(default=8000)
    fill_ttl_ms: int = Field(default=30000)
    source: str = Field(default="execution.watchdog")

    @field_validator("ack_ttl_ms", "fill_ttl_ms", mode="before")
    @classmethod
    def _positive_ttl(cls, value: Any, info) -> int:  # type: ignore[override]
        default = 8000 if info.field_name == "ack_ttl_ms" else 30000
        return _non_negative_int(value, default)


class ExecutionManageModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    auto: bool = Field(default=False)
    brackets: ManageBracketsModel = Field(default_factory=ManageBracketsModel)
    orphan_monitor: OrphanMonitorModel = Field(
        default_factory=OrphanMonitorModel)
    quick_profit: QuickProfitModel = Field(default_factory=QuickProfitModel)
    trailing: TrailingModel = Field(default_factory=TrailingModel)
    emergency: EmergencyModel = Field(default_factory=EmergencyModel)
    order_guardian: GuardianModel = Field(default_factory=GuardianModel)
    watchdog: WatchdogModel = Field(default_factory=WatchdogModel)


class LeverageDefaultsModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    default: Decimal = Field(default=Decimal("20"))
    per_symbol: Dict[str, Decimal] = Field(default_factory=dict)

    @field_validator("default", mode="before")
    @classmethod
    def _coerce_default(cls, value: Any) -> Decimal:
        return _decimal_from_any(value, Decimal("20"))

    @field_validator("per_symbol", mode="before")
    @classmethod
    def _coerce_map(cls, value: Any) -> Dict[str, Decimal]:
        result: Dict[str, Decimal] = {}
        if isinstance(value, dict):
            for key, raw in value.items():
                if key in {"default", "__default__"}:
                    continue
                result[str(key)] = _decimal_from_any(raw, Decimal("20"))
        return result


class ExposureCapsModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_equity_utilization_pct: Decimal = Field(default=Decimal("0.20"))
    max_portfolio_fraction: Decimal = Field(default=Decimal("0.20"))
    max_directional_ratio: Decimal = Field(default=Decimal("2.0"))
    per_symbol_cap_pct: Decimal = Field(default=Decimal("0.08"))
    max_side_utilization_pct: Dict[str, Decimal] = Field(
        default_factory=lambda: {"long": Decimal(
            "0.12"), "short": Decimal("0.12")}
    )

    @field_validator(
        "max_equity_utilization_pct",
        "max_portfolio_fraction",
        "max_directional_ratio",
        "per_symbol_cap_pct",
        mode="before",
    )
    @classmethod
    # type: ignore[override]
    def _coerce_ratio(cls, value: Any, info) -> Decimal:
        defaults = {
            "max_equity_utilization_pct": Decimal("0.20"),
            "max_portfolio_fraction": Decimal("0.20"),
            "max_directional_ratio": Decimal("2.0"),
            "per_symbol_cap_pct": Decimal("0.08"),
        }
        default = defaults.get(info.field_name, Decimal("0"))
        candidate = _decimal_from_any(value, default)
        if candidate > 1 and info.field_name != "max_directional_ratio":
            candidate = candidate / Decimal("100")
        return candidate

    @field_validator("max_side_utilization_pct", mode="before")
    @classmethod
    def _coerce_side_map(cls, value: Any) -> Dict[str, Decimal]:
        if not isinstance(value, dict):
            return {"long": Decimal("0.12"), "short": Decimal("0.12")}
        return {
            "long": _decimal_from_any(value.get("long"), Decimal("0.12")),
            "short": _decimal_from_any(value.get("short"), Decimal("0.12")),
        }


class PendingReservationsModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    pending_ttl_sec: int = Field(default=90)
    post_fill_hold_ttl_sec: int = Field(default=5)
    positions_stale_ttl_sec: int = Field(default=5)


class ExposureFallbackModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    policy: str = Field(default="fail_closed")
    risk_reduction_pct: Decimal = Field(default=Decimal("0.5"))
    backoff_ms: List[int] = Field(default_factory=lambda: [200, 500, 1000])
    max_attempts: int = Field(default=3)
    enabled: bool = Field(default=True)

    @field_validator("risk_reduction_pct", mode="before")
    @classmethod
    def _coerce_pct(cls, value: Any) -> Decimal:
        candidate = _decimal_from_any(value, Decimal("0.5"))
        if candidate > 1:
            candidate = candidate / Decimal("100")
        return candidate

    @field_validator("backoff_ms", mode="before")
    @classmethod
    def _coerce_backoff(cls, value: Any) -> List[int]:
        if isinstance(value, (list, tuple)):
            cleaned = [int(v) for v in value if int(v) > 0]
            return cleaned or [200, 500, 1000]
        if value is None:
            return [200, 500, 1000]
        try:
            candidate = int(value)
            return [candidate] if candidate > 0 else [200, 500, 1000]
        except Exception:
            return [200, 500, 1000]

    @field_validator("max_attempts", mode="before")
    @classmethod
    def _coerce_attempts(cls, value: Any) -> int:
        candidate = _non_negative_int(value, 3)
        return max(candidate, 1)


class ExposureModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    caps: ExposureCapsModel = Field(default_factory=ExposureCapsModel)
    reservations: PendingReservationsModel = Field(
        default_factory=PendingReservationsModel)
    leverage_defaults: LeverageDefaultsModel = Field(
        default_factory=LeverageDefaultsModel)
    count_pending_orders: bool = Field(default=True)
    exclude_reduce_only: bool = Field(default=True)
    fallback: ExposureFallbackModel = Field(
        default_factory=ExposureFallbackModel)


class ExecutionFallbackModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    backoff_ms: List[int] = Field(default_factory=lambda: [200, 500, 1000])
    max_attempts: int = Field(default=3)


class ExecutionModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    manage: ExecutionManageModel = Field(default_factory=ExecutionManageModel)
    exposure: ExposureModel = Field(default_factory=ExposureModel)
    fallback: ExecutionFallbackModel = Field(
        default_factory=ExecutionFallbackModel)


class DailyLimitsModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_loss_usd: Decimal = Field(default=Decimal("250"))
    max_drawdown_pct: Decimal = Field(default=Decimal("8"))
    reset_time_utc: str = Field(default="00:00")

    @field_validator("max_loss_usd", mode="before")
    @classmethod
    def _coerce_loss(cls, value: Any) -> Decimal:
        return _decimal_from_any(value, Decimal("250"))

    @field_validator("max_drawdown_pct", mode="before")
    @classmethod
    def _coerce_drawdown(cls, value: Any) -> Decimal:
        candidate = _decimal_from_any(value, Decimal("8"))
        if candidate <= 1:
            candidate *= Decimal("100")
        return candidate


class RiskSoftLimitsModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: str = Field(default="clip")
    clip_min_notional_usdt: Decimal = Field(default=Decimal("10"))
    directional_ratio_max: Decimal = Field(default=Decimal("3"))
    side_exposure_usdt: Decimal = Field(default=Decimal("600"))
    margin_exposure_usdt: Decimal = Field(default=Decimal("1100"))


class TradingRiskModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    daily_limits: DailyLimitsModel = Field(default_factory=DailyLimitsModel)
    soft_limits: RiskSoftLimitsModel = Field(
        default_factory=RiskSoftLimitsModel)


class InstrumentModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    trade_cooldown_sec: Optional[float] = Field(default=None)
    cooldown_sec: Optional[float] = Field(default=None, alias="cooldown_sec")

    @model_validator(mode="after")
    def _validate_cooldown(self) -> "InstrumentModel":
        if self.trade_cooldown_sec is not None and self.trade_cooldown_sec < 0:
            self.trade_cooldown_sec = 0.0
        if self.cooldown_sec is not None and self.cooldown_sec < 0:
            self.cooldown_sec = 0.0
        return self


class DomainConfigEntryModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    trading_mode: Optional[str] = Field(default=None)


class BinanceApiEnvModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_key: Optional[str] = Field(default=None)
    api_secret: Optional[str] = Field(default=None)
    rest_url: Optional[str] = Field(default=None)
    ws_url: Optional[str] = Field(default=None)


class BinanceApiModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    live: BinanceApiEnvModel = Field(default_factory=BinanceApiEnvModel)
    testnet: BinanceApiEnvModel = Field(default_factory=BinanceApiEnvModel)


class OpsConfigModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    metrics_url: str = Field(default="http://127.0.0.1:8000/metrics")
    reports_dir: str = Field(default="reports")


class TradingModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: str = Field(default="testnet")
    execution: ExecutionModel = Field(default_factory=ExecutionModel)
    risk: TradingRiskModel = Field(default_factory=TradingRiskModel)
    instruments: Dict[str, InstrumentModel] = Field(default_factory=dict)
    domain_configuration: Dict[str, DomainConfigEntryModel] = Field(
        default_factory=dict)


class SSOTConfig(BaseModel):
    """Canonical SSOT configuration for trading stack."""

    model_config = ConfigDict(extra="allow")

    trading_mode: str = Field(default="testnet")
    trading: TradingModel = Field(default_factory=TradingModel)
    binance_api: BinanceApiModel = Field(default_factory=BinanceApiModel)
    ops: OpsConfigModel = Field(default_factory=OpsConfigModel)

    @model_validator(mode="after")
    def _sync_modes(self) -> "SSOTConfig":
        if self.trading.mode != self.trading_mode:
            self.trading.mode = self.trading_mode
        return self

    @field_validator("trading_mode", mode="before")
    @classmethod
    def _normalize_mode(cls, value: Any) -> str:
        allowed = {
            "testnet",
            "live",
            "production",
            "hybrid_live_data_testnet_exec",
            "shadow_live",
            "full_testnet",
            "full_live",
        }
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in allowed:
                return lowered
        return "testnet"


__all__ = [
    "SSOTConfig",
    "ExecutionModel",
    "ExecutionManageModel",
    "ExposureModel",
    "TradingRiskModel",
    "InstrumentModel",
    "DomainConfigEntryModel",
]
