from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.reference.config.shared.atoms import (
    BarGatingConfig,
    BehaviorFsmConfig,
    DirectionStrengthScoringConfig,
    KellyConfig,
    LiquidityGateConfig,
    PositionSizingConfig,
    QosConfig,
    ROIExitConfig,
    SignalWeights,
    SignalsConfig,
)
from apps.reference.config.shared.enums import (
    DangerZoneExitType,
    ExecutionGateName,
    OperationalMode,
)


_REGIME_CONFIDENCE_GATE_KEYS = frozenset({
    "DEFAULT",
    "TREND_UP",
    "TREND_DOWN",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "MEAN_REVERSION",
    "UNCERTAIN",
})
_REGIME_CONFIDENCE_SIDE_KEYS = frozenset({"BUY", "SELL"})

_LOW_VOL_COST_FLOOR_RUNTIME_MODES = frozenset(
    {"testnet", "hybrid_live_data_testnet_exec", "live", "production"}
)

_LOW_VOL_DIRECTION_CONFIDENCE_SOURCES = frozenset(
    {"strategy_confidence", "signal_score", "final_score", "judge_confidence"}
)
_LOW_VOL_RAW_SIGNED_SCORE_SOURCES = frozenset({"signal_score", "final_score"})
_LOW_VOL_NORMALIZED_CONFIDENCE_SOURCES = frozenset(
    {"strategy_confidence", "judge_confidence"})


def _validate_regime_confidence_threshold_mapping_shape(value, *, field_name: str):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f'{field_name} must be a mapping')
    for raw_key, raw_threshold in value.items():
        if not isinstance(raw_key, str):
            raise ValueError(f'{field_name} keys must be strings')
        if raw_threshold is None or isinstance(raw_threshold, bool):
            raise ValueError(
                f'{field_name} values must be numeric thresholds in [0.0, 1.0]'
            )
        try:
            threshold = float(raw_threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f'{field_name} values must be numeric thresholds in [0.0, 1.0]'
            ) from exc
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError(f'{field_name} values must be in [0.0, 1.0]')
    return value


def _normalize_regime_confidence_threshold_mapping(
    mapping,
    *,
    field_name: str,
    require_default: bool = True,
) -> Dict[str, float]:
    if not mapping:
        if require_default:
            raise ValueError(f'{field_name} requires DEFAULT when provided')
        raise ValueError(f'{field_name} must not be empty when provided')
    normalized: Dict[str, float] = {}
    for raw_key, threshold in mapping.items():
        key = str(raw_key)
        canonical = key.strip()
        if key != canonical or canonical != canonical.upper():
            raise ValueError(
                f'{field_name} keys must be canonical uppercase labels')
        if canonical not in _REGIME_CONFIDENCE_GATE_KEYS:
            allowed = ', '.join(sorted(_REGIME_CONFIDENCE_GATE_KEYS))
            raise ValueError(
                f"unsupported {field_name} key '{raw_key}'; allowed: {allowed}"
            )
        normalized[canonical] = float(threshold)
    if require_default and 'DEFAULT' not in normalized:
        raise ValueError(f'{field_name} requires DEFAULT when provided')
    return normalized


def _validate_symbol_regime_confidence_threshold_mapping_shape(value, *, field_name: str):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f'{field_name} must be a mapping')
    for raw_symbol, raw_mapping in value.items():
        if not isinstance(raw_symbol, str):
            raise ValueError(f'{field_name} keys must be strings')
        symbol = raw_symbol.strip()
        if not symbol or raw_symbol != symbol or symbol != symbol.upper():
            raise ValueError(
                f'{field_name} keys must be canonical uppercase symbols')
        _validate_regime_confidence_threshold_mapping_shape(
            raw_mapping,
            field_name=f'{field_name}.{symbol}',
        )
    return value


def _normalize_symbol_regime_confidence_threshold_mapping(
    mapping,
    *,
    field_name: str,
    require_default: bool = True,
) -> Dict[str, Dict[str, float]]:
    if not mapping:
        raise ValueError(f'{field_name} must not be empty when provided')
    normalized: Dict[str, Dict[str, float]] = {}
    for raw_symbol, raw_mapping in mapping.items():
        symbol = str(raw_symbol)
        canonical = symbol.strip()
        if symbol != canonical or canonical != canonical.upper():
            raise ValueError(
                f'{field_name} keys must be canonical uppercase symbols')
        normalized[canonical] = _normalize_regime_confidence_threshold_mapping(
            raw_mapping,
            field_name=f'{field_name}.{canonical}',
            require_default=require_default,
        )
    return normalized


def _validate_regime_confidence_side_threshold_mapping_shape(value, *, field_name: str):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f'{field_name} must be a mapping')
    allowed = ', '.join(
        sorted(key for key in _REGIME_CONFIDENCE_GATE_KEYS if key != 'DEFAULT')
    )
    for raw_key, raw_mapping in value.items():
        if not isinstance(raw_key, str):
            raise ValueError(f'{field_name} keys must be strings')
        key = raw_key.strip()
        if raw_key != key or key != key.upper():
            raise ValueError(
                f'{field_name} keys must be canonical uppercase regime labels'
            )
        if key == 'DEFAULT' or key not in _REGIME_CONFIDENCE_GATE_KEYS:
            raise ValueError(
                f"unsupported {field_name} key '{raw_key}'; allowed: {allowed}"
            )
        if raw_mapping is None:
            raise ValueError(f'{field_name}.{key} must be a side mapping')
    return value


def _normalize_regime_confidence_side_threshold_mapping(
    mapping,
    *,
    field_name: str,
):
    if not mapping:
        raise ValueError(f'{field_name} must not be empty when provided')
    normalized = {}
    allowed = ', '.join(
        sorted(key for key in _REGIME_CONFIDENCE_GATE_KEYS if key != 'DEFAULT')
    )
    for raw_key, raw_mapping in mapping.items():
        key = str(raw_key)
        canonical = key.strip()
        if key != canonical or canonical != canonical.upper():
            raise ValueError(
                f'{field_name} keys must be canonical uppercase regime labels'
            )
        if canonical == 'DEFAULT' or canonical not in _REGIME_CONFIDENCE_GATE_KEYS:
            raise ValueError(
                f"unsupported {field_name} key '{raw_key}'; allowed: {allowed}"
            )
        normalized[canonical] = raw_mapping
    return normalized


def _validate_symbol_regime_confidence_side_threshold_mapping_shape(value, *, field_name: str):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f'{field_name} must be a mapping')
    for raw_symbol, raw_mapping in value.items():
        if not isinstance(raw_symbol, str):
            raise ValueError(f'{field_name} keys must be strings')
        symbol = raw_symbol.strip()
        if not symbol or raw_symbol != symbol or symbol != symbol.upper():
            raise ValueError(
                f'{field_name} keys must be canonical uppercase symbols'
            )
        _validate_regime_confidence_side_threshold_mapping_shape(
            raw_mapping,
            field_name=f'{field_name}.{symbol}',
        )
    return value


def _normalize_symbol_regime_confidence_side_threshold_mapping(
    mapping,
    *,
    field_name: str,
):
    if not mapping:
        raise ValueError(f'{field_name} must not be empty when provided')
    normalized = {}
    for raw_symbol, raw_mapping in mapping.items():
        symbol = str(raw_symbol)
        canonical = symbol.strip()
        if symbol != canonical or canonical != canonical.upper():
            raise ValueError(
                f'{field_name} keys must be canonical uppercase symbols'
            )
        normalized[canonical] = _normalize_regime_confidence_side_threshold_mapping(
            raw_mapping,
            field_name=f'{field_name}.{canonical}',
        )
    return normalized


def _validate_regime_confidence_band_contract(
    *,
    min_value: Optional[float],
    max_value: Optional[float],
    field_name: str,
) -> None:
    if min_value is None or max_value is None:
        return
    if float(max_value) < float(min_value):
        raise ValueError(
            f'{field_name} max threshold must be >= min threshold'
        )


def _validate_regime_confidence_band_mapping_contract(
    *,
    min_mapping: Optional[Dict[str, float]],
    max_mapping: Optional[Dict[str, float]],
    field_name: str,
) -> None:
    if not min_mapping or not max_mapping:
        return
    common_keys = set(min_mapping).intersection(max_mapping)
    for key in common_keys:
        _validate_regime_confidence_band_contract(
            min_value=min_mapping.get(key),
            max_value=max_mapping.get(key),
            field_name=f'{field_name}.{key}',
        )


def _validate_regime_confidence_band_symbol_contract(
    *,
    min_mapping: Optional[Dict[str, Dict[str, float]]],
    max_mapping: Optional[Dict[str, Dict[str, float]]],
    field_name: str,
) -> None:
    if not min_mapping or not max_mapping:
        return
    common_symbols = set(min_mapping).intersection(max_mapping)
    for symbol in common_symbols:
        _validate_regime_confidence_band_mapping_contract(
            min_mapping=min_mapping.get(symbol),
            max_mapping=max_mapping.get(symbol),
            field_name=f'{field_name}.{symbol}',
        )


def _validate_regime_confidence_side_threshold_value(value, *, field_name: str):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(
            f'{field_name} values must be numeric thresholds in [0.0, 1.0]'
        )
    try:
        threshold = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f'{field_name} values must be numeric thresholds in [0.0, 1.0]'
        ) from exc
    if threshold < 0.0 or threshold > 1.0:
        raise ValueError(f'{field_name} values must be in [0.0, 1.0]')
    return threshold


class RegimeConfidenceSideMinThresholdConfig(BaseModel):
    """Side-aware strategy-local min regime-confidence override."""

    model_config = ConfigDict(extra='forbid')

    BUY: Optional[float] = Field(default=None)
    SELL: Optional[float] = Field(default=None)

    @field_validator('BUY', 'SELL', mode='before')
    @classmethod
    def validate_side_threshold(cls, value, info):
        return _validate_regime_confidence_side_threshold_value(
            value,
            field_name=f'side_min_threshold.{info.field_name}',
        )

    @model_validator(mode='after')
    def validate_presence(self) -> 'RegimeConfidenceSideMinThresholdConfig':
        explicit_null = [
            side for side in self.model_fields_set if getattr(self, side) is None
        ]
        if explicit_null:
            raise ValueError(
                f"side_min_threshold does not support explicit null for {', '.join(sorted(explicit_null))}"
            )
        if all(getattr(self, side) is None for side in _REGIME_CONFIDENCE_SIDE_KEYS):
            raise ValueError('side_min_threshold requires at least one side')
        return self


