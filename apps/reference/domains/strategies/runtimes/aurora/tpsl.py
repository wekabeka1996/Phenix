"""Compute optional regime-aware TP/SL candidates for Aurora signals.

This mixin only derives candidate stop/target prices plus TP/SL telemetry. It
does not place orders and it does not decide on its own whether a missing TP/SL
result should block signal emission; that decision stays with the caller.
"""
from __future__ import annotations

import decimal
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from apps.reference.shared.decision_primitives.tpsl_owner import (
    TPSL_OWNER_LOSS_ATR_UNAVAILABLE,
    TPSL_OWNER_LOSS_CONFIG_ERROR,
    TPSL_OWNER_LOSS_DISABLED_OR_MISSING,
    TPSL_OWNER_LOSS_INVALID_INPUT,
    TPSL_OWNER_LOSS_SL_MIN_DIST_BPS,
    TPSL_OWNER_LOSS_SL_WRONG_SIDE,
    TPSL_OWNER_LOSS_TP_MIN_DIST_BPS,
    TPSL_OWNER_LOSS_TP_WRONG_SIDE,
    TPSL_OWNER_LOSS_UNSUPPORTED_MODE,
)
from apps.reference.domains.strategies.runtimes.aurora.policies import (
    RegimeTpslCalculator,
)

if TYPE_CHECKING:
    from apps.reference.domains.strategies.runtimes.aurora.handler import SymbolState

logger = logging.getLogger("aurora_handler")


