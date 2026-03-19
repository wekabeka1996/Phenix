"""
Aurora TP/SL Computation Mixin.

Extracted from aurora_handler.py (Phase 14A Decomposition).

Provides regime-based TP/SL calculation:
  - pct_mult mode: percentage × regime multiplier
  - atr mode: volatility-based ATR × regime coefficients
  - Guardrails: min/max SL%, min/max RR, min distance bps
"""
from __future__ import annotations

import decimal
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from apps.reference.domains.decision_making.aurora_handler import SymbolState

logger = logging.getLogger("aurora_handler")


class AuroraTpslMixin:
    """
    Mixin: regime-based TP/SL computation for AuroraHandler.

    Self-attributes used (provided by AuroraHandler):
      - self.logger
      - self._symbol_states
      - self.anti_churn_enabled
      - self._get_volatility_strict()
    """

    # ------------------------------------------------------------------
    # ATR Volatility accessor (co-located because _compute_tpsl_atr needs it)
    # ------------------------------------------------------------------

    def _get_volatility_strict(
        self,
        symbol: str,
        features: Dict[str, Any],
    ) -> Optional[decimal.Decimal]:
        """
        Get ATR volatility (STRICT: no fallbacks, fail-closed).

        Reads from:
        1. features["volatility"]["atr_14"] (canonical FE output)
        2. features["atr"] (backward compatibility)

        Returns None if ATR is missing → caller MUST abort signal emission.
        This is fail-closed behavior: prefer no trade over a bad trade.
        """
        atr = None

        # Primary path: nested volatility.atr_14 (from FeatureEngineering)
        volatility_block = features.get("volatility")
        if isinstance(volatility_block, dict):
            atr = volatility_block.get("atr_14")

        # Fallback: top-level "atr" (backward compatibility / tests)
        if atr is None:
            atr = features.get("atr")

        if atr is None:
            self.logger.error(
                f"[{symbol}] ATR_MISSING: volatility_entry_logic requires 'volatility.atr_14' or 'atr'. "
                f"Signal ABORTED (fail-closed). Check FeatureEngineering pipeline."
            )
            return None

        try:
            return decimal.Decimal(str(atr))
        except (decimal.InvalidOperation, ValueError) as e:
            self.logger.error(f"[{symbol}] ATR_INVALID: Cannot convert atr={atr!r} to Decimal: {e}")
            return None

    # ------------------------------------------------------------------
    # Regime-Based TP/SL (AURORA_REGIME_TP_SL_PLAN)
    # ------------------------------------------------------------------

    def _compute_regime_tpsl(
        self,
        symbol: str,
        entry_price: decimal.Decimal,
        side: str,
        regime: Optional[str],
        instr_cfg: Any,
        features: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Compute regime-based TP/SL for Aurora signal.

        Returns dict with:
        - stop_price: Decimal
        - target_price: Decimal
        - tpsl_ctx: dict (telemetry)

        Returns None if regime_tpsl is disabled or config missing.

        AURORA_REGIME_TP_SL_PLAN: Strategy-provided TP/SL injection point.
        """
        if instr_cfg is None:
            return None

        exit_cfg = getattr(instr_cfg, "exit", None)
        if exit_cfg is None:
            return None

        regime_tpsl_cfg = getattr(exit_cfg, "regime_tpsl", None)
        if regime_tpsl_cfg is None or not getattr(regime_tpsl_cfg, "enabled", False):
            return None

        tp_cfg = getattr(instr_cfg, "take_profit", None)

        # Resolve effective regime (prefer effective from anti-churn if enabled)
        state = self._symbol_states.get(symbol)
        if state is None:
            self.logger.warning("[%s] Unknown symbol for regime TP/SL", symbol)
            return None
        if entry_price <= 0:
            self.logger.error(
                "[%s] Invalid entry_price for TP/SL: %s", symbol, entry_price
            )
            return None
        regime_used = regime or "DEFAULT"
        if getattr(self, "anti_churn_enabled", False) and state.regime_effective:
            regime_used = state.regime_effective

        mode = getattr(regime_tpsl_cfg, "mode", "pct_mult")

        # === Calculate SL/TP based on mode ===
        if mode == "pct_mult":
            result = self._compute_tpsl_pct_mult(
                entry_price=entry_price,
                side=side,
                regime_used=regime_used,
                exit_cfg=exit_cfg,
                tp_cfg=tp_cfg,
                regime_tpsl_cfg=regime_tpsl_cfg,
            )
        elif mode == "atr":
            result = self._compute_tpsl_atr(
                symbol=symbol,
                entry_price=entry_price,
                side=side,
                regime_used=regime_used,
                regime_tpsl_cfg=regime_tpsl_cfg,
                features=features,
            )
        else:
            self.logger.warning(f"[{symbol}] Unknown regime_tpsl mode: {mode}, skipping")
            return None

        if result is None:
            return None

        # Apply guardrails
        result = self._apply_tpsl_guardrails(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
            result=result,
            regime_tpsl_cfg=regime_tpsl_cfg,
        )

        return result

    def _compute_tpsl_pct_mult(
        self,
        entry_price: decimal.Decimal,
        side: str,
        regime_used: str,
        exit_cfg: Any,
        tp_cfg: Any,
        regime_tpsl_cfg: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Compute TP/SL using pct_mult mode (simple multipliers).

        SL = entry × (1 ± sl_pct_base × sl_mult[regime])
        TP = entry × (1 ± sl_pct_eff × tp_low_ratio × tp_mult[regime])

        FAIL-CLOSED: Requires explicit sl_pct and tp_low_ratio in config.
        """
        # Get base values (FAIL-CLOSED: no silent defaults)
        sl_pct_raw = getattr(exit_cfg, "sl_pct", None)
        if sl_pct_raw is None:
            self.logger.error(
                "TPSL_CONFIG_ERROR: exit.sl_pct is required for regime_tpsl pct_mult mode. "
                "Add explicit sl_pct to instrument config."
            )
            return None
        sl_pct_base = float(sl_pct_raw)

        tp_low_ratio_raw = getattr(tp_cfg, "tp_low_ratio", None) if tp_cfg else None
        if tp_low_ratio_raw is None:
            self.logger.error(
                "TPSL_CONFIG_ERROR: take_profit.tp_low_ratio is required for regime_tpsl pct_mult mode. "
                "Add explicit tp_low_ratio to instrument config."
            )
            return None
        tp_low_ratio_base = float(tp_low_ratio_raw)

        # Get multipliers (FAIL-CLOSED: DEFAULT key required by model validator)
        sl_mult_map = dict(getattr(regime_tpsl_cfg, "sl_mult", None) or {})
        tp_mult_map = dict(getattr(regime_tpsl_cfg, "tp_mult", None) or {})

        if "DEFAULT" not in sl_mult_map or "DEFAULT" not in tp_mult_map:
            self.logger.error(
                f"TPSL_CONFIG_ERROR: sl_mult and tp_mult must have 'DEFAULT' key. "
                f"Got sl_mult keys: {list(sl_mult_map.keys())}, tp_mult keys: {list(tp_mult_map.keys())}"
            )
            return None

        sl_mult = float(sl_mult_map.get(regime_used, sl_mult_map["DEFAULT"]))
        tp_mult = float(tp_mult_map.get(regime_used, tp_mult_map["DEFAULT"]))

        # Calculate effective values
        sl_pct_eff = sl_pct_base * sl_mult
        tp_rr_eff = tp_low_ratio_base * tp_mult

        # Calculate prices
        sl_pct_dec = decimal.Decimal(str(sl_pct_eff))
        tp_dist_pct = sl_pct_dec * decimal.Decimal(str(tp_rr_eff))

        if side.upper() == "BUY":
            stop_price = entry_price * (1 - sl_pct_dec)
            target_price = entry_price * (1 + tp_dist_pct)
        elif side.upper() == "SELL":
            stop_price = entry_price * (1 + sl_pct_dec)
            target_price = entry_price * (1 - tp_dist_pct)
        else:
            return None

        return {
            "stop_price": stop_price,
            "target_price": target_price,
            "tpsl_ctx": {
                "mode": "pct_mult",
                "regime_used": regime_used,
                "sl_pct_base": sl_pct_base,
                "sl_mult": sl_mult,
                "sl_pct_eff": sl_pct_eff,
                "tp_low_ratio_base": tp_low_ratio_base,
                "tp_mult": tp_mult,
                "tp_rr_eff": tp_rr_eff,
            },
        }

    def _compute_tpsl_atr(
        self,
        symbol: str,
        entry_price: decimal.Decimal,
        side: str,
        regime_used: str,
        regime_tpsl_cfg: Any,
        features: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Compute TP/SL using ATR mode (volatility-based).

        SL = entry ± (atr_pct × sl_k_atr[regime])
        TP = entry ± (sl_dist × rr_by_regime[regime])

        FAIL-CLOSED: Requires ATR feature and explicit config maps.
        """
        # Get ATR (strict, no fallbacks)
        atr = self._get_volatility_strict(symbol, features)
        if atr is None or atr == 0:
            self.logger.warning(f"[{symbol}] ATR missing for regime_tpsl atr mode, skipping TP/SL injection")
            return None

        # ATR as percentage of entry price
        atr_pct = atr / entry_price

        # Get coefficients (FAIL-CLOSED: DEFAULT key required)
        sl_k_map = dict(getattr(regime_tpsl_cfg, "sl_k_atr", None) or {})
        rr_map = dict(getattr(regime_tpsl_cfg, "rr_by_regime", None) or {})

        if "DEFAULT" not in sl_k_map:
            self.logger.error(
                f"[{symbol}] TPSL_CONFIG_ERROR: sl_k_atr must have 'DEFAULT' key for atr mode. "
                f"Got keys: {list(sl_k_map.keys())}"
            )
            return None
        if "DEFAULT" not in rr_map:
            self.logger.error(
                f"[{symbol}] TPSL_CONFIG_ERROR: rr_by_regime must have 'DEFAULT' key for atr mode. "
                f"Got keys: {list(rr_map.keys())}"
            )
            return None

        sl_k = decimal.Decimal(str(sl_k_map.get(regime_used, sl_k_map["DEFAULT"])))
        rr = decimal.Decimal(str(rr_map.get(regime_used, rr_map["DEFAULT"])))

        # Calculate SL distance
        sl_pct_eff = atr_pct * sl_k

        # Calculate prices
        if side.upper() == "BUY":
            stop_price = entry_price * (1 - sl_pct_eff)
            target_price = entry_price * (1 + sl_pct_eff * rr)
        elif side.upper() == "SELL":
            stop_price = entry_price * (1 + sl_pct_eff)
            target_price = entry_price * (1 - sl_pct_eff * rr)
        else:
            return None

        return {
            "stop_price": stop_price,
            "target_price": target_price,
            "tpsl_ctx": {
                "mode": "atr",
                "regime_used": regime_used,
                "atr": float(atr),
                "atr_pct": float(atr_pct),
                "sl_k": float(sl_k),
                "sl_pct_eff": float(sl_pct_eff),
                "rr": float(rr),
            },
        }

    def _apply_tpsl_guardrails(
        self,
        symbol: str,
        entry_price: decimal.Decimal,
        side: str,
        result: Dict[str, Any],
        regime_tpsl_cfg: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        Apply guardrails to computed TP/SL values.

        Validates:
        - SL/TP on correct side of entry
        - min/max SL%
        - min/max TP RR
        - min distance in bps
        """
        stop_price = result["stop_price"]
        target_price = result["target_price"]
        tpsl_ctx = result["tpsl_ctx"]

        # Guardrail params
        min_sl_pct = decimal.Decimal(str(getattr(regime_tpsl_cfg, "min_sl_pct", 0.003)))
        max_sl_pct = decimal.Decimal(str(getattr(regime_tpsl_cfg, "max_sl_pct", 0.06)))
        min_tp_rr = decimal.Decimal(str(getattr(regime_tpsl_cfg, "min_tp_rr", 0.3)))
        max_tp_rr = decimal.Decimal(str(getattr(regime_tpsl_cfg, "max_tp_rr", 3.0)))
        min_dist_bps = int(getattr(regime_tpsl_cfg, "min_dist_bps", 15))

        # Calculate actual SL distance
        if entry_price <= 0:
            self.logger.error(
                "[%s] Invalid entry_price for TP/SL guardrails: %s", symbol, entry_price
            )
            return None
        side_upper = side.upper()
        if side_upper == "BUY":
            sl_dist_pct = (entry_price - stop_price) / entry_price
            tp_dist_pct = (target_price - entry_price) / entry_price
        elif side_upper == "SELL":
            sl_dist_pct = (stop_price - entry_price) / entry_price
            tp_dist_pct = (entry_price - target_price) / entry_price
        else:
            self.logger.error(
                "[%s] Invalid side for TP/SL guardrails: %r", symbol, side
            )
            return None

        # Validate SL on correct side
        if sl_dist_pct <= 0:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: SL on wrong side of entry "
                f"(side={side}, entry={entry_price}, sl={stop_price})"
            )
            return None

        # Validate TP on correct side
        if tp_dist_pct <= 0:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: TP on wrong side of entry "
                f"(side={side}, entry={entry_price}, tp={target_price})"
            )
            return None

        # Clamp SL to min/max (clamp, not fail-closed)
        if sl_dist_pct < min_sl_pct:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: SL too close ({float(sl_dist_pct):.4f} < {float(min_sl_pct):.4f}), "
                f"clamping to min_sl_pct"
            )
            sl_dist_pct = min_sl_pct
            if side.upper() == "BUY":
                stop_price = entry_price * (1 - sl_dist_pct)
            else:
                stop_price = entry_price * (1 + sl_dist_pct)
            tpsl_ctx["guardrail_sl_clamp"] = "min"
        elif sl_dist_pct > max_sl_pct:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: SL too far ({float(sl_dist_pct):.4f} > {float(max_sl_pct):.4f}), "
                f"clamping to max_sl_pct"
            )
            sl_dist_pct = max_sl_pct
            if side.upper() == "BUY":
                stop_price = entry_price * (1 - sl_dist_pct)
            else:
                stop_price = entry_price * (1 + sl_dist_pct)
            tpsl_ctx["guardrail_sl_clamp"] = "max"

        # Calculate RR (Risk:Reward ratio) = TP distance / SL distance
        current_rr = tp_dist_pct / sl_dist_pct if sl_dist_pct > 0 else decimal.Decimal("1.0")

        # Telemetry: capture RR before RR clamp (post SL clamp).
        try:
            tpsl_ctx["rr_pre"] = float(current_rr)
        except (decimal.InvalidOperation, OverflowError, ValueError):
            self.logger.debug("Failed to serialize rr_pre for %s", symbol, exc_info=True)

        # Clamp RR to min/max (adjusts TP, not SL)
        if current_rr < min_tp_rr:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: RR too low ({float(current_rr):.2f} < {float(min_tp_rr):.2f}), "
                f"clamping to min_tp_rr"
            )
            tp_dist_pct = sl_dist_pct * min_tp_rr
            if side.upper() == "BUY":
                target_price = entry_price * (1 + tp_dist_pct)
            else:
                target_price = entry_price * (1 - tp_dist_pct)
            tpsl_ctx["guardrail_rr_clamp"] = "min"
            current_rr = min_tp_rr
        elif current_rr > max_tp_rr:
            self.logger.warning(
                f"[{symbol}] TPSL_GUARDRAIL: RR too high ({float(current_rr):.2f} > {float(max_tp_rr):.2f}), "
                f"clamping to max_tp_rr"
            )
            tp_dist_pct = sl_dist_pct * max_tp_rr
            if side.upper() == "BUY":
                target_price = entry_price * (1 + tp_dist_pct)
            else:
                target_price = entry_price * (1 - tp_dist_pct)
            tpsl_ctx["guardrail_rr_clamp"] = "max"
            current_rr = max_tp_rr

        # Check min distance in bps (after all clamps)
        min_dist_dec = decimal.Decimal(str(min_dist_bps)) / decimal.Decimal("10000")
        if sl_dist_pct < min_dist_dec:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: SL distance {float(sl_dist_pct)*10000:.1f} bps "
                f"< min_dist_bps {min_dist_bps}"
            )
            return None
        if tp_dist_pct < min_dist_dec:
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: TP distance {float(tp_dist_pct)*10000:.1f} bps "
                f"< min_dist_bps {min_dist_bps}"
            )
            return None

        # Update telemetry with effective (post-clamp) values
        tpsl_ctx["sl_pct_eff"] = float(sl_dist_pct)
        tpsl_ctx["tp_pct_eff"] = float(tp_dist_pct)
        tpsl_ctx["rr_eff"] = float(current_rr)

        # Convenience aliases for post-clamp observability.
        tpsl_ctx["sl_pct_post"] = float(sl_dist_pct)
        tpsl_ctx["rr_post"] = float(current_rr)

        return {
            "stop_price": stop_price,
            "target_price": target_price,
            "tpsl_ctx": tpsl_ctx,
        }