class RegimeConfidenceMaxSideOverrideConfig(BaseModel):
    """Side-aware strategy-local max regime-confidence override."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator('threshold', mode='before')
    @classmethod
    def validate_threshold_shape(cls, value):
        if value is None:
            return None
        return _validate_regime_confidence_side_threshold_value(
            value,
            field_name='side_max_override.threshold',
        )

    @model_validator(mode='after')
    def validate_contract(self) -> 'RegimeConfidenceMaxSideOverrideConfig':
        if self.enabled and self.threshold is None:
            raise ValueError(
                'side_max_override enabled=true requires threshold'
            )
        if not self.enabled and self.threshold is not None:
            raise ValueError(
                'side_max_override enabled=false requires threshold to be omitted'
            )
        return self


class RegimeConfidenceSideMaxOverrideMapConfig(BaseModel):
    """Per-side map of max regime-confidence overrides."""

    model_config = ConfigDict(extra='forbid')

    BUY: Optional[RegimeConfidenceMaxSideOverrideConfig] = Field(default=None)
    SELL: Optional[RegimeConfidenceMaxSideOverrideConfig] = Field(default=None)

    @model_validator(mode='after')
    def validate_presence(self) -> 'RegimeConfidenceSideMaxOverrideMapConfig':
        explicit_null = [
            side for side in self.model_fields_set if getattr(self, side) is None
        ]
        if explicit_null:
            raise ValueError(
                f"side_max_override_map does not support explicit null for {', '.join(sorted(explicit_null))}"
            )
        if all(getattr(self, side) is None for side in _REGIME_CONFIDENCE_SIDE_KEYS):
            raise ValueError(
                'side_max_override_map requires at least one side'
            )
        return self


def _validate_regime_confidence_side_band_mapping_contract(
    *,
    min_mapping: Optional[Dict[str, RegimeConfidenceSideMinThresholdConfig]],
    max_mapping: Optional[Dict[str, RegimeConfidenceSideMaxOverrideMapConfig]],
    field_name: str,
) -> None:
    if not min_mapping or not max_mapping:
        return
    common_regimes = set(min_mapping).intersection(max_mapping)
    for regime_key in common_regimes:
        min_side_cfg = min_mapping.get(regime_key)
        max_side_cfg = max_mapping.get(regime_key)
        for side in _REGIME_CONFIDENCE_SIDE_KEYS:
            min_value = getattr(min_side_cfg, side, None)
            max_override = getattr(max_side_cfg, side, None)
            if min_value is None or max_override is None or not max_override.enabled:
                continue
            _validate_regime_confidence_band_contract(
                min_value=min_value,
                max_value=max_override.threshold,
                field_name=f'{field_name}.{regime_key}.{side}',
            )


def _validate_regime_confidence_side_band_symbol_contract(
    *,
    min_mapping: Optional[Dict[str, Dict[str, RegimeConfidenceSideMinThresholdConfig]]],
    max_mapping: Optional[Dict[str, Dict[str, RegimeConfidenceSideMaxOverrideMapConfig]]],
    field_name: str,
) -> None:
    if not min_mapping or not max_mapping:
        return
    common_symbols = set(min_mapping).intersection(max_mapping)
    for symbol in common_symbols:
        _validate_regime_confidence_side_band_mapping_contract(
            min_mapping=min_mapping.get(symbol),
            max_mapping=max_mapping.get(symbol),
            field_name=f'{field_name}.{symbol}',
        )


def _normalize_low_vol_gate_threshold_mapping(mapping, *, field_name: str) -> Dict[str, float]:
    normalized = _normalize_regime_confidence_threshold_mapping(
        mapping,
        field_name=field_name,
    )
    if 'LOW_VOLATILITY' not in normalized:
        raise ValueError(
            f'{field_name} requires explicit LOW_VOLATILITY threshold')
    return normalized


def _validate_low_vol_strategy_symbol_threshold_overrides_shape(value, *, field_name: str):
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f'{field_name} must be a non-empty mapping when provided')
    for raw_strategy_id, symbol_map in value.items():
        if not isinstance(raw_strategy_id, str):
            raise ValueError(f'{field_name} strategy keys must be strings')
        strategy_id = raw_strategy_id.strip()
        if not strategy_id:
            raise ValueError(
                f'{field_name} strategy keys must be non-empty strings')
        if raw_strategy_id != strategy_id:
            raise ValueError(
                f'{field_name} strategy keys must not contain surrounding whitespace')
        if not isinstance(symbol_map, dict) or not symbol_map:
            raise ValueError(
                f'{field_name}.{strategy_id} must be a non-empty symbol mapping')
        for raw_symbol, thresholds in symbol_map.items():
            if not isinstance(raw_symbol, str):
                raise ValueError(
                    f'{field_name}.{strategy_id} symbol keys must be strings')
            symbol = raw_symbol.strip()
            if not symbol:
                raise ValueError(
                    f'{field_name}.{strategy_id} symbol keys must be non-empty strings')
            if raw_symbol != symbol:
                raise ValueError(
                    f'{field_name}.{strategy_id} symbol keys must not contain surrounding whitespace')
            _validate_regime_confidence_threshold_mapping_shape(
                thresholds,
                field_name=f'{field_name}.{strategy_id}.{symbol}',
            )
    return value


def _normalize_low_vol_strategy_symbol_threshold_overrides(
    value,
    *,
    field_name: str,
) -> Dict[str, Dict[str, Dict[str, float]]] | None:
    if value is None:
        return None
    normalized: Dict[str, Dict[str, Dict[str, float]]] = {}
    for raw_strategy_id, symbol_map in value.items():
        strategy_id = str(raw_strategy_id).strip()
        normalized_symbol_map: Dict[str, Dict[str, float]] = {}
        for raw_symbol, thresholds in symbol_map.items():
            symbol = str(raw_symbol).strip().upper()
            if raw_symbol != symbol:
                raise ValueError(
                    f'{field_name}.{strategy_id} symbol keys must be canonical uppercase labels')
            normalized_symbol_map[symbol] = _normalize_low_vol_gate_threshold_mapping(
                thresholds,
                field_name=f'{field_name}.{strategy_id}.{symbol}',
            )
        normalized[strategy_id] = normalized_symbol_map
    return normalized


def _validate_low_vol_runtime_modes(value, *, field_name: str):
    if not isinstance(value, list) or not value:
        raise ValueError(f'{field_name} must be a non-empty list')
    normalized: List[str] = []
    seen: set[str] = set()
    for raw_mode in value:
        if not isinstance(raw_mode, str):
            raise ValueError(f'{field_name} entries must be strings')
        mode = raw_mode.strip()
        if raw_mode != mode:
            raise ValueError(
                f'{field_name} entries must not contain surrounding whitespace')
        if mode not in _LOW_VOL_COST_FLOOR_RUNTIME_MODES:
            allowed = ', '.join(sorted(_LOW_VOL_COST_FLOOR_RUNTIME_MODES))
            raise ValueError(
                f"unsupported {field_name} mode '{raw_mode}'; allowed: {allowed}"
            )
        if mode in seen:
            raise ValueError(f'{field_name} entries must be unique')
        seen.add(mode)
        normalized.append(mode)
    return normalized


def _validate_low_vol_direction_sources(value, *, field_name: str):
    if not isinstance(value, list) or not value:
        raise ValueError(f'{field_name} must be a non-empty list')
    normalized: List[str] = []
    seen: set[str] = set()
    for raw_source in value:
        if not isinstance(raw_source, str):
            raise ValueError(f'{field_name} entries must be strings')
        source = raw_source.strip()
        if raw_source != source:
            raise ValueError(
                f'{field_name} entries must not contain surrounding whitespace')
        if source not in _LOW_VOL_DIRECTION_CONFIDENCE_SOURCES:
            allowed = ', '.join(sorted(_LOW_VOL_DIRECTION_CONFIDENCE_SOURCES))
            raise ValueError(
                f"unsupported {field_name} source '{raw_source}'; allowed: {allowed}"
            )
        if source in seen:
            raise ValueError(f'{field_name} entries must be unique')
        seen.add(source)
        normalized.append(source)
    return normalized


def _validate_low_vol_source_family(value, *, field_name: str, allowed: frozenset[str]) -> List[str]:
    """Validate a source family list (may be empty — both lists share that responsibility)."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f'{field_name} must be a list')
    normalized: List[str] = []
    seen: set[str] = set()
    for raw_source in value:
        if not isinstance(raw_source, str):
            raise ValueError(f'{field_name} entries must be strings')
        source = raw_source.strip()
        if raw_source != source:
            raise ValueError(
                f'{field_name} entries must not contain surrounding whitespace')
        if source not in allowed:
            raise ValueError(
                f"unsupported {field_name} source '{raw_source}'; allowed: {sorted(allowed)}"
            )
        if source in seen:
            raise ValueError(f'{field_name} entries must be unique')
        seen.add(source)
        normalized.append(source)
    return normalized


class RegimeConfidenceGateConfig(BaseModel):
    """Strategy-local regime-confidence admission threshold overrides."""

    model_config = ConfigDict(extra='forbid')

    min_by_regime: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-regime regime_confidence thresholds. '
            'When provided, DEFAULT is required and strategy values override domain defaults.'
        ),
    )
    min_by_symbol: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-symbol regime_confidence thresholds. '
            'When provided, each symbol mapping requires DEFAULT and overrides strategy/domain defaults for that symbol.'
        ),
    )
    min_by_regime_side: Optional[Dict[str, RegimeConfidenceSideMinThresholdConfig]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-regime, per-side regime_confidence floors. '
            'Exact regime+side matches override legacy strategy/domain thresholds. DEFAULT+side is not supported.'
        ),
    )
    min_by_symbol_regime_side: Optional[Dict[str, Dict[str, RegimeConfidenceSideMinThresholdConfig]]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-symbol, per-regime, per-side regime_confidence floors. '
            'Exact symbol+regime+side matches override all other strategy/domain thresholds.'
        ),
    )
    max_by_regime: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-regime regime_confidence upper bounds. '
            'When provided, explicit regime-specific keys apply; DEFAULT may be omitted.'
        ),
    )
    max_by_symbol: Optional[Dict[str, Dict[str, float]]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-symbol regime_confidence upper bounds. '
            'When provided, each symbol mapping may be partial and overrides strategy/domain defaults for the listed keys.'
        ),
    )
    max_by_regime_side: Optional[Dict[str, RegimeConfidenceSideMaxOverrideMapConfig]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-regime, per-side regime_confidence ceilings. '
            'Exact regime+side matches may raise the ceiling or disable it explicitly with enabled=false.'
        ),
    )
    max_by_symbol_regime_side: Optional[Dict[str, Dict[str, RegimeConfidenceSideMaxOverrideMapConfig]]] = Field(
        default=None,
        description=(
            'Optional strategy-local per-symbol, per-regime, per-side regime_confidence ceilings. '
            'Exact symbol+regime+side matches may raise the ceiling or disable it explicitly with enabled=false.'
        ),
    )

    @field_validator('min_by_regime', mode='before')
    @classmethod
    def validate_min_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.min_by_regime',
        )

    @field_validator('min_by_symbol', mode='before')
    @classmethod
    def validate_min_by_symbol_shape(cls, value):
        return _validate_symbol_regime_confidence_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.min_by_symbol',
        )

    @field_validator('min_by_regime_side', mode='before')
    @classmethod
    def validate_min_by_regime_side_shape(cls, value):
        return _validate_regime_confidence_side_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.min_by_regime_side',
        )

    @field_validator('min_by_symbol_regime_side', mode='before')
    @classmethod
    def validate_min_by_symbol_regime_side_shape(cls, value):
        return _validate_symbol_regime_confidence_side_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.min_by_symbol_regime_side',
        )

    @field_validator('max_by_regime', mode='before')
    @classmethod
    def validate_max_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.max_by_regime',
        )

    @field_validator('max_by_symbol', mode='before')
    @classmethod
    def validate_max_by_symbol_shape(cls, value):
        return _validate_symbol_regime_confidence_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.max_by_symbol',
        )

    @field_validator('max_by_regime_side', mode='before')
    @classmethod
    def validate_max_by_regime_side_shape(cls, value):
        return _validate_regime_confidence_side_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.max_by_regime_side',
        )

    @field_validator('max_by_symbol_regime_side', mode='before')
    @classmethod
    def validate_max_by_symbol_regime_side_shape(cls, value):
        return _validate_symbol_regime_confidence_side_threshold_mapping_shape(
            value,
            field_name='safety_gates.regime_confidence.max_by_symbol_regime_side',
        )

    @model_validator(mode='after')
    def validate_threshold_contract(self) -> 'RegimeConfidenceGateConfig':
        min_by_regime = _normalize_regime_confidence_threshold_mapping(
            self.min_by_regime,
            field_name='safety_gates.regime_confidence.min_by_regime',
        ) if self.min_by_regime is not None else None
        min_by_symbol = _normalize_symbol_regime_confidence_threshold_mapping(
            self.min_by_symbol,
            field_name='safety_gates.regime_confidence.min_by_symbol',
        ) if self.min_by_symbol is not None else None
        min_by_regime_side = _normalize_regime_confidence_side_threshold_mapping(
            self.min_by_regime_side,
            field_name='safety_gates.regime_confidence.min_by_regime_side',
        ) if self.min_by_regime_side is not None else None
        min_by_symbol_regime_side = _normalize_symbol_regime_confidence_side_threshold_mapping(
            self.min_by_symbol_regime_side,
            field_name='safety_gates.regime_confidence.min_by_symbol_regime_side',
        ) if self.min_by_symbol_regime_side is not None else None
        max_by_regime = _normalize_regime_confidence_threshold_mapping(
            self.max_by_regime,
            field_name='safety_gates.regime_confidence.max_by_regime',
            require_default=False,
        ) if self.max_by_regime is not None else None
        max_by_symbol = _normalize_symbol_regime_confidence_threshold_mapping(
            self.max_by_symbol,
            field_name='safety_gates.regime_confidence.max_by_symbol',
            require_default=False,
        ) if self.max_by_symbol is not None else None
        max_by_regime_side = _normalize_regime_confidence_side_threshold_mapping(
            self.max_by_regime_side,
            field_name='safety_gates.regime_confidence.max_by_regime_side',
        ) if self.max_by_regime_side is not None else None
        max_by_symbol_regime_side = _normalize_symbol_regime_confidence_side_threshold_mapping(
            self.max_by_symbol_regime_side,
            field_name='safety_gates.regime_confidence.max_by_symbol_regime_side',
        ) if self.max_by_symbol_regime_side is not None else None

        _validate_regime_confidence_band_mapping_contract(
            min_mapping=min_by_regime,
            max_mapping=max_by_regime,
            field_name='safety_gates.regime_confidence',
        )
        _validate_regime_confidence_band_symbol_contract(
            min_mapping=min_by_symbol,
            max_mapping=max_by_symbol,
            field_name='safety_gates.regime_confidence',
        )
        _validate_regime_confidence_side_band_mapping_contract(
            min_mapping=min_by_regime_side,
            max_mapping=max_by_regime_side,
            field_name='safety_gates.regime_confidence',
        )
        _validate_regime_confidence_side_band_symbol_contract(
            min_mapping=min_by_symbol_regime_side,
            max_mapping=max_by_symbol_regime_side,
            field_name='safety_gates.regime_confidence',
        )

        self.min_by_regime = min_by_regime
        self.min_by_symbol = min_by_symbol
        self.min_by_regime_side = min_by_regime_side
        self.min_by_symbol_regime_side = min_by_symbol_regime_side
        self.max_by_regime = max_by_regime
        self.max_by_symbol = max_by_symbol
        self.max_by_regime_side = max_by_regime_side
        self.max_by_symbol_regime_side = max_by_symbol_regime_side
        return self