class AuroraTpslMixin:
    """Provide regime-aware TP/SL computation helpers for AuroraHandler.

    Host contract:
    - ``self.logger`` is available for diagnostics.
    - ``self._symbol_states`` stores per-symbol regime state.
    - ``self.anti_churn_enabled`` controls whether regime_effective overrides
      the raw regime passed by the caller.

    Side effects are limited to logging; successful methods return computed
    prices and telemetry dictionaries.
    """

    def _set_tpsl_owner_loss_reason(self, reason: Optional[str]) -> None:
        self._tpsl_owner_loss_reason = reason

    def _get_tpsl_owner_loss_reason(self) -> Optional[str]:
        return getattr(self, "_tpsl_owner_loss_reason", None)

    # ------------------------------------------------------------------
    # ATR Volatility accessor (co-located because _compute_tpsl_atr needs it)
    # ------------------------------------------------------------------

    def _get_volatility_strict(
        self,
        symbol: str,
        features: Dict[str, Any],
    ) -> Optional[decimal.Decimal]:
        """
        Return ATR as Decimal using the Aurora feature contract.

        Reads from:
        1. features["volatility"]["atr_14"] (canonical FE output)
        2. features["atr"] (backward compatibility)

        Returns None when ATR is missing or invalid.

        Important: this helper is strict about data extraction, but the caller
        decides whether missing ATR is fatal for the whole signal or only for
        TP/SL injection.
        """
        atr = None

        # Canonical FE output lives under volatility.atr_14. The top-level key
        # remains only for older fixtures and compatibility paths.
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
            self.logger.error(
                f"[{symbol}] ATR_INVALID: Cannot convert atr={atr!r} to Decimal: {e}")
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
        Compute regime-based TP/SL for a candidate Aurora entry.

        Returns dict with:
        - stop_price: Decimal
        - target_price: Decimal
        - tpsl_ctx: dict (telemetry)

        Returns None when TP/SL injection is disabled, config is incomplete,
        symbol state is unavailable, ATR is unusable for atr mode, or the
        resulting geometry is rejected by guardrails.

        This method only computes candidate prices. Downstream code decides
        whether a None result means "emit without TP/SL" or "block signal".
        """
        self._set_tpsl_owner_loss_reason(None)

        if instr_cfg is None:
            self._set_tpsl_owner_loss_reason(
                TPSL_OWNER_LOSS_DISABLED_OR_MISSING)
            return None

        exit_cfg = getattr(instr_cfg, "exit", None)
        if exit_cfg is None:
            self._set_tpsl_owner_loss_reason(
                TPSL_OWNER_LOSS_DISABLED_OR_MISSING)
            return None

        regime_tpsl_cfg = getattr(exit_cfg, "regime_tpsl", None)
        if regime_tpsl_cfg is None or not getattr(regime_tpsl_cfg, "enabled", False):
            self._set_tpsl_owner_loss_reason(
                TPSL_OWNER_LOSS_DISABLED_OR_MISSING)
            return None

        tp_cfg = getattr(instr_cfg, "take_profit", None)

        # TP/SL follows the same effective regime that anti-churn can pin for
        # entry/exit decisions, not just the raw detector regime.
        state = self._symbol_states.get(symbol)
        if state is None:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_INVALID_INPUT)
            self.logger.warning("[%s] Unknown symbol for regime TP/SL", symbol)
            return None
        if entry_price <= 0:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_INVALID_INPUT)
            self.logger.error(
                "[%s] Invalid entry_price for TP/SL: %s", symbol, entry_price
            )
            return None
        regime_used = RegimeTpslCalculator().select_regime(
            raw_regime=regime,
            effective_regime=state.regime_effective,
            anti_churn_enabled=bool(getattr(self, "anti_churn_enabled", False)),
        ).regime_used

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
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_UNSUPPORTED_MODE)
            self.logger.warning(
                f"[{symbol}] Unknown regime_tpsl mode: {mode}, skipping")
            return None

        if result is None:
            return None

        # Guardrails normalize the candidate prices into an emit-safe geometry.
        # A None return here means "no TP/SL payload", not necessarily a hard
        # abort for the whole decision path.
        result = self._apply_tpsl_guardrails(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
            result=result,
            regime_tpsl_cfg=regime_tpsl_cfg,
        )
        if result is not None:
            self._set_tpsl_owner_loss_reason(None)

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
        self._set_tpsl_owner_loss_reason(None)

        # Get base values (FAIL-CLOSED: no silent defaults)
        sl_pct_raw = getattr(exit_cfg, "sl_pct", None)
        if sl_pct_raw is None:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_CONFIG_ERROR)
            self.logger.error(
                "TPSL_CONFIG_ERROR: exit.sl_pct is required for regime_tpsl pct_mult mode. "
                "Add explicit sl_pct to instrument config."
            )
            return None
        sl_pct_base = float(sl_pct_raw)

        tp_low_ratio_raw = getattr(
            tp_cfg, "tp_low_ratio", None) if tp_cfg else None
        if tp_low_ratio_raw is None:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_CONFIG_ERROR)
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
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_CONFIG_ERROR)
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
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_INVALID_INPUT)
            return None

        self._set_tpsl_owner_loss_reason(None)
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

        FAIL-CLOSED at the TP/SL layer: requires ATR input and explicit config
        maps. Missing ATR disables TP/SL injection for this path.
        """
        self._set_tpsl_owner_loss_reason(None)

        # Get ATR (strict, no fallbacks)
        atr = self._get_volatility_strict(symbol, features)
        if atr is None or atr == 0:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_ATR_UNAVAILABLE)
            self.logger.warning(
                f"[{symbol}] ATR missing for regime_tpsl atr mode, skipping TP/SL injection")
            return None

        # Normalizing ATR by entry keeps the regime coefficients dimensionless
        # across symbols with very different price scales.
        atr_pct = atr / entry_price

        # Get coefficients (FAIL-CLOSED: DEFAULT key required)
        sl_k_map = dict(getattr(regime_tpsl_cfg, "sl_k_atr", None) or {})
        rr_map = dict(getattr(regime_tpsl_cfg, "rr_by_regime", None) or {})

        if "DEFAULT" not in sl_k_map:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_CONFIG_ERROR)
            self.logger.error(
                f"[{symbol}] TPSL_CONFIG_ERROR: sl_k_atr must have 'DEFAULT' key for atr mode. "
                f"Got keys: {list(sl_k_map.keys())}"
            )
            return None
        if "DEFAULT" not in rr_map:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_CONFIG_ERROR)
            self.logger.error(
                f"[{symbol}] TPSL_CONFIG_ERROR: rr_by_regime must have 'DEFAULT' key for atr mode. "
                f"Got keys: {list(rr_map.keys())}"
            )
            return None

        sl_k = decimal.Decimal(
            str(sl_k_map.get(regime_used, sl_k_map["DEFAULT"])))
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
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_INVALID_INPUT)
            return None

        self._set_tpsl_owner_loss_reason(None)
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
        Apply final TP/SL guardrails to already computed candidate prices.

        Order matters:
        - reject wrong-side geometry immediately;
        - clamp SL distance into the configured band;
        - recompute effective RR against the post-SL geometry;
        - clamp TP RR if needed;
        - finally reject setups that still violate min_dist_bps.
        """
        stop_price = result["stop_price"]
        target_price = result["target_price"]
        tpsl_ctx = result["tpsl_ctx"]

        # Guardrail params
        min_sl_pct = decimal.Decimal(
            str(getattr(regime_tpsl_cfg, "min_sl_pct", 0.003)))
        max_sl_pct = decimal.Decimal(
            str(getattr(regime_tpsl_cfg, "max_sl_pct", 0.06)))
        min_tp_rr = decimal.Decimal(
            str(getattr(regime_tpsl_cfg, "min_tp_rr", 0.3)))
        max_tp_rr = decimal.Decimal(
            str(getattr(regime_tpsl_cfg, "max_tp_rr", 3.0)))
        min_dist_bps = int(getattr(regime_tpsl_cfg, "min_dist_bps", 15))

        # Calculate actual SL distance
        if entry_price <= 0:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_INVALID_INPUT)
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
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_INVALID_INPUT)
            self.logger.error(
                "[%s] Invalid side for TP/SL guardrails: %r", symbol, side
            )
            return None

        # Validate SL on correct side
        if sl_dist_pct <= 0:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_SL_WRONG_SIDE)
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: SL on wrong side of entry "
                f"(side={side}, entry={entry_price}, sl={stop_price})"
            )
            return None

        # Validate TP on correct side
        if tp_dist_pct <= 0:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_TP_WRONG_SIDE)
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
        current_rr = tp_dist_pct / \
            sl_dist_pct if sl_dist_pct > 0 else decimal.Decimal("1.0")

        # Telemetry: capture RR before RR clamp (post SL clamp).
        try:
            tpsl_ctx["rr_pre"] = float(current_rr)
        except (decimal.InvalidOperation, OverflowError, ValueError):
            self.logger.debug(
                "Failed to serialize rr_pre for %s", symbol, exc_info=True)

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

        # min_dist_bps is evaluated on the final post-clamp geometry because it
        # is a contract on the emitted prices, not on intermediate values.
        min_dist_dec = decimal.Decimal(
            str(min_dist_bps)) / decimal.Decimal("10000")
        if sl_dist_pct < min_dist_dec:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_SL_MIN_DIST_BPS)
            self.logger.error(
                f"[{symbol}] TPSL_GUARDRAIL_FAIL: SL distance {float(sl_dist_pct)*10000:.1f} bps "
                f"< min_dist_bps {min_dist_bps}"
            )
            return None
        if tp_dist_pct < min_dist_dec:
            self._set_tpsl_owner_loss_reason(TPSL_OWNER_LOSS_TP_MIN_DIST_BPS)
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

        self._set_tpsl_owner_loss_reason(None)
        return {
            "stop_price": stop_price,
            "target_price": target_price,
            "tpsl_ctx": tpsl_ctx,
        }
