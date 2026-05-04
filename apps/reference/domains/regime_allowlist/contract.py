"""
Regime Allowlist Contract.

TASK51-B: Explicit validation that strategies have proper regime configurations.
Ensures that:
1. MR-capable strategies have MEAN_REVERSION in allowed_regimes OR explicitly disable it
2. Regime blocking is explainable and config-driven
3. No implicit/hidden regime blocks

Contract:
- If strategy assignment includes "mean_reversion", the symbol's allowed_regimes
  MUST contain at least one FLAT regime OR explicitly define MR behavior
- Config mismatches are detected at startup (fail-closed for LIVE)
"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

LOG = logging.getLogger(__name__)


# Known regime types
ALL_REGIMES = frozenset([
    "TREND_UP",
    "TREND_DOWN",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
    "MEAN_REVERSION",
    "UNCERTAIN",
    "FLAT_LOW",
    "FLAT_NORMAL",
    "FLAT_HIGH",
])

# Regimes that are compatible with Mean Reversion strategy
MR_COMPATIBLE_REGIMES = frozenset([
    "FLAT_LOW",
    "FLAT_NORMAL",
    "FLAT_HIGH",
    "LOW_VOLATILITY",
    "MEAN_REVERSION",
])

# Regimes that are compatible with Aurora (momentum/trend)
AURORA_COMPATIBLE_REGIMES = frozenset([
    "TREND_UP",
    "TREND_DOWN",
    "HIGH_VOLATILITY",
    "LOW_VOLATILITY",
])


class RegimeAllowlistError(Exception):
    """
    Raised when regime allowlist configuration is invalid.
    
    This is a fail-closed exception for LIVE mode to prevent
    silent regime blocking.
    """
    
    def __init__(self, violations: List["AllowlistViolation"]):
        self.violations = violations
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        lines = ["Regime allowlist configuration errors (fail-closed):"]
        for v in self.violations:
            lines.append(f"  [{v.severity}] {v.symbol}: {v.message}")
        lines.append("")
        lines.append("Fix: Update config/aurora/strategies/aurora.yaml (aurora.assets) or strategies.yaml")
        return "\n".join(lines)


@dataclass
class AllowlistViolation:
    """Describes a regime allowlist configuration violation."""
    symbol: str
    strategy: str
    message: str
    severity: str  # CRITICAL, WARNING, INFO
    
    def __str__(self) -> str:
        return f"[{self.severity}] {self.symbol}/{self.strategy}: {self.message}"


@dataclass
class StrategyRegimeConfig:
    """
    Extracted regime configuration for a symbol+strategy pair.
    
    Used for validation to ensure explainable regime behavior.
    """
    symbol: str
    strategy: str
    allowed_regimes: Optional[List[str]]
    has_mr_assignment: bool
    has_aurora_assignment: bool
    
    @property
    def allows_mr_regimes(self) -> bool:
        """Check if config allows any MR-compatible regimes."""
        # STRICT allowlist semantics:
        # - allowed_regimes missing/empty => allow NOTHING (fail-closed)
        if not self.allowed_regimes:
            return False
        return bool(set(self.allowed_regimes) & MR_COMPATIBLE_REGIMES)
    
    @property
    def allows_aurora_regimes(self) -> bool:
        """Check if config allows any Aurora-compatible regimes."""
        if not self.allowed_regimes:
            return False
        return bool(set(self.allowed_regimes) & AURORA_COMPATIBLE_REGIMES)

    @property
    def is_aurora_enabled_but_blocked(self) -> bool:
        """Aurora assigned but all Aurora-compatible regimes are blocked."""
        return self.has_aurora_assignment and not self.allows_aurora_regimes
    
    @property
    def is_mr_enabled_but_blocked(self) -> bool:
        """
        Check if MR strategy is assigned but all MR regimes are blocked.
        
        This is a configuration error: why assign MR if it can never fire?
        """
        return self.has_mr_assignment and not self.allows_mr_regimes


class RegimeAllowlistContract:
    """
    Validates regime allowlist configurations across strategies.
    
    TASK51-B Contract:
    - If strategy "mean_reversion" is assigned to a symbol, at least one
      MR-compatible regime must be in allowed_regimes
        - STRICT: If allowed_regimes is empty/None, all regimes are BLOCKED (fail-closed)
    - Blocking must be explicit and explainable in logs
    """
    
    @staticmethod
    def extract_strategy_config(
        symbol: str,
        assignments: Dict[str, List[str]],
        aurora_assets: Dict[str, Any],
    ) -> StrategyRegimeConfig:
        """
        Extract regime configuration for a symbol.
        
        Args:
            symbol: Trading symbol
            assignments: strategies.yaml assignments
            aurora_assets: strategies/aurora.yaml::aurora.assets config
            
        Returns:
            StrategyRegimeConfig for validation
        """
        symbol_strategies = assignments.get(symbol, [])
        symbol_config = aurora_assets.get(symbol, {})
        
        return StrategyRegimeConfig(
            symbol=symbol,
            strategy=",".join(symbol_strategies) if symbol_strategies else "none",
            allowed_regimes=symbol_config.get("allowed_regimes"),
            has_mr_assignment="mean_reversion" in symbol_strategies,
            has_aurora_assignment="aurora" in symbol_strategies,
        )
    
    @staticmethod
    def validate_symbol(config: StrategyRegimeConfig) -> List[AllowlistViolation]:
        """
        Validate a single symbol's regime configuration.
        
        Returns:
            List of violations (empty if valid)
        """
        violations = []
        
        # Check: MR assigned but no MR-compatible regimes allowed
        if config.is_mr_enabled_but_blocked:
            violations.append(AllowlistViolation(
                symbol=config.symbol,
                strategy="mean_reversion",
                message=(
                    f"MR strategy assigned but no MR-compatible regimes in allowed_regimes: "
                    f"{config.allowed_regimes}. Add FLAT_LOW/FLAT_NORMAL/FLAT_HIGH or MEAN_REVERSION."
                ),
                severity="CRITICAL",
            ))

        # Check: Aurora assigned but no Aurora-compatible regimes allowed
        if config.is_aurora_enabled_but_blocked:
            violations.append(AllowlistViolation(
                symbol=config.symbol,
                strategy="aurora",
                message=(
                    f"Aurora strategy assigned but no Aurora-compatible regimes in allowed_regimes: "
                    f"{config.allowed_regimes}. Add TREND_UP/TREND_DOWN/LOW_VOLATILITY/HIGH_VOLATILITY."
                ),
                severity="CRITICAL",
            ))
        
        # Check: Unknown regimes in allowlist
        if config.allowed_regimes:
            unknown = set(config.allowed_regimes) - ALL_REGIMES
            if unknown:
                violations.append(AllowlistViolation(
                    symbol=config.symbol,
                    strategy=config.strategy,
                    message=f"Unknown regimes in allowed_regimes: {unknown}",
                    severity="WARNING",
                ))
        
        # Info: MR assigned and MR regimes allowed (expected behavior)
        if config.has_mr_assignment and config.allows_mr_regimes:
            LOG.debug(
                f"[{config.symbol}] MR strategy enabled with MR-compatible regimes: "
                f"{set(config.allowed_regimes or []) & MR_COMPATIBLE_REGIMES}"
            )
        
        return violations
    
    @classmethod
    def validate_all(
        cls,
        assignments: Dict[str, List[str]],
        aurora_assets: Dict[str, Any],
        *,
        fail_on_critical: bool = True,
    ) -> Dict[str, List[AllowlistViolation]]:
        """
        Validate all symbols' regime configurations.
        
        Args:
            assignments: strategies.yaml assignments section
            aurora_assets: strategies/aurora.yaml::aurora.assets config
            fail_on_critical: If True, raise exception on critical violations
            
        Returns:
            Dict of symbol -> violations
            
        Raises:
            RegimeAllowlistError: On critical violations if fail_on_critical=True
        """
        LOG.info(f"Validating regime allowlist for {len(assignments)} symbols...")
        
        all_violations: Dict[str, List[AllowlistViolation]] = {}
        critical_violations: List[AllowlistViolation] = []
        
        for symbol in assignments:
            config = cls.extract_strategy_config(symbol, assignments, aurora_assets)
            violations = cls.validate_symbol(config)
            
            if violations:
                all_violations[symbol] = violations
                critical_violations.extend(
                    v for v in violations if v.severity == "CRITICAL"
                )
                
                for v in violations:
                    if v.severity == "CRITICAL":
                        LOG.error(str(v))
                    else:
                        LOG.warning(str(v))
            else:
                LOG.info(f"✅ {symbol}: regime allowlist OK")
        
        if critical_violations and fail_on_critical:
            raise RegimeAllowlistError(critical_violations)
        
        return all_violations
    
    @staticmethod
    def explain_blocking(
        symbol: str,
        current_regime: str,
        allowed_regimes: Optional[List[str]],
    ) -> str:
        """
        Generate explainable reason for regime blocking.
        
        TASK51-B: All regime blocks must be explainable.
        
        Args:
            symbol: Trading symbol
            current_regime: Current detected regime
            allowed_regimes: Configured allowed regimes
            
        Returns:
            Human-readable explanation
        """
        if not allowed_regimes:
            return (
                f"[{symbol}] Regime {current_regime} BLOCKED: allowed_regimes is missing/empty (fail-closed) "
                f"(configured in strategies/*.yaml allowlists)"
            )
        
        if current_regime in allowed_regimes:
            return f"[{symbol}] Regime {current_regime} is ALLOWED"
        
        return (
            f"[{symbol}] Regime {current_regime} BLOCKED: "
            f"not in allowed_regimes={allowed_regimes} "
            f"(configured in strategies/aurora.yaml::aurora.assets)"
        )

    @staticmethod
    def is_regime_allowed(*, current_regime: str, allowed_regimes: Optional[List[str]]) -> bool:
        """Strict allowlist semantics: only explicitly listed regimes are allowed."""
        if not allowed_regimes:
            return False
        return str(current_regime) in set(str(x) for x in allowed_regimes)


def validate_strategy_regime_config(
    strategies_yaml: Dict[str, Any],
    aurora_assets_yaml: Dict[str, Any],
    *,
    mode: str = "live",
    warn_only: bool = False,
) -> None:
    """
    Startup hook: Validate strategy regime configurations.
    
    TASK51-B: Called during startup to ensure regime configs are valid.
    
    Args:
        strategies_yaml: Parsed strategies.yaml
        aurora_assets_yaml: Parsed strategies/aurora.yaml::aurora.assets
        mode: Operating mode (live/testnet/shadow/dev)
        warn_only: If True, warn instead of crash (DEV/SHADOW only)
        
    Raises:
        RegimeAllowlistError: On critical violations in LIVE/TESTNET mode
    """
    assignments = strategies_yaml.get("assignments", {})
    
    if not assignments:
        LOG.warning("No strategy assignments found - skipping regime validation")
        return
    
    RegimeAllowlistContract.validate_all(
        assignments,
        aurora_assets_yaml,
        fail_on_critical=not warn_only,
    )