class SafetyGatesConfig(BaseModel):
    """Safety gates control for directional sanity and price motion gates.

    DM-SAFETY-BYPASSES-P1: Replaces hardcoded strategy_id == 'aurora' check.
    - Aurora (trend-following): enabled=true -> gates APPLY
    - Mean Reversion (counter-trend): enabled=false -> gates SKIPPED
    - Missing config -> FAIL-CLOSED (trade blocked)

    Phase 0.6: system_stress_policy controls how Gate 0.5 behaves per-strategy:
    - off       -> Gate 0.5 fully bypassed (even EXTREME is ignored)
    - attenuate -> EXTREME=DENY(NRR-059); STRESS=ALLOW + reduce margin_pct_mult by factor
    - block     -> EXTREME and STRESS both DENY(NRR-059)
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description='Enable directional sanity and price motion gates for this strategy'
    )
    system_stress_policy: Literal["off", "attenuate", "block"] = Field(
        ..., description=(
            "System stress gate policy: "
            "off=bypass Gate 0.5 entirely, "
            "attenuate=EXTREME denied + STRESS reduces size, "
            "block=EXTREME and STRESS both denied"
        ),
    )
    stress_attenuation_factor: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Multiplicative factor applied to margin_pct_mult when STRESS and policy=attenuate",
    )
    regime_confidence: Optional[RegimeConfidenceGateConfig] = Field(
        default=None,
        description=(
            "Optional strategy-local regime-confidence admission threshold overrides. "
            "Absent block means the domain-level directional_sanity thresholds apply."
        ),
    )


class DecisionModeOverrideConfig(BaseModel):
    """Mode-specific decision overrides (testnet/production).

    CFG-DICT-ANY-BURN-13: Typed config for mode overrides.
    Allows ANY field from DecisionConfig to be overridden.
    extra='allow' justified: config_loader merges ANY override key.
    """

    model_config = ConfigDict(extra='forbid')

    signal_threshold: Optional[float] = Field(...)


class AnchorShockVetoConfig(BaseModel):
    """Anchor Shock Veto configuration.

    Phase 3 Fix: Block BUY signals when anchor (BTC) is crashing.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable anchor shock veto")
    anchor_symbol: str = Field(
        ..., description="Symbol used as anchor")
    threshold: float = Field(
        ..., description="Block BUY if macro_resid < threshold")


class HoldingPeriodConfig(BaseModel):
    """Minimum Holding Period configuration (Anti-Churn Gate).

    RFC: docs/RFC_min_duration_logic.md
    Prevents HFT-style churn by enforcing minimum time in position before
    allowing signal-based exits. Does NOT affect safety exits (SL/TP/Risk).
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable minimum holding period gate")
    min_duration_sec: float = Field(
        ..., description="Minimum seconds to hold position before allowing signal-based exit")
    emergency_exit_threshold: float = Field(
        ..., description="|score| threshold for emergency override (allows exit even within holding period)")
    apply_to_flips: bool = Field(
        ..., description="Also apply holding period to FLIP signals (not just exits)")


class VolAdjGatesConfig(BaseModel):
    """Volume-Adjusted Gates configuration (VOL-ADJ-GATES-01).

    Anti-Flat: Block entry when normalized motion < threshold (fee churn in dead market).
    Anti-FOMO: Block entry when normalized motion > threshold (snapback risk).

    Uses pm_norm_<window>s from price_motion feature domain.
    Formula: pm_norm = clip(ret_window / (k_vol * vol_window), -1, 1)
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable vol-adj gates (Anti-Flat + Anti-FOMO)")
    anti_flat_sigma: float = Field(
        ..., ge=0.0,
        le=1.0,
        description="Block ENTRY if |pm_norm| < anti_flat_sigma (dead market, fee churn)"
    )
    anti_fomo_sigma: float = Field(
        ..., ge=1.0,
        le=10.0,
        description="Block ENTRY if |pm_norm| > anti_fomo_sigma (extreme impulse, snapback risk)"
    )
    motion_window_sec: int = Field(
        ..., ge=10,
        description="Which pm_norm window to use: 10, 60, 300, or 900 (seconds)"
    )


class DashboardConfig(BaseModel):
    """
    Phase 6: Dashboard Metrics Configuration.
    Tracks strategy performance (Sharpe, WinRate, Coverage).
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    sharpe_window_days: int = Field(..., ge=1)
    metrics: List[str] = Field(
        ..., description="List of metrics to track and log"
    )


class RegimeShiftInceptionConfig(BaseModel):
    """Regime-shift inception: rescue-only micro-entry on first bar of regime shift."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description='Enable inception detection (fail-closed default)')
    action: Literal["none", "micro_size", "confirm_next_bar"] = Field(
        ..., description='Action on inception: none=telemetry only, micro_size=25% entry, confirm_next_bar=wait'
    )
    micro_size_fraction: float = Field(
        ..., gt=0.0, le=1.0,
        description='Position size fraction for micro-entry (0.25 = 25% of normal)'
    )


class RegimeSmoothingConfig(BaseModel):
    """EMA/ramp smoothing for regime threshold multipliers."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description='Enable regime multiplier smoothing (fail-closed default)')
    method: Literal["ema", "linear_ramp"] = Field(
        ..., description='Smoothing method')
    ema_alpha: float = Field(..., gt=0.0, le=1.0,
                             description='EMA decay factor (0.3 = ~5-bar half-life)')
    ramp_bars: int = Field(
        ..., ge=1, le=20, description='Linear ramp duration in bars (used when method=linear_ramp)')


class PyramidingRuleV1Config(BaseModel):
    """A single scoped allow-exception rule for pyramiding policy V1."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique rule identifier")
    strategy_id: str = Field(..., description="Strategy this rule applies to (e.g. aurora)")
    regimes: List[str] = Field(..., description="Regimes where this rule activates (e.g. [LOW_VOLATILITY])")
    sides: List[str] = Field(..., description="Sides where this rule activates (BUY or SELL)")
    symbols: Optional[List[str]] = Field(
        None, description="Symbol allowlist. None = all symbols for the strategy.",
    )
    enabled: bool = Field(..., description="Enable this specific rule")

    @field_validator("sides", mode="before")
    @classmethod
    def _validate_sides(cls, v: Any) -> Any:
        if isinstance(v, list):
            for s in v:
                if str(s).upper() not in {"BUY", "SELL"}:
                    raise ValueError(f"Invalid side {s!r}. Must be BUY or SELL.")
        return v

    @field_validator("regimes", mode="before")
    @classmethod
    def _validate_regimes(cls, v: Any) -> Any:
        _valid = {
            "LOW_VOLATILITY", "HIGH_VOLATILITY", "TREND_UP", "TREND_DOWN",
            "MEAN_REVERSION", "UNCERTAIN", "FLAT_LOW", "FLAT_NORMAL", "FLAT_HIGH",
        }
        if isinstance(v, list):
            for r in v:
                if str(r).upper() not in _valid:
                    raise ValueError(f"Invalid regime {r!r}. Valid: {sorted(_valid)}")
        return v


class PyramidingGuardsV1Config(BaseModel):
    """Guard flags that control fail-closed behaviour of the pyramiding gate."""

    model_config = ConfigDict(extra="forbid")

    require_same_side_position: bool = Field(
        ..., description="Block if there is no existing position on the same side",
    )
    require_position_mode_strict_base: bool = Field(
        ..., description="Base position_mode must be STRICT (the policy is the narrow exception)",
    )
    block_if_close_in_progress: bool = Field(
        ..., description="Block new pyramiding adds if a close is in progress",
    )
    block_if_pending_add_exists: bool = Field(
        ..., description="Block if a pending pyramiding LIMIT add already exists for the symbol",
    )
    block_if_sidecar_live_authority_active: bool = Field(
        ..., description="Block if sidecar has live close authority (shadow mode bypasses)",
    )
    require_regime_confidence: bool = Field(
        ..., description="Block if regime_confidence is unavailable (reserved, currently unused)",
    )


class PyramidingTelemetryV1Config(BaseModel):
    """Telemetry settings for pyramiding policy V1."""

    model_config = ConfigDict(extra="forbid")

    emit_trace: bool = Field(..., description="Emit PYRAMIDING_POLICY_EVALUATED trace on every evaluation")


