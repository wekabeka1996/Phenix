"""
Feature Event Parser

Converts raw feature payloads into strict MarketObservation objects.
Includes representation-safe preprocessing for VAE input stability.
"""

from __future__ import annotations

from typing import Any, Dict, Union
import logging
import math

import numpy as np

from apps.reference.domains.neocortex.config_models import IngestConfig
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation

logger = logging.getLogger(__name__)

_EPS = 1e-8
_DEFAULT_CLIP_ABS = {
    "ema_bias": 1.0,
    "spread_bps": 500.0,
    "macro_resid": 5.0,
    "volume_zscore": 10.0,
}


def _flatten_features(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten nested feature dicts into a single-level dict.

    Examples:
      {"volatility": {"atr_14": 1.2}} -> {"volatility_atr_14": 1.2}
      {"volatility.atr_14": 1.2} -> {"volatility_atr_14": 1.2}
    """
    out: Dict[str, Any] = {}

    def _emit(key: str, value: Any) -> None:
        if key not in out:
            out[key] = value

    def _recurse(prefix_parts: list[str], obj: Any) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and "." in k:
                    parts = [p for p in k.split(".") if p]
                else:
                    parts = [str(k)]
                _recurse(prefix_parts + parts, v)
            return

        flat_key = "_".join([p for p in prefix_parts if p])
        _emit(flat_key, obj)

    _recurse([], features)
    return out


class FeatureParser:
    """Stateful parser that respects IngestConfig."""

    def __init__(self, config: IngestConfig):
        self.config = config
        self.feature_indices = {
            name: i for i, name in enumerate(config.feature_list)}
        self._feature_count = len(config.feature_list)

        # Representation preprocessing knobs (defaults are configured in model schema).
        self._price_feature_mode = str(
            getattr(config, "price_feature_mode", "raw")).lower()
        self._delta_price_mode = str(
            getattr(config, "delta_price_mode", "raw")).lower()
        self._clip_abs_cfg: Dict[str, float] = {
            str(k): float(v) for k, v in getattr(config, "feature_clip_abs", {}).items()
            if isinstance(v, (int, float)) and float(v) > 0.0 and math.isfinite(float(v))
        }

    def parse(self, payload: Dict[str, Any]) -> MarketObservation:
        """
        Parse raw event payload into MarketObservation.

        Args:
            payload: Dictionary containing 'timestamp' (or 'ts'), 'features' (dict),
                     and optional metadata like 'mid_price'.

        Returns:
            MarketObservation

        Raises:
            ValueError: If critical fields (ts) are missing.
        """
        # 1) Timestamp
        ts = payload.get("timestamp")
        if ts is None:
            ts = payload.get("ts")
        if ts is None:
            raise ValueError("Payload missing timestamp")
        ts = float(ts)

        # 2) Feature map extraction (root or payload['features'])
        features_dict = payload.get("features")
        if features_dict is None:
            features_dict = payload
        elif not isinstance(features_dict, dict):
            logger.warning(
                "Field 'features' is not a dict: %s", type(features_dict))
            features_dict = payload

        flat_features = _flatten_features(features_dict)

        # 3) Metadata fields (best effort)
        mid_price = self._sanitize_finite(
            self._safe_float(payload.get("mid_price"), 0.0))

        volatility = self._sanitize_finite(
            self._safe_float(payload.get("volatility"), 0.0))
        if volatility == 0.0:
            vol = (
                flat_features.get("bb_width")
                or flat_features.get("atr")
                or flat_features.get("volatility_atr_14")
                or flat_features.get("volatility_true_range")
            )
            volatility = self._sanitize_finite(self._safe_float(vol, 0.0))

        obi = self._sanitize_finite(self._safe_float(payload.get("obi"), 0.0))
        if obi == 0.0:
            obi = self._sanitize_finite(
                self._safe_float(flat_features.get("obi"), 0.0))

        # 4) Build raw per-feature map from config ordering.
        values = {
            name: self._parse_feature_value(flat_features.get(name))
            for name in self.config.feature_list
        }

        # 5) Scale-invariant feature transforms.
        self._apply_representation_transforms(values)

        # 6) Finite + clip sanitization.
        vector = np.zeros(self._feature_count, dtype=np.float32)
        for i, name in enumerate(self.config.feature_list):
            val = self._sanitize_finite(values.get(name, 0.0))
            val = self._clip_value(name, val)
            vector[i] = np.float32(val)

        return MarketObservation(
            ts=ts,
            mid_price=mid_price,
            volatility=volatility,
            obi=obi,
            features_vector=vector,
        )

    def _parse_feature_value(self, raw_val: Any) -> float:
        if raw_val is None:
            return 0.0

        try:
            value = float(raw_val)
        except (ValueError, TypeError):
            return 0.0

        if not np.isfinite(value):
            return 0.0
        return value

    def _apply_representation_transforms(self, values: Dict[str, float]) -> None:
        """
        Apply representation transforms selected in IngestConfig:
        - delta_price_mode: raw | pct
        - price_feature_mode: raw | log | drop
        """
        price = float(values.get("price", 0.0))

        if self._delta_price_mode == "pct" and "delta_price" in values:
            denom = abs(price) if abs(price) > _EPS else _EPS
            values["delta_price"] = float(values["delta_price"] / denom)

        if "price" in values:
            if self._price_feature_mode == "drop":
                values["price"] = 0.0
            elif self._price_feature_mode == "log":
                if price > _EPS:
                    values["price"] = float(np.log(price))
                else:
                    values["price"] = 0.0

    def _clip_value(self, name: str, value: float) -> float:
        # Explicit config clip has highest priority.
        clip_abs = self._clip_abs_cfg.get(name)

        # Dynamic defaults for key heavy-tail features.
        if clip_abs is None:
            if name == "delta_price" and self._delta_price_mode == "pct":
                clip_abs = 0.2
            elif name == "price" and self._price_feature_mode == "log":
                clip_abs = 30.0
            else:
                clip_abs = _DEFAULT_CLIP_ABS.get(name)

        if clip_abs is None:
            return value
        return float(np.clip(value, -clip_abs, clip_abs))

    def _sanitize_finite(self, value: float, default: float = 0.0) -> float:
        if np.isfinite(value):
            return float(value)
        return float(default)

    def _safe_float(self, value: Union[str, float, int, None], default: float) -> float:
        """Safely convert string/decimal to float."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
