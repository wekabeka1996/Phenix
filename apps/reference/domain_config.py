"""
Domain Configuration Resolver.

Provides unified, type-safe access to domain-specific configurations.
Eliminates isinstance(config, dict) checks and hasattr spaghetti throughout the codebase.

Usage:
    resolver = DomainConfigResolver(aurora_config)
    eg_config = resolver.get_exposure_guard()
    watchdog_config = resolver.get_watchdog()
"""

from __future__ import annotations

import logging
import warnings
from typing import Optional, TYPE_CHECKING

from .config_models import (
    AuroraConfig,
    DomainsConfig,
    ExecutionPositionDomainConfig,
    ExposureGuardConfig,
    WatchdogConfig,
    FsmOpenConfig,
    OrderIndexConfig,
    MetricsCollectorConfig,
    IdempotentCancelConfig,
    ExecutionUtilsConfig,
    DecisionMakingDomainConfig,
    FeatureEngineeringDomainConfig,
    RiskManagementDomainConfig,
    PositionTrackingDomainConfig,
    AccountObserverDomainConfig,
    BracketsConfig,
    ManageConfig,
    ExposureConfig,
)

if TYPE_CHECKING:
    from decimal import Decimal

LOG = logging.getLogger(__name__)


class DomainConfigResolver:
    """
    Unified configuration resolver for all domains.
    
    Provides type-safe access to domain configs with proper fallbacks.
    All methods return typed Pydantic models, enabling IDE autocomplete.
    
    Example:
        >>> resolver = DomainConfigResolver(config)
        >>> eg = resolver.get_exposure_guard()
        >>> eg.max_equity_utilization_pct  # IDE knows this is float!
    """
    
    __slots__ = ('_config', '_domains', '_cached_execution_position')
    
    def __init__(self, config: AuroraConfig):
        """
        Initialize resolver with validated AuroraConfig.
        
        Args:
            config: Validated AuroraConfig instance (not dict!)
        
        Raises:
            TypeError: If config is dict (legacy pattern)
        """
        if isinstance(config, dict):
            raise TypeError(
                f"DomainConfigResolver requires AuroraConfig, got dict. "
                "Convert dict to AuroraConfig first."
            )
        self._config = config
        self._domains: Optional[DomainsConfig] = None
        self._cached_execution_position: Optional[ExecutionPositionDomainConfig] = None
        
        # Eagerly resolve domains to fail fast
        self._domains = self._resolve_domains()
    
    def _resolve_domains(self) -> DomainsConfig:
        """
        Resolve DomainsConfig from AuroraConfig.
        
        CFG-DOMAINS-STEP-02: CANONICAL ONLY (fail-closed).
        
        Priority:
        1. config.domains (root level) — CANONICAL
        2. FAIL if missing (no fallback to trading.domains)
        
        Note: trading.domains exists as deprecated mirror for legacy code,
              but resolver MUST NOT read it (enforce canonical path).
        
        Raises:
            ValueError: If config.domains is None or missing
        """
        # CANONICAL PATH ONLY
        if self._config.domains is not None:
            return self._config.domains
        
        # FAIL CLOSED: domains REQUIRED (no fallback)
        raise ValueError(
            "DomainConfigResolver requires config.domains (canonical). "
            "Ensure domains.yaml is loaded and config.domains is populated. "
            "Legacy trading.domains is NOT used by resolver."
        )
    
    # =========================================================================
    # EXECUTION_POSITION DOMAIN
    # =========================================================================
    
    def get_execution_position(self) -> ExecutionPositionDomainConfig:
        """Get complete execution_position domain configuration."""
        if self._cached_execution_position is None:
            self._cached_execution_position = self._domains.execution_position
        return self._cached_execution_position
    
    def get_exposure_guard(self) -> ExposureGuardConfig:
        """Get ExposureGuard configuration with all limits and TTLs."""
        return self.get_execution_position().exposure_guard
    
    def get_watchdog(self) -> WatchdogConfig:
        """Get OrderTimeoutWatchdog configuration."""
        return self.get_execution_position().watchdog
    
    def get_fsm_open(self) -> FsmOpenConfig:
        """Get FSM Open configuration (idempotency settings)."""
        return self.get_execution_position().fsm_open
    
    def get_order_index(self) -> OrderIndexConfig:
        """Get Order Index TTL configuration."""
        return self.get_execution_position().order_index
    
    def get_metrics_collector(self) -> MetricsCollectorConfig:
        """Get Metrics Collector configuration."""
        return self.get_execution_position().metrics_collector
    
    def get_idempotent_cancel(self) -> IdempotentCancelConfig:
        """Get Idempotent Cancel retry configuration."""
        return self.get_execution_position().idempotent_cancel
    
    def get_execution_utils(self) -> ExecutionUtilsConfig:
        """Get execution utilities configuration."""
        return self.get_execution_position().utils
    
    def get_brackets_strict(self) -> BracketsConfig:
        """
        Get brackets config (fail-closed, no defaults).
        
        SSOT: trading.execution.manage.brackets (will migrate to domains in future).
        
        Raises:
            ValueError: If brackets config is missing or incomplete
        """
        try:
            if (self._config.trading and 
                self._config.trading.execution and 
                self._config.trading.execution.manage and
                self._config.trading.execution.manage.brackets):
                brackets = self._config.trading.execution.manage.brackets
                
                # Validate required fields exist
                if brackets.sl is None or brackets.sl.fixed_bps is None:
                    raise ValueError(
                        "BracketsConfig.sl.fixed_bps is required (got None). "
                        "Check trading.yaml: trading.execution.manage.brackets.sl.fixed_bps"
                    )
                if brackets.tp is None or brackets.tp.fixed_bps is None:
                    raise ValueError(
                        "BracketsConfig.tp.fixed_bps is required (got None). "
                        "Check trading.yaml: trading.execution.manage.brackets.tp.fixed_bps"
                    )
                    
                return brackets
        except AttributeError as e:
            raise ValueError(
                f"Failed to access brackets config path: {e}. "
                "Ensure trading.yaml has trading.execution.manage.brackets section."
            ) from e
        
        raise ValueError(
            "BracketsConfig not found in trading.execution.manage.brackets. "
            "This is required for TP/SL calculation - no defaults allowed."
        )
    
    # =========================================================================
    # OTHER DOMAINS
    # =========================================================================
    
    def get_decision_making(self) -> DecisionMakingDomainConfig:
        """Get decision_making domain configuration."""
        return self._domains.decision_making
    
    def get_feature_engineering(self) -> FeatureEngineeringDomainConfig:
        """Get feature_engineering domain configuration."""
        return self._domains.feature_engineering
    
    def get_risk_management(self) -> RiskManagementDomainConfig:
        """Get risk_management domain configuration."""
        return self._domains.risk_management
    
    def get_position_tracking(self) -> PositionTrackingDomainConfig:
        """Get position_tracking domain configuration."""
        return self._domains.position_tracking
    
    # def get_account_observer(self) -> AccountObserverDomainConfig: (Deleted)
    #    """Get account_observer domain configuration."""
    #    return self._domains.account_observer
    
    # =========================================================================
    # LEGACY ACCESSORS (DEPRECATED)
    # =========================================================================
    
    def get_legacy_exposure(self) -> Optional[ExposureConfig]:
        """
        Get legacy trading.execution.exposure config.
        
        DEPRECATED: Use get_exposure_guard() instead.
        """
        warnings.warn(
            "get_legacy_exposure() is deprecated. "
            "Use get_exposure_guard() for domains.execution_position.exposure_guard",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            if (self._config.trading and 
                self._config.trading.execution and 
                self._config.trading.execution.exposure):
                return self._config.trading.execution.exposure
        except AttributeError:
            pass
        return None
    
    def get_legacy_brackets(self) -> Optional[BracketsConfig]:
        """
        Get legacy brackets config from trading.execution.manage.brackets.
        
        DEPRECATED: Will be moved to domains in future.
        """
        warnings.warn(
            "get_legacy_brackets() is deprecated. "
            "Brackets config will move to domains.execution_position in future.",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            if (self._config.trading and 
                self._config.trading.execution and 
                self._config.trading.execution.manage and
                self._config.trading.execution.manage.brackets):
                return self._config.trading.execution.manage.brackets
        except AttributeError:
            pass
        return None
    
    def get_legacy_manage(self) -> Optional[ManageConfig]:
        """
        Get legacy manage config from trading.execution.manage.
        
        DEPRECATED: Will be moved to domains in future.
        """
        warnings.warn(
            "get_legacy_manage() is deprecated. "
            "Manage config will move to domains.execution_position in future.",
            DeprecationWarning,
            stacklevel=2
        )
        try:
            if (self._config.trading and 
                self._config.trading.execution and 
                self._config.trading.execution.manage):
                return self._config.trading.execution.manage
        except AttributeError:
            pass
        return None
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    @property
    def trading_mode(self) -> str:
        """Get current trading mode (testnet/production/live)."""
        return self._config.trading_mode
    
    @property
    def raw_config(self) -> AuroraConfig:
        """Get underlying AuroraConfig (for edge cases)."""
        return self._config
    
    def __repr__(self) -> str:
        return f"DomainConfigResolver(mode={self.trading_mode})"


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_resolver(config: AuroraConfig) -> DomainConfigResolver:
    """
    Create a DomainConfigResolver from AuroraConfig.
    
    Args:
        config: Validated AuroraConfig
        
    Returns:
        Configured DomainConfigResolver
    """
    return DomainConfigResolver(config)


def create_resolver_from_dict(config_dict: dict) -> DomainConfigResolver:
    """
    Create a DomainConfigResolver from raw dict.
    
    Validates dict through Pydantic first.
    
    Args:
        config_dict: Raw configuration dictionary
        
    Returns:
        Configured DomainConfigResolver
        
    Raises:
        pydantic.ValidationError: If config is invalid
    """
    aurora_config = AuroraConfig(**config_dict)
    return DomainConfigResolver(aurora_config)