class PyramidingPolicyV1Config(BaseModel):
    """Regime/side-scoped pyramiding policy V1.

    Default disabled. The first enabled slice is aurora + LOW_VOLATILITY + SELL
    in testnet modes only.  All adds are LIMIT-only.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        ..., description="Enable pyramiding policy. False = same-side adds blocked (original STRICT behavior).",
    )
    mode: Literal["testnet_enforced"] = Field(
        ..., description="Policy enforcement mode. testnet_enforced = active only in testnet/hybrid modes.",
    )
    default_action: Literal["block"] = Field(
        ..., description="Action when no rule matches. Must be block (fail-closed).",
    )
    order_type: Literal["LIMIT"] = Field(
        ..., description="Add orders must be LIMIT. MARKET pyramiding is prohibited.",
    )
    max_adds_per_lifecycle: int = Field(
        ..., ge=0, le=5,
        description="Maximum pyramiding adds allowed per position lifecycle (per symbol)",
    )
    max_pending_add_orders_per_symbol: int = Field(
        ..., ge=0, le=5,
        description="Maximum concurrent pending pyramiding LIMIT add orders per symbol",
    )
    rules: List[PyramidingRuleV1Config] = Field(
        ..., description="Ordered list of scoped allow-exception rules",
    )
    guards: PyramidingGuardsV1Config = Field(
        ..., description="Guard flags controlling fail-closed behaviour",
    )
    telemetry: PyramidingTelemetryV1Config = Field(
        ..., description="Telemetry settings",
    )

    @model_validator(mode="after")
    def _validate_rules_not_empty_when_enabled(self) -> "PyramidingPolicyV1Config":
        if self.enabled and not self.rules:
            raise ValueError("pyramiding_policy.enabled=true requires at least one rule in rules[]")
        return self


class QuadraticRolloutConfig(BaseModel):
    """Explicit rollout/rollback controls for Quadratic scoring."""

    model_config = ConfigDict(extra="forbid")

    shadow_enabled: bool = Field(
        ..., description="Evaluate Quadratic in shadow while keeping the live engine unchanged.",
    )
    rollback_armed: bool = Field(
        ..., description="Explicit one-step rollback arm. When true and Quadratic was requested live, runtime falls back to v2 semantics.",
    )
    rollback_reason_chain: List[str] = Field(
        ..., description="Operator-visible rollback reasons that are surfaced in runtime payloads.",
    )


class DecisionGeometryConfig(BaseModel):
    """Aurora admission/sizing geometry contract.

    Purpose:
    - make admission math explicit and config-gated
    - preserve backward-safe baseline quadratic mode
    - allow decoupling admission geometry from sizing geometry without hidden constants
    """

    model_config = ConfigDict(extra='forbid')

    admission_mode: Literal["quadratic", "soft_power", "linear"] = Field(
        ..., description="Transform used for admission score and side resolution.",
    )
    admission_power: Optional[float] = Field(
        ..., description="Exponent for soft_power admission. Required only when admission_mode=soft_power.",
    )
    sizing_mode: Literal["quadratic", "soft_power", "linear"] = Field(
        ..., description="Transform used for sizing_score / quantization semantics.",
    )
    sizing_power: Optional[float] = Field(
        ..., description="Exponent for soft_power sizing. Required only when sizing_mode=soft_power.",
    )
    admission_shield_floor: float = Field(
        ..., ge=0.0,
        le=1.0,
        description=(
            "Admission-only lower bound for shield attenuation. "
            "Does not override explicit hard vetoes when shield multiplier is 0."
        ),
    )

    @model_validator(mode='after')
    def _validate_geometry(self) -> 'DecisionGeometryConfig':
        for mode_field, power_field in (
            ("admission_mode", "admission_power"),
            ("sizing_mode", "sizing_power"),
        ):
            mode = getattr(self, mode_field)
            power = getattr(self, power_field)
            if mode == "soft_power":
                if power is None:
                    raise ValueError(
                        f"{power_field} is required when {mode_field}=soft_power")
                if not (1.0 < float(power) < 2.0):
                    raise ValueError(
                        f"{power_field} must be in (1, 2) for soft_power")
            elif power is not None:
                raise ValueError(
                    f"{power_field} must be omitted unless {mode_field}=soft_power")
        return self


class DecisionConfig(BaseModel):
    """Decision making configuration (testnet/production overrides).

    CFG-TOPLEVEL-EXTRA-ALLOW-BURN-14: Converted to extra='forbid' (all fields explicit).
    """

    model_config = ConfigDict(extra='forbid')

    testnet: Optional[DecisionModeOverrideConfig] = Field(...)
    production: Optional[DecisionModeOverrideConfig] = Field(...)

    signal_threshold: float = Field(
        ..., description='Signal score threshold. PRODUCTION MUST OVERRIDE in trading.yaml!')
    cooldown_sec: Optional[int] = Field(
        ..., description='[DEPRECATED] Global cooldown (use per-instrument qos)')
    side_bias_min_score: Optional[float] = Field(
        ..., description='[DEPRECATED] Min score for side bias')
    side_bias_penalty_factor: Optional[float] = Field(
        ..., description='Side bias penalty factor')
    side_bias_target_ratio: Optional[float] = Field(
        ..., description='Side bias target ratio')
    side_bias_window_sec: Optional[int] = Field(
        ..., description='Side bias window (seconds)')
    side_bias_min_intents: Optional[int] = Field(
        ..., description="Minimum number of intents required in window to activate side-bias penalty"
    )
    side_bias_min_intents: int = Field(
        ..., description='Min intents in window to activate side bias penalty')

    retry_ttl_ms: int = Field(..., description='Retry TTL in ms')
    retry_max_count: int = Field(..., description='Max retry attempts')
    retry_backoff_factor: float = Field(...,
                                        description='Retry backoff multiplier')

    signal_weights: Optional[SignalWeights] = Field(...)
    signals: SignalsConfig = Field(...)
    direction_strength_scoring: Optional[DirectionStrengthScoringConfig] = Field(
        ..., description="DEPRECATED (V2 path): Direction/Strength split scoring configuration."
    )
    kelly: KellyConfig = Field(...)
    qos: QosConfig = Field(...)

    bar_gating: Optional[BarGatingConfig] = Field(...)
    behavior_fsm: Optional[BehaviorFsmConfig] = Field(...)
    roi_exit: Optional[ROIExitConfig] = Field(...)
    mean_reversion: Optional[MeanReversionConfig] = Field(...)

    regime_thresholds: Dict[str, float] = Field(
        ..., description='Regime-specific signal thresholds')
    regime_threshold_multipliers: Dict[str, float] = Field(
        ..., description='Regime threshold multipliers')
    regime_smoothing: Optional[RegimeSmoothingConfig] = Field(
        ..., description='PKG-2: EMA/ramp smoothing for regime threshold multipliers'
    )
    blocked_regimes: Optional[List[str]] = Field(
        ..., description=(
            "Regime kill-switch: if current regime is in this list, suppress Aurora strategy signals "
            "(no entry/exit/hold/flip intents from strategy; safety exits like SL/TP still apply)."
        ),
    )
    symbols_to_track: Optional[List[str]] = Field(
        ..., description='DEPRECATED: Use instruments SSOT')
    neutral_threshold: Optional[float] = Field(
        ..., description='Neutral zone threshold')

    scoring_version: Literal["v1", "v2", "quadratic"] = Field(
        ..., description="Scoring engine version: quadratic (Phase 9). v1/v2 are DEPRECATED.")
    feature_neutrals: Dict[str, float] = Field(
        ..., description="Neutral offsets for V2 scoring")
    essential_features: List[str] = Field(
        ..., description="Features that must be present/ready")
    liquidity_gate: Optional[LiquidityGateConfig] = Field(
        ..., description="Global liquidity gate config")
    anchor_shock_veto: Optional[AnchorShockVetoConfig] = Field(
        ..., description="Phase 3: Block BUY during anchor crash")

    score_multiplier: float = Field(
        ..., description="Multiplier for linear score before quadratic transform")

    decision_geometry: Optional["DecisionGeometryConfig"] = Field(
        ..., description="Explicit admission/sizing geometry contract for Aurora decision math.",
    )

    scoring_engine: Optional["ScoringEngineConfig"] = Field(
        ..., description="Phase 9: Quadratic scoring engine parameters (used when scoring_version='quadratic')",
    )
    quadratic_rollout: Optional["QuadraticRolloutConfig"] = Field(
        ..., description="URS-E1: additive shadow rollout and explicit rollback controls for Quadratic activation.",
    )

    holding_period: Optional[HoldingPeriodConfig] = Field(
        ..., description="RFC: docs/RFC_min_duration_logic.md - Prevents HFT churn")

    reentry_cooldown_sec: Optional[int] = Field(
        ..., description="Global cooldown after position closes before allowing new entry")

    gates: Optional[VolAdjGatesConfig] = Field(
        ..., description="VOL-ADJ-GATES-01: Block entries in dead/extreme markets")

    entry_plan: Optional["EntryPlanConfig"] = Field(
        ..., description="EP-01.2-INT: EntryPlan configuration")

    money_management: Optional["MoneyManagementConfig"] = Field(
        ..., description="Phase 9: Risk-based sizing configuration (risk_per_trade, etc.)"
    )

    execution: Optional["ExecutionGateConfig"] = Field(
        ..., description="Phase 5: 4-stage execution gate configuration (Hard Veto, Direction, Shield, Structural)"
    )
    exit: Optional["ExitManagerConfig"] = Field(
        ..., description="Phase 5: Exit Manager configuration (Signal, Time, DangerZone)"
    )

    operational_mode: OperationalMode = Field(
        ..., description="Phase 6: Operational Mode (PARANOID=Strict, CURIOUS=Relaxed)"
    )
    dashboard: Optional["DashboardConfig"] = Field(
        ..., description="Phase 6: Dashboard metrics configuration"
    )

    pyramiding_policy: Optional[PyramidingPolicyV1Config] = Field(
        None,
        description=(
            "Pyramiding Policy V1: regime/side-scoped same-side add exception. "
            "Default None = disabled (original STRICT behavior preserved). "
            "First enabled slice: aurora + LOW_VOLATILITY + SELL in testnet modes."
        ),
    )

    @model_validator(mode="after")
    def _validate_direction_strength_contract(self) -> "DecisionConfig":
        sv = getattr(self, "scoring_version", "quadratic")
        if sv == "quadratic":
            return self

        ds = getattr(self, "direction_strength_scoring", None)
        if ds is None:
            raise ValueError(
                "direction_strength_scoring is required for scoring_version v1/v2")

        essentials = set(getattr(self, "essential_features", []) or [])
        directional = set(getattr(ds, "directional_features", []) or [])
        missing = sorted(essentials - directional)
        if missing:
            raise ValueError(
                "direction_strength_scoring.directional_features must include all essential_features; "
                f"missing: {missing}"
            )
        return self


class RiskSkewConfig(BaseModel):
    """Risk skew guard configuration (Commit 5)."""

    model_config = ConfigDict(extra='forbid')

    max_skew_sec: int = Field(
        ..., description='Max age difference between features.ts and risk.ts')
    max_defer_count: int = Field(
        ..., description='Max DEFERs per symbol before NO_TRADE_UNTIL_REFRESH')
    defer_cooldown_sec: int = Field(
        ..., description='Cooldown between deferred retries')
    defer_window_sec: int = Field(
        ..., description='Window duration (seconds) - resets defer_count after this period')
    until_refresh_retry_sec: int = Field(
        ..., description='Retry delay when in NO_TRADE_UNTIL_REFRESH state')
    until_refresh_max_hold_sec: int = Field(
        ..., ge=30, le=3600,
        description='Max seconds until_refresh latch can be held. After this, auto-clear and log CRITICAL.'
    )


class RiskGateConfig(BaseModel):
    """Risk gate alert thresholds for blocked intents monitoring."""

    model_config = ConfigDict(extra='forbid')

    threshold_pct_testnet: float = Field(
        ..., description='Alert if >X% intents blocked (testnet)')
    threshold_pct_production: float = Field(
        ..., description='Alert if >X% intents blocked (production)')
    min_intents_for_check: int = Field(
        ..., description='Minimum intents before checking threshold')


class FeaturesTtlConfig(BaseModel):
    """Features TTL configuration."""

    model_config = ConfigDict(extra='forbid')

    ttl_sec: int = Field(...)


class ArmingConfig(BaseModel):
    """Arming/Warmup configuration for DecisionMaking."""

    model_config = ConfigDict(extra='forbid')

    require_regime_warmup: bool = Field(...)
    retry_backoff_ms: int = Field(...)
    max_attempts: int = Field(...)


class DirectionalSanityConfig(BaseModel):
    """Directional sanity gate configuration (DM-DIR-FORENSIC-01).

    Fail-closed semantics live in runtime code: when enabled and trend is
    not confidently confirmed, DM denies opening trades.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description='Enable directional sanity gate (fail-closed)')
    min_abs_delta_price: float = Field(
        ..., ge=0.0,
        description='Minimum absolute delta_price to consider trend (noise threshold)'
    )
    min_confidence: float = Field(
        ..., ge=0.0,
        le=1.0,
        description='Minimum confidence required (max(regime_confidence, trend_confidence))'
    )
    min_regime_confidence: float = Field(
        ..., ge=0.0,
        le=1.0,
        description='Minimum regime_confidence required to open position (0.0 = disabled). '
                    'Separate from min_confidence which blends regime+trend. FIX-CONF-GATE-01.'
    )
    min_regime_confidence_by_regime: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            'Optional per-regime regime_confidence admission thresholds. '
            'When provided, DEFAULT is required and runtime regime-specific keys override it.'
        ),
    )
    max_regime_confidence_by_regime: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            'Optional per-regime regime_confidence upper bounds. '
            'When provided, explicit regime-specific keys apply; DEFAULT may be omitted.'
        ),
    )
    hard_veto_consecutive_bars: int = Field(
        ..., ge=1,
        le=10,
        description='Trailing same-sign filtered delta bars required before directional_sanity emits hard countertrend veto (NRR-027). '
                    'Keeps single-bar trend context for tracing while avoiding hard veto on one-bar countertrend blips.'
    )
    hard_veto_consecutive_bars_by_regime: Optional[Dict[str, int]] = Field(
        default=None,
        description=(
            'Optional per-regime override for hard_veto_consecutive_bars. '
            'When a key matches the current structural regime label, its value overrides the '
            'scalar hard_veto_consecutive_bars. Unknown fields are rejected by Pydantic. '
            'Values must be in [1, 10]. Canonical regime keys: DEFAULT, TREND_UP, TREND_DOWN, '
            'HIGH_VOLATILITY, LOW_VOLATILITY, MEAN_REVERSION, UNCERTAIN.'
        ),
    )
    consecutive_bars: int = Field(
        ..., ge=1,
        le=3,
        description='Number of consecutive deltas required to confirm trend (1-3). Use 1 for bar-based backtest, 2+ for live tick-based.'
    )
    nrr026_enabled: bool = Field(
        default=True,
        description=(
            'Enable NRR-026 (INSUFFICIENT_TREND_CONFIRMATION) gate. '
            'When False, regime-confidence-below-min and trend/confidence checks are bypassed '
            'independently of nrr027_enabled. Requires directional_sanity.enabled=true to have effect.'
        ),
    )
    nrr027_enabled: bool = Field(
        default=True,
        description=(
            'Enable NRR-027 (DIRECTIONAL_SANITY_BLOCKED) countertrend hard-veto gate. '
            'When False, countertrend veto is bypassed independently of nrr026_enabled. '
            'Requires directional_sanity.enabled=true to have effect.'
        ),
    )

    @field_validator('min_regime_confidence_by_regime', mode='before')
    @classmethod
    def validate_min_regime_confidence_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='min_regime_confidence_by_regime',
        )

    @field_validator('max_regime_confidence_by_regime', mode='before')
    @classmethod
    def validate_max_regime_confidence_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='max_regime_confidence_by_regime',
        )

    @field_validator('hard_veto_consecutive_bars_by_regime', mode='before')
    @classmethod
    def validate_hard_veto_consecutive_bars_by_regime_shape(cls, value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError(
                'hard_veto_consecutive_bars_by_regime must be a mapping'
            )
        allowed = ', '.join(sorted(_REGIME_CONFIDENCE_GATE_KEYS))
        for raw_key, raw_val in value.items():
            if not isinstance(raw_key, str):
                raise ValueError(
                    'hard_veto_consecutive_bars_by_regime keys must be strings'
                )
            key = raw_key.strip()
            if key != raw_key or key != key.upper():
                raise ValueError(
                    f'hard_veto_consecutive_bars_by_regime key {raw_key!r} '
                    f'must be canonical uppercase; allowed: {allowed}'
                )
            if key not in _REGIME_CONFIDENCE_GATE_KEYS:
                raise ValueError(
                    f'hard_veto_consecutive_bars_by_regime: unknown key '
                    f'{raw_key!r}; allowed: {allowed}'
                )
            if isinstance(raw_val, bool) or not isinstance(raw_val, int):
                raise ValueError(
                    f'hard_veto_consecutive_bars_by_regime[{raw_key!r}] '
                    f'must be an integer'
                )
            if not (1 <= raw_val <= 10):
                raise ValueError(
                    f'hard_veto_consecutive_bars_by_regime[{raw_key!r}]='
                    f'{raw_val} must be in [1, 10]'
                )
        return value

    @model_validator(mode='after')
    def validate_min_regime_confidence_by_regime_contract(self) -> 'DirectionalSanityConfig':
        min_mapping = self.min_regime_confidence_by_regime
        if min_mapping is None:
            normalized_min = None
        else:
            normalized_min = _normalize_regime_confidence_threshold_mapping(
                min_mapping,
                field_name='min_regime_confidence_by_regime',
            )
        max_mapping = self.max_regime_confidence_by_regime
        if max_mapping is None:
            normalized_max = None
        else:
            normalized_max = _normalize_regime_confidence_threshold_mapping(
                max_mapping,
                field_name='max_regime_confidence_by_regime',
                require_default=False,
            )
        _validate_regime_confidence_band_contract(
            min_value=self.min_regime_confidence,
            max_value=normalized_max.get(
                'DEFAULT') if normalized_max else None,
            field_name='directional_sanity',
        )
        _validate_regime_confidence_band_mapping_contract(
            min_mapping=normalized_min,
            max_mapping=normalized_max,
            field_name='directional_sanity',
        )
        self.min_regime_confidence_by_regime = normalized_min
        self.max_regime_confidence_by_regime = normalized_max
        return self


class PriceMotionSanityConfig(BaseModel):
    """Multi-window price-motion sanity gate configuration (SSOT-required).

    Used to block opening positions against persistent price motion, even if
    microstructure signals (e.g., OBI) are favorable.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable price-motion sanity gate (fail-closed)")
    k_vol: float = Field(
        ..., gt=0.0, description="Normalization factor: pm_norm = ret/(k_vol*vol_pct)")
    flash_window_sec: int = Field(
        ..., ge=1, le=300, description="Flash window length (seconds)")
    bleed_window_sec: int = Field(
        ..., ge=10, le=3600, description="Bleed window length (seconds)")
    flash_threshold_norm: float = Field(
        ..., ge=0.0, description="DENY if pm_norm_flash <= -threshold for LONG")
    bleed_threshold_norm: float = Field(
        ..., ge=0.0, description="DENY if pm_norm_bleed <= -threshold for LONG")
    require_bleed_ready: bool = Field(
        ..., description="If true: missing bleed window data => DENY (fail-closed)")
    pm_norm_clip_abs: float = Field(
        ..., gt=0.0,
        le=50.0,
        description="Absolute clipping bound for pm_norm: clip to [-clip_abs, +clip_abs]. Default 10.0 for Anti-FOMO."
    )
    nrr028_enabled: bool = Field(
        ..., description="Enable NRR-028 (PRICE_MOTION_INSUFFICIENT) gate."
    )
    nrr029_enabled: bool = Field(
        ..., description="Enable NRR-029 (PRICE_MOTION_FLASH_BLOCKED) gate."
    )
    nrr030_enabled: bool = Field(
        ..., description="Enable NRR-030 (PRICE_MOTION_BLEED_BLOCKED) gate."
    )


class FlipOrchestrationConfig(BaseModel):
    """Per-symbol flip-orchestration tuning (close-on-reversal).

    STRICT SSOT: No defaults. Every active symbol MUST have explicit flip config.

    This is a smoothing layer for tick-based signals:
    it prevents immediate flip-closes on marginal opposite signals.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ...,
        description="Enable flip hysteresis for this symbol.",
    )
    hysteresis_mult: float = Field(
        ...,
        ge=1.0,
        description=(
            "Require stronger opposite signal before emitting reduce-only CLOSE during flip. "
            "Example: 1.3 means opposite score must exceed its threshold by 30%."
        ),
    )


class GlobalFlipKillswitchConfig(BaseModel):
    """Global FLIP killswitch for DecisionMaking.

    STRICT SSOT: No defaults. Must be explicitly set in domains.yaml.

    If disabled, ALL flip logic is OFF regardless of per-symbol settings.
    Per-symbol tuning (enabled + hysteresis_mult) is in instruments.yaml.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ...,
        description="Master killswitch for FLIP. If false, all flip disabled globally.",
    )


class MoneyManagementConfig(BaseModel):
    """
    Phase 9: Money Management Configuration.

    Controls risk-based sizing and exposure quantization.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable Phase 9 risk-based sizing")
    risk_per_trade_pct: float = Field(
        ..., gt=0.0, le=1.0,
        description="Risk per trade as fraction of equity (e.g. 0.01 = 1%)"
    )
    stop_distance_pct: float = Field(
        ..., gt=0.0,
        description="Assumed stop distance for sizing calculation (e.g. 0.005 = 0.5%)"
    )
    max_notional_cap: Optional[Decimal] = Field(
        ..., description="Optional hard cap on notional value (USDT)"
    )


class StructuralGateConfig(BaseModel):
    """Configuration for Structural Gate (Risk/Reward checks)."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    min_risk_reward: float = Field(
        ..., ge=0.0,
        description="Minimum Risk/Reward ratio (TP_dist / SL_dist)"
    )
    max_risk_reward: Optional[float] = Field(
        ..., gt=0.0,
        description="Optional cap on R/R (to filter unrealistic TPs)"
    )


class ExecutionGateConfig(BaseModel):
    """
    Phase 5: Execution Gate Configuration.
    Controls the 4-stage filter pipeline.
    """

    model_config = ConfigDict(extra='forbid')

    gates_enabled: List[ExecutionGateName] = Field(
        ..., description="Active execution gates (order invariant, but typically checked in stage order)"
    )
    structural_gate: StructuralGateConfig = Field(
        ...)


class ExitManagerConfig(BaseModel):
    """
    Phase 5: Exit Manager Configuration.
    Controls signal reversal, time stops, and danger zone actions.
    """

    model_config = ConfigDict(extra='forbid')

    time_exit_enabled: bool = Field(...)
    max_hold_time_sec: int = Field(
        ..., ge=60,
        description="Maximum holding time in seconds before forced exit (Time Stop)"
    )

    signal_exit_enabled: bool = Field(...)
    signal_reversal_threshold: float = Field(
        ..., description="Score threshold to trigger exit if position is opposing (e.g. -0.1 for LONG)"
    )

    danger_zone_action: DangerZoneExitType = Field(
        ..., description="Action when DangerZone triggers while in position (Default: TIGHTEN_STOPS)"
    )
    danger_zone_tighten_factor: float = Field(
        ..., gt=0.0, le=1.0,
        description="Factor to tighten stops by if DangerZone triggers (e.g. 0.5 = reduce SL distance by 50%)"
    )


class EntryPlanConfig(BaseModel):
    """
    EntryPlan configuration for ATR-based entry/SL/TP computation.

    Validation stays strict on unknown fields, but additive defaults mirror the
    runtime EntryPlanParams contract for optional structural-stop controls.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Enable EntryPlan-based SL/TP injection into trade intents"
    )
    atr_period: int = Field(
        ..., ge=1, le=100,
        description="Expected ATR period (for validation/tracing, must match FE config)"
    )
    entry_k_atr: float = Field(
        ..., gt=0.0, le=5.0,
        description="Entry offset as ATR multiplier (e.g., 0.5 = 0.5*ATR from ref price)"
    )
    sl_k_atr: float = Field(
        ..., gt=0.0, le=10.0,
        description="Stop-loss distance as ATR multiplier (e.g., 1.5 = 1.5*ATR)"
    )
    tp_k_atr: float = Field(
        ..., gt=0.0, le=10.0,
        description="Take-profit distance as ATR multiplier (e.g., 2.0 = 2.0*ATR)"
    )
    obi_weight: float = Field(
        ..., ge=0.0, le=2.0,
        description="OBI modulation weight (0 = no modulation, 1 = full modulation)"
    )
    obi_mod_clamp_min: float = Field(
        ..., gt=0.0, le=1.0,
        description="Minimum clamp for OBI multiplier (anti-taker drift safety)"
    )
    obi_mod_clamp_max: float = Field(
        ..., ge=1.0, le=3.0,
        description="Maximum clamp for OBI multiplier (anti-taker drift safety)"
    )
    require_atr: bool = Field(
        ..., description="If True, reject trade intent if ATR is not ready (fail-closed)"
    )
    obi_missing_policy: Literal["neutral"] = Field(
        ..., description="Policy when OBI is None: 'neutral' applies multiplier=1.0 (EXPLICIT, not silent)"
    )
    structural_stop_enabled: bool = Field(
        False, description="Enable dynamic structural stops based on pillar conviction"
    )
    base_atr_mult: float = Field(
        1.5, gt=0.0,
        description="Base ATR multiplier for stop loss (at zero conviction)"
    )
    confidence_scale: float = Field(
        0.5, gt=0.0,
        description="Scaling factor for conviction: mult = base - scale * confidence"
    )
    min_stop_bps: int = Field(
        15, ge=1,
        description="Minimum stop distance in basis points (safety floor)"
    )

    @model_validator(mode='after')
    def validate_clamp_order(self) -> 'EntryPlanConfig':
        if self.obi_mod_clamp_min > 1.0:
            raise ValueError(
                f"obi_mod_clamp_min ({self.obi_mod_clamp_min}) must be <= 1.0")
        if self.obi_mod_clamp_max < 1.0:
            raise ValueError(
                f"obi_mod_clamp_max ({self.obi_mod_clamp_max}) must be >= 1.0")
        if self.obi_mod_clamp_min > self.obi_mod_clamp_max:
            raise ValueError(
                f"obi_mod_clamp_min ({self.obi_mod_clamp_min}) must be <= obi_mod_clamp_max ({self.obi_mod_clamp_max})"
            )
        return self


class DegradedContextStrategyContractConfig(BaseModel):
    """Explicit per-strategy degraded-context contract."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="When true, degraded-context checks apply to this strategy only.",
    )
    critical_keys: List[str] = Field(
        ..., description="Exact DecisionContext keys owned by this strategy contract. Empty means explicit no-op.",
    )


class RegimeLossEmbargoConfig(BaseModel):
    """Decision-making-owned regime loss embargo controls."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(
        ..., description="Hard kill switch for regime loss embargo. False = fully inert.",
    )
    min_loss_threshold_net: float = Field(
        ..., ge=0.0,
        description="Net-PnL epsilon in quote currency. Loss latch requires realized_pnl_net < -threshold.",
    )
    fee_only_close_policy: Literal["ignore", "latch"] = Field(
        ...,
        description=(
            "How provable fee-only terminal closes are handled. "
            "ignore = do not latch when realized_pnl == 0 and net loss is fees-only; "
            "latch = preserve net-only latch semantics."
        ),
    )


class LowVolCostFloorFeeConfig(BaseModel):
    """Explicit fee assumptions for LOW_VOL cost-floor evaluation."""

    model_config = ConfigDict(extra='forbid')

    open_fee_bps: float = Field(..., gt=0.0)
    close_fee_bps: float = Field(..., gt=0.0)
    fee_source: Literal["explicit_config"] = Field(...)


class LowVolCostFloorSlippageConfig(BaseModel):
    """Explicit slippage assumptions for LOW_VOL cost-floor evaluation."""

    model_config = ConfigDict(extra='forbid')

    buffer_bps: float = Field(..., ge=0.0)
    source: Literal["explicit_config"] = Field(...)


class LowVolCostFloorThresholdsConfig(BaseModel):
    """Threshold contract for LOW_VOL fee-adjusted profitability gating."""

    model_config = ConfigDict(extra='forbid')

    target_net_fee_multiple: float = Field(..., gt=0.0)
    min_tp_fee_coverage: float = Field(..., gt=0.0)
    min_rr: float = Field(..., gt=0.0)
    min_regime_confidence_by_regime: Dict[str, float] = Field(...)
    # Migration alias: kept for backward compat. Gate uses min_raw_score_by_regime /
    # min_normalized_confidence_by_regime instead. If those are absent, this is copied into both.
    min_direction_confidence_by_regime: Dict[str, float] = Field(...)
    min_regime_confidence_overrides_by_strategy_symbol: Optional[
        Dict[str, Dict[str, Dict[str, float]]]
    ] = Field(default=None)
    min_direction_confidence_overrides_by_strategy_symbol: Optional[
        Dict[str, Dict[str, Dict[str, float]]]
    ] = Field(default=None)
    # Scale-split threshold families (preferred over migration alias above).
    min_raw_score_by_regime: Optional[Dict[str, float]] = Field(
        default=None,
        description="Threshold for raw_signed_score sources (signal_score, final_score). Compared to abs(value).",
    )
    min_normalized_confidence_by_regime: Optional[Dict[str, float]] = Field(
        default=None,
        description="Threshold for normalized_confidence sources (strategy_confidence, judge_confidence).",
    )
    min_raw_score_overrides_by_strategy_symbol: Optional[
        Dict[str, Dict[str, Dict[str, float]]]
    ] = Field(default=None)
    min_normalized_confidence_overrides_by_strategy_symbol: Optional[
        Dict[str, Dict[str, Dict[str, float]]]
    ] = Field(default=None)

    @field_validator('min_regime_confidence_by_regime', mode='before')
    @classmethod
    def validate_min_regime_confidence_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_regime_confidence_by_regime',
        )

    @field_validator('min_direction_confidence_by_regime', mode='before')
    @classmethod
    def validate_min_direction_confidence_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_direction_confidence_by_regime',
        )

    @field_validator('min_raw_score_by_regime', mode='before')
    @classmethod
    def validate_min_raw_score_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_raw_score_by_regime',
        )

    @field_validator('min_normalized_confidence_by_regime', mode='before')
    @classmethod
    def validate_min_normalized_confidence_by_regime_shape(cls, value):
        return _validate_regime_confidence_threshold_mapping_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_normalized_confidence_by_regime',
        )

    @field_validator('min_regime_confidence_overrides_by_strategy_symbol', mode='before')
    @classmethod
    def validate_min_regime_confidence_overrides_by_strategy_symbol_shape(cls, value):
        return _validate_low_vol_strategy_symbol_threshold_overrides_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_regime_confidence_overrides_by_strategy_symbol',
        )

    @field_validator('min_direction_confidence_overrides_by_strategy_symbol', mode='before')
    @classmethod
    def validate_min_direction_confidence_overrides_by_strategy_symbol_shape(cls, value):
        return _validate_low_vol_strategy_symbol_threshold_overrides_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_direction_confidence_overrides_by_strategy_symbol',
        )

    @field_validator('min_raw_score_overrides_by_strategy_symbol', mode='before')
    @classmethod
    def validate_min_raw_score_overrides_by_strategy_symbol_shape(cls, value):
        return _validate_low_vol_strategy_symbol_threshold_overrides_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_raw_score_overrides_by_strategy_symbol',
        )

    @field_validator('min_normalized_confidence_overrides_by_strategy_symbol', mode='before')
    @classmethod
    def validate_min_normalized_confidence_overrides_by_strategy_symbol_shape(cls, value):
        return _validate_low_vol_strategy_symbol_threshold_overrides_shape(
            value,
            field_name='low_vol_cost_floor_gate.thresholds.min_normalized_confidence_overrides_by_strategy_symbol',
        )

    @model_validator(mode='after')
    def validate_threshold_maps(self) -> 'LowVolCostFloorThresholdsConfig':
        self.min_regime_confidence_by_regime = _normalize_low_vol_gate_threshold_mapping(
            self.min_regime_confidence_by_regime,
            field_name='low_vol_cost_floor_gate.thresholds.min_regime_confidence_by_regime',
        )
        self.min_direction_confidence_by_regime = _normalize_low_vol_gate_threshold_mapping(
            self.min_direction_confidence_by_regime,
            field_name='low_vol_cost_floor_gate.thresholds.min_direction_confidence_by_regime',
        )
        self.min_regime_confidence_overrides_by_strategy_symbol = _normalize_low_vol_strategy_symbol_threshold_overrides(
            self.min_regime_confidence_overrides_by_strategy_symbol,
            field_name='low_vol_cost_floor_gate.thresholds.min_regime_confidence_overrides_by_strategy_symbol',
        )
        self.min_direction_confidence_overrides_by_strategy_symbol = _normalize_low_vol_strategy_symbol_threshold_overrides(
            self.min_direction_confidence_overrides_by_strategy_symbol,
            field_name='low_vol_cost_floor_gate.thresholds.min_direction_confidence_overrides_by_strategy_symbol',
        )
        # Normalize new split families if explicitly provided.
        if self.min_raw_score_by_regime is not None:
            self.min_raw_score_by_regime = _normalize_low_vol_gate_threshold_mapping(
                self.min_raw_score_by_regime,
                field_name='low_vol_cost_floor_gate.thresholds.min_raw_score_by_regime',
            )
        else:
            # Migration alias: copy from legacy field so gate always has a value.
            self.min_raw_score_by_regime = dict(
                self.min_direction_confidence_by_regime)
        if self.min_normalized_confidence_by_regime is not None:
            self.min_normalized_confidence_by_regime = _normalize_low_vol_gate_threshold_mapping(
                self.min_normalized_confidence_by_regime,
                field_name='low_vol_cost_floor_gate.thresholds.min_normalized_confidence_by_regime',
            )
        else:
            self.min_normalized_confidence_by_regime = dict(
                self.min_direction_confidence_by_regime)
        if self.min_raw_score_overrides_by_strategy_symbol is not None:
            self.min_raw_score_overrides_by_strategy_symbol = _normalize_low_vol_strategy_symbol_threshold_overrides(
                self.min_raw_score_overrides_by_strategy_symbol,
                field_name='low_vol_cost_floor_gate.thresholds.min_raw_score_overrides_by_strategy_symbol',
            )
        if self.min_normalized_confidence_overrides_by_strategy_symbol is not None:
            self.min_normalized_confidence_overrides_by_strategy_symbol = _normalize_low_vol_strategy_symbol_threshold_overrides(
                self.min_normalized_confidence_overrides_by_strategy_symbol,
                field_name='low_vol_cost_floor_gate.thresholds.min_normalized_confidence_overrides_by_strategy_symbol',
            )
        return self


class LowVolDirectionConfidenceConfig(BaseModel):
    """Direction-confidence sourcing contract for LOW_VOL gating.

    Source families are separated by scale so each is compared against its own threshold family:
    - raw_signed_score_sources: signal_score, final_score (range [-1,1], magnitude used)
    - normalized_confidence_sources: strategy_confidence, judge_confidence (range [0,1])
    """

    model_config = ConfigDict(extra='forbid')

    required: bool = Field(...)
    raw_signed_score_sources: List[Literal['signal_score', 'final_score']] = Field(
        default_factory=list,
        description="Sources with range [-1,1]; gate compares abs(value) to min_raw_score threshold",
    )
    normalized_confidence_sources: List[Literal['strategy_confidence', 'judge_confidence']] = Field(
        default_factory=list,
        description="Sources with range [0,1]; gate compares value to min_normalized_confidence threshold",
    )
    judge_confidence_live_producer_required: bool = Field(
        default=False,
        description=(
            "When True, judge_confidence is only accepted if trace contains "
            "judge_confidence_live_producer_proof=True"
        ),
    )
    missing_policy: Literal['fail_closed',
                            'warn_and_allow', 'disabled'] = Field(...)

    @field_validator('raw_signed_score_sources', mode='before')
    @classmethod
    def validate_raw_signed_score_sources(cls, value):
        return _validate_low_vol_source_family(
            value,
            field_name='low_vol_cost_floor_gate.direction_confidence.raw_signed_score_sources',
            allowed=_LOW_VOL_RAW_SIGNED_SCORE_SOURCES,
        )

    @field_validator('normalized_confidence_sources', mode='before')
    @classmethod
    def validate_normalized_confidence_sources(cls, value):
        return _validate_low_vol_source_family(
            value,
            field_name='low_vol_cost_floor_gate.direction_confidence.normalized_confidence_sources',
            allowed=_LOW_VOL_NORMALIZED_CONFIDENCE_SOURCES,
        )

    @model_validator(mode='after')
    def validate_at_least_one_source_family(self) -> 'LowVolDirectionConfidenceConfig':
        if not self.raw_signed_score_sources and not self.normalized_confidence_sources:
            raise ValueError(
                'low_vol_cost_floor_gate.direction_confidence: at least one source family '
                '(raw_signed_score_sources or normalized_confidence_sources) must be non-empty'
            )
        return self

    @property
    def allowed_sources(self) -> List[str]:
        """Combined ordered list for gate backward compatibility."""
        return list(self.raw_signed_score_sources) + list(self.normalized_confidence_sources)


class LowVolGeometryConfig(BaseModel):
    """TP/SL geometry contract for LOW_VOL gating."""

    model_config = ConfigDict(extra='forbid')

    require_tpsl: bool = Field(...)
    missing_policy: Literal['fail_closed',
                            'warn_and_allow', 'disabled'] = Field(...)


class LowVolCostFloorGateConfig(BaseModel):
    """Decision-making owned LOW_VOLATILITY cost-floor gate contract."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    decision_chain_enabled: bool = Field(
        default=True,
        description=(
            "If false, evaluate and persist LOW_VOL cost-floor telemetry but do "
            "not emit NRR-062 as an active decision-chain block."
        ),
    )
    enforce_in_modes: List[Literal['testnet',
                                   'hybrid_live_data_testnet_exec', 'live', 'production']] = Field(...)
    observe_only_in_modes: List[Literal['testnet',
                                        'hybrid_live_data_testnet_exec', 'live', 'production']] = Field(...)
    regimes: List[str] = Field(...)
    fee: LowVolCostFloorFeeConfig = Field(...)
    slippage: LowVolCostFloorSlippageConfig = Field(...)
    thresholds: LowVolCostFloorThresholdsConfig = Field(...)
    direction_confidence: LowVolDirectionConfidenceConfig = Field(...)
    geometry: LowVolGeometryConfig = Field(...)

    @field_validator('enforce_in_modes', mode='before')
    @classmethod
    def validate_enforce_in_modes(cls, value):
        return _validate_low_vol_runtime_modes(
            value,
            field_name='low_vol_cost_floor_gate.enforce_in_modes',
        )

    @field_validator('observe_only_in_modes', mode='before')
    @classmethod
    def validate_observe_only_in_modes(cls, value):
        return _validate_low_vol_runtime_modes(
            value,
            field_name='low_vol_cost_floor_gate.observe_only_in_modes',
        )

    @field_validator('regimes', mode='before')
    @classmethod
    def validate_regimes(cls, value):
        if not isinstance(value, list) or not value:
            raise ValueError(
                'low_vol_cost_floor_gate.regimes must be a non-empty list')
        normalized: List[str] = []
        seen: set[str] = set()
        for raw_regime in value:
            if not isinstance(raw_regime, str):
                raise ValueError(
                    'low_vol_cost_floor_gate.regimes entries must be strings')
            regime = raw_regime.strip()
            if raw_regime != regime or regime != regime.upper():
                raise ValueError(
                    'low_vol_cost_floor_gate.regimes entries must be canonical uppercase labels')
            if regime not in _REGIME_CONFIDENCE_GATE_KEYS:
                allowed = ', '.join(sorted(_REGIME_CONFIDENCE_GATE_KEYS))
                raise ValueError(
                    f"unsupported low_vol_cost_floor_gate.regimes value '{raw_regime}'; allowed: {allowed}"
                )
            if regime in seen:
                raise ValueError(
                    'low_vol_cost_floor_gate.regimes entries must be unique')
            seen.add(regime)
            normalized.append(regime)
        if 'LOW_VOLATILITY' not in normalized:
            raise ValueError(
                'low_vol_cost_floor_gate.regimes must include LOW_VOLATILITY')
        return normalized

    @model_validator(mode='after')
    def validate_mode_sets(self) -> 'LowVolCostFloorGateConfig':
        overlap = set(self.enforce_in_modes) & set(self.observe_only_in_modes)
        if overlap:
            raise ValueError(
                'low_vol_cost_floor_gate enforce/observe mode sets must not overlap: '
                + ', '.join(sorted(overlap))
            )
        return self


MANDATORY_JUDGE_BRIDGE_HARD_GATES = frozenset({
    "panic_killswitch",
    "exchange_filter_fail",
    "exposure_limit",
    "stale_features",
    "stale_regime",
    "order_guardian_block",
})


JudgeBridgeAuthorityMode = Literal[
    "shadow",
    "advisory",
    "hybrid_gated",
    "live_gated",
]
JudgeBridgeBandAction = Literal["allow", "suppress"]
JudgeBridgeUnknownPolicy = Literal["fail_closed", "record_only"]


class JudgeBridgeConfidenceBandConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    min: float = Field(..., ge=0.0, le=1.0)
    max: float = Field(..., ge=0.0, le=1.0)
    action: JudgeBridgeBandAction

    @model_validator(mode='after')
    def validate_bounds(self) -> 'JudgeBridgeConfidenceBandConfig':
        if self.min >= self.max:
            raise ValueError('judge_bridge confidence band min must be < max')
        return self


class JudgeBridgeConfidencePolicyConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    unknown_policy: JudgeBridgeUnknownPolicy = Field(...)
    allow_overlapping_bands: bool = Field(...)
    open_bands: List[JudgeBridgeConfidenceBandConfig] = Field(...)
    suppress_bands: List[JudgeBridgeConfidenceBandConfig] = Field(...)

    @staticmethod
    def _overlaps(
        left: JudgeBridgeConfidenceBandConfig,
        right: JudgeBridgeConfidenceBandConfig,
    ) -> bool:
        return max(left.min, right.min) < min(left.max, right.max)

    @model_validator(mode='after')
    def validate_bands(self) -> 'JudgeBridgeConfidencePolicyConfig':
        all_bands = list(self.open_bands) + list(self.suppress_bands)
        for band in self.open_bands:
            if band.action != "allow":
                raise ValueError('judge_bridge open_bands action must be allow')
        for band in self.suppress_bands:
            if band.action != "suppress":
                raise ValueError('judge_bridge suppress_bands action must be suppress')

        if not self.allow_overlapping_bands:
            for idx, left in enumerate(all_bands):
                for right in all_bands[idx + 1:]:
                    if self._overlaps(left, right):
                        raise ValueError(
                            'judge_bridge confidence bands must not overlap'
                        )
        for open_band in self.open_bands:
            for suppress_band in self.suppress_bands:
                if self._overlaps(open_band, suppress_band):
                    raise ValueError(
                        'judge_bridge open and suppress bands must not conflict'
                    )
        return self


class JudgeBridgeHardGatesConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    judge_cannot_override: List[str] = Field(..., min_length=1)

    @model_validator(mode='after')
    def validate_mandatory_gates(self) -> 'JudgeBridgeHardGatesConfig':
        configured = set(self.judge_cannot_override)
        missing = MANDATORY_JUDGE_BRIDGE_HARD_GATES - configured
        if missing:
            raise ValueError(
                'judge_bridge hard_gates missing mandatory gates: '
                + ', '.join(sorted(missing))
            )
        return self


class JudgeBridgeCalibrationGuardConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    required_for_hybrid_gated: bool = Field(...)
    required_for_live_gated: bool = Field(...)
    accepted_artifact_path: Optional[str] = Field(...)
    auto_apply: bool = Field(...)

    @model_validator(mode='after')
    def validate_no_auto_apply(self) -> 'JudgeBridgeCalibrationGuardConfig':
        if self.auto_apply:
            raise ValueError('judge_bridge calibration_guard.auto_apply must be false')
        return self


class JudgeBridgeRuntimeAgreementStateScoresConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    agree: float = Field(..., ge=0.0, le=1.0)
    single_expert: float = Field(..., ge=0.0, le=1.0)
    unknown: float = Field(..., ge=0.0, le=1.0)
    disagree: float = Field(..., ge=0.0, le=1.0)
    no_experts: float = Field(..., ge=0.0, le=1.0)


class JudgeBridgeRuntimeVerdictThresholdsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    open_long_min_confidence: float = Field(..., ge=0.0, le=1.0)
    open_short_min_confidence: float = Field(..., ge=0.0, le=1.0)
    suppress_max_confidence: float = Field(..., ge=0.0, le=1.0)
    unknown_max_evidence_score: float = Field(..., ge=0.0, le=1.0)


class JudgeBridgeRuntimeStalePolicyConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    stale_regime_penalty: float = Field(..., ge=0.0)
    stale_market_penalty: float = Field(..., ge=0.0)
    missing_execution_readiness_penalty: float = Field(..., ge=0.0)
    missing_risk_context_penalty: float = Field(..., ge=0.0)
    missing_portfolio_context_penalty: float = Field(..., ge=0.0)


class JudgeBridgeRuntimeHardUnknownConditionsConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    no_strategy_experts: bool = Field(...)
    missing_regime_context: bool = Field(...)
    missing_market_context: bool = Field(...)


class JudgeBridgeRuntimeMetaScoringConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: Literal["1.0.0"] = "1.0.0"
    agreement_weight: float = Field(..., ge=0.0)
    confidence_weight: float = Field(..., ge=0.0)
    regime_weight: float = Field(..., ge=0.0)
    historical_surface_weight: float = Field(..., ge=0.0)
    missingness_penalty_weight: float = Field(..., ge=0.0)
    freshness_penalty_weight: float = Field(..., ge=0.0)
    disagreement_penalty_weight: float = Field(..., ge=0.0)
    no_expert_penalty: float = Field(..., ge=0.0)
    unknown_cap: float = Field(..., ge=0.0, le=1.0)
    min_confidence: float = Field(..., ge=0.0, le=1.0)
    max_confidence: float = Field(..., ge=0.0, le=1.0)
    verdict_thresholds: JudgeBridgeRuntimeVerdictThresholdsConfig
    stale_policy: JudgeBridgeRuntimeStalePolicyConfig
    hard_unknown_conditions: JudgeBridgeRuntimeHardUnknownConditionsConfig
    agreement_state_scores: JudgeBridgeRuntimeAgreementStateScoresConfig

    @model_validator(mode='after')
    def validate_runtime_meta_config(self) -> 'JudgeBridgeRuntimeMetaScoringConfig':
        if self.min_confidence > self.max_confidence:
            raise ValueError('judge_bridge shadow_capture min_confidence must be <= max_confidence')
        if not any(
            weight > 0
            for weight in (
                self.agreement_weight,
                self.confidence_weight,
                self.regime_weight,
                self.historical_surface_weight,
            )
        ):
            raise ValueError('judge_bridge shadow_capture requires at least one positive scoring weight')
        return self


class JudgeBridgeShadowCaptureConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    output_dir: str = Field(..., min_length=1)
    evidence_envelope_file: str = Field(..., min_length=1)
    policy_verdict_file: str = Field(..., min_length=1)
    bridge_decision_file: str = Field(..., min_length=1)
    calibration_row_file: str = Field(..., min_length=1)
    meta_scoring: JudgeBridgeRuntimeMetaScoringConfig

    @field_validator(
        'evidence_envelope_file',
        'policy_verdict_file',
        'bridge_decision_file',
        'calibration_row_file',
    )
    @classmethod
    def validate_jsonl_filename(cls, value: str) -> str:
        if not value.endswith('.jsonl'):
            raise ValueError('judge_bridge shadow_capture files must be jsonl')
        return value


class JudgeBridgeConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    authority_mode: JudgeBridgeAuthorityMode = Field(...)
    allowed_runtime_modes: List[str] = Field(..., min_length=1)
    forbidden_runtime_modes: List[str] = Field(..., min_length=1)
    confidence_policy: JudgeBridgeConfidencePolicyConfig = Field(...)
    hard_gates: JudgeBridgeHardGatesConfig = Field(...)
    calibration_guard: JudgeBridgeCalibrationGuardConfig = Field(...)
    shadow_capture: JudgeBridgeShadowCaptureConfig = Field(...)

    @model_validator(mode='after')
    def validate_runtime_policy(self) -> 'JudgeBridgeConfig':
        allowed = set(self.allowed_runtime_modes)
        forbidden = set(self.forbidden_runtime_modes)
        if allowed & forbidden:
            raise ValueError('judge_bridge allowed and forbidden runtime modes overlap')
        if "production" not in forbidden or "live" not in forbidden:
            raise ValueError('judge_bridge must forbid production and live runtime modes')
        if self.authority_mode == "live_gated" and not self.calibration_guard.accepted_artifact_path:
            raise ValueError(
                'judge_bridge live_gated requires accepted_artifact_path'
            )
        return self


class TradeFlowGateConfig(BaseModel):
    """Configuration for T6C3 strategy-aware trade-flow degraded entry gate."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(...)
    sensitive_strategies: List[str] = Field(...)
    block_states: List[str] = Field(...)
    missing_state_behavior: Literal["observe_only", "fail_closed"] = Field(...)
    unknown_state_behavior: Literal["observe_only", "fail_closed"] = Field(...)
    apply_to: List[str] = Field(...)
    preserve: List[str] = Field(...)


class DecisionMakingDomainConfig(BaseModel):
    """Complete decision making domain configuration."""

    model_config = ConfigDict(extra='forbid')

    trade_flow_gate: TradeFlowGateConfig = Field(
        ...,
        description="T6C3 strategy-aware trade-flow degraded entry gate configuration.",
    )
    position_sizing: PositionSizingConfig = Field(...)
    entry_plan: EntryPlanConfig = Field(
        ..., description="EP-01.2: EntryPlan config for ATR-based entry/SL/TP computation"
    )
    qos: QosConfig = Field(...)
    features: FeaturesTtlConfig = Field(...)
    bar_gating: BarGatingConfig = Field(...)
    behavior_fsm: BehaviorFsmConfig = Field(...)
    risk_skew: RiskSkewConfig = Field(...)
    risk_gate: RiskGateConfig = Field(...)
    arming: ArmingConfig = Field(...)
    directional_sanity: DirectionalSanityConfig = Field(...)
    low_vol_cost_floor_gate: LowVolCostFloorGateConfig = Field(
        ...,
        description='LVC-2: LOW_VOLATILITY fee-adjusted entry gate with explicit mode scoping.',
    )
    price_motion_sanity: PriceMotionSanityConfig = Field(...)
    flip: GlobalFlipKillswitchConfig = Field(
        ...,
        description="Global FLIP killswitch. Per-symbol config in instruments.yaml."
    )
    regime_loss_embargo: RegimeLossEmbargoConfig = Field(
        ...,
        description="Decision-making-owned stable regime epoch loss embargo.",
    )
    judge_bridge: JudgeBridgeConfig = Field(
        ...,
        description="Disabled-by-default Judge bridge mode policy. Phase 7 contract only.",
    )
    neocortex_enforcement_mode: Literal["shadow", "enforce"] = Field(
        ...,
        description="Neocortex authority mode: shadow records model decisions while returning ALLOW; enforce returns model BLOCK/ALLOW.",
    )
    fail_closed_on_degraded_context: bool = Field(
        ..., description=(
            "If true, DecisionMaking may DEFER intents when critical DecisionContext "
            "features are missing/invalid (fail-closed)."
        ),
    )
    degraded_context_critical_keys: List[str] = Field(
        ..., description=(
            "Optional global list of critical DecisionContext keys. If empty, DecisionMaking uses a safe built-in default set."
        ),
    )
    degraded_context_critical_keys_by_strategy: Dict[str, List[str]] = Field(
        ..., description=(
            "Deprecated legacy per-strategy override map. Runtime strategy-scoped degraded-context "
            "resolution now uses degraded_context_contracts_by_strategy."
        ),
    )
    degraded_context_contracts_by_strategy: Dict[str, DegradedContextStrategyContractConfig] = Field(
        ..., description=(
            "Canonical strategy-scoped degraded-context contracts. Runtime no longer falls back "
            "to a hidden global default bundle when this redesign surface is in use."
        ),
    )
    portfolio_warmup_timeout_sec: int = Field(
        ..., ge=5, le=120,
        description='Max seconds to wait for initial EVT:PORTFOLIO_STATE_UPDATED at startup before emitting empty fallback.'
    )


class ReadinessRegistryConfig(BaseModel):
    """P0-0: Readiness contract registry - SSOT for declared ready keys."""

    model_config = ConfigDict(extra='forbid')

    declared_keys: List[str] = Field(
        ..., min_length=1,
        description='All keys that FE can emit in warmup.ready. essential_features MUST be subset.'
    )


class WarmupEnforcementConfig(BaseModel):
    """P0-0: Warmup enforcement configuration. MANDATORY in production.

    TASK-ZOMBIE-FIX: Removed validate_essential_subset (dead, never read in runtime).
    """

    model_config = ConfigDict(extra='forbid')

    enforcement_mode: Literal["fail_fast", "warn_only", "disabled"] = Field(
        ..., description='LOCKED to fail_fast in production. warn_only/disabled forbidden.'
    )
    check_full_ready_invariant: bool = Field(
        ..., description='Invariant: full_ready=True => all declared_keys present'
    )
    degraded_allowed_strategies: List[str] = Field(
        ..., description='Strategy IDs allowed to receive CMD:PROCESS_STRATEGY even if full_ready=False. Handlers must perform their own specific checks.'
    )

    @model_validator(mode="after")
    def _warn_if_not_fail_fast(self) -> "WarmupEnforcementConfig":
        if self.enforcement_mode != "fail_fast":
            import warnings

            warnings.warn(
                f"warmup.enforcement_mode={self.enforcement_mode} is NOT recommended for production. "
                "Use 'fail_fast' to ensure system does not trade until all features ready.",
                UserWarning
            )
        return self


class ContextShieldConfig(BaseModel):
    """Regime-aware attenuation shield config.

    REGIME-FIX-01: regime_multipliers keys MUST match RegimeDetector output
    (UPPERCASE: TREND_UP, TREND_DOWN, HIGH_VOLATILITY, LOW_VOLATILITY,
    MEAN_REVERSION, UNCERTAIN).

    TTL-STALE-01: If regime data is older than ttl_ms, apply stale penalty
    to prevent trading on stale regime information.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable ContextShield')
    regime_multipliers: Dict[str, float] = Field(
        ..., description='Regime -> multiplier mapping (keys MUST match RegimeDetector output)',
    )
    default_multiplier: float = Field(
        ..., ge=0.0, le=1.0,
        description='Multiplier for unknown regimes',
    )
    no_regime_multiplier: float = Field(
        ..., ge=0.0, le=1.0,
        description='Multiplier when no regime detected',
    )
    ttl_ms: int = Field(
        ..., gt=0,
        description='Regime staleness TTL in milliseconds (default: 4h = 14,400,000ms)',
    )
    stale_mult_normal: float = Field(
        ..., ge=0.0, le=1.0,
        description='Multiplier for stale non-danger regimes',
    )
    stale_mult_danger: float = Field(
        ..., ge=0.0, le=1.0,
        description='Multiplier for stale danger regimes (more aggressive reduction)',
    )
    danger_regimes: List[str] = Field(
        ..., description='Regime names considered dangerous for stale penalty',
    )


class MemoryShieldConfig(BaseModel):
    """
    Phase 3 / Doctrine v2.6 (P0-3.1): Memory Shield Configuration.
    Tracks state visits and applies multipliers based on familiarity.

    Note: ``is_backtest`` is NOT a config knob - it is a runtime truth.
    Callers must set ``storage_path: null`` in backtest configs to guarantee
    no cross-run leakage and no filesystem I/O.
    """

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable MemoryShield')
    decay_rate: float = Field(
        ..., gt=0.0, lt=1.0,
        description='Exponential decay rate for state visits (weight = visits * decay^days)'
    )
    max_states: int = Field(
        ..., ge=1,
        description='LRU capacity for state memory'
    )
    unknown_threshold: int = Field(..., ge=1)
    exploring_threshold: int = Field(..., ge=1)
    unknown_multiplier: float = Field(..., ge=0.0, le=1.0)
    exploring_multiplier: float = Field(..., ge=0.0, le=1.0)
    known_multiplier: float = Field(..., ge=0.0, le=1.0)
    storage_path: Optional[str] = Field(
        ..., description='JSON file path for LIVE persistence. None -> RAM-only (safe for backtest).',
    )
    flush_interval_sec: float = Field(
        ..., ge=1.0,
        description='Minimum seconds between disk flushes (LIVE only).',
    )

    @model_validator(mode='after')
    def _validate_thresholds(self) -> 'MemoryShieldConfig':
        if self.unknown_threshold >= self.exploring_threshold:
            raise ValueError(
                f"unknown_threshold ({self.unknown_threshold}) must be < "
                f"exploring_threshold ({self.exploring_threshold})"
            )
        return self


class DangerZoneShieldConfig(BaseModel):
    """Volatility circuit breaker shield config."""

    model_config = ConfigDict(extra='forbid')

    enabled: bool = Field(..., description='Enable DangerZoneShield')
    vol_threshold: float = Field(
        ..., gt=0.0, le=1.0,
        description='volatility_state above this -> VETO',
    )
    spread_threshold: float = Field(
        ..., gt=0.0,
        description='spread_bps above this -> VETO',
    )
    motion_threshold: float = Field(
        ..., gt=0.0,
        description='|price_motion_norm| above this -> VETO',
    )


class ScoringEngineConfig(BaseModel):
    """Phase 9: Quadratic scoring engine parameters.

    Used when DecisionConfig.scoring_version == 'quadratic'.
    Controls exposure transform and shield cascade behavior.
    """

    model_config = ConfigDict(extra='forbid')

    exposure_cap: float = Field(
        ..., gt=0.0, le=1.0,
        description='Maximum absolute exposure after quadratic transform',
    )
    min_pillar_confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description='Minimum pillar_sum magnitude to consider actionable (below -> neutral)',
    )
    shield_enabled: bool = Field(
        ..., description='Enable shield cascade (Phase 3). False = NullShield.',
    )
    context_shield: ContextShieldConfig = Field(
        ...)
    memory_shield: MemoryShieldConfig = Field(
        ...)
    danger_zone_shield: DangerZoneShieldConfig = Field(
        ...)
