"""
Helper functions for accessing domain-specific configurations.

This module provides a unified interface for domains to access their configurations,
with automatic fallback from new domains.yaml to legacy decision/feature_engineering configs.
"""

from typing import Any, Optional
import logging

LOG = logging.getLogger(__name__)


def get_domains_config(config: Any, domain_name: str) -> Optional[Any]:
    """
    Get domain-specific configuration with fallback to legacy paths.
    
    Args:
        config: The main AuroraConfig object
        domain_name: Name of the domain (e.g., 'decision_making', 'feature_engineering')
    
    Returns:
        Domain configuration object or None
    """
    try:
        if hasattr(config, 'domains'):
            domains = config.domains
            if hasattr(domains, domain_name):
                return getattr(domains, domain_name)
        
        # Fallback: try config.trading.domains if domains is nested  
        if hasattr(config, 'trading') and hasattr(config.trading, 'domains'):
            trading_domains = config.trading.domains
            if hasattr(trading_domains, domain_name):
                return getattr(trading_domains, domain_name)
    except (Attribute Error, TypeError) as e:
        LOG.warning(f"Could not get domains config for {domain_name}: {e}")
    
    return None


def get_config_value(config: Any, domain_name: str, path: str, default: Any = None) -> Any:
    """
    Get a configuration value from domain config with automatic fallback.
    
    Args:
        config: The main AuroraConfig object
        domain_name: Name of the domain
        path: Dotted path to the config value (e.g., 'qos.exposure_block_cooldown_sec')
        default: Default value if not found
    
    Returns:
        Configuration value or default
    
    Example:
        >>> value = get_config_value(config, 'decision_making', 'qos.exposure_block_cooldown_sec', 10)
    """
    try:
        # Try domains config first
        domain_config = get_domains_config(config, domain_name)
        if domain_config:
            value = domain_config
            for part in path.split('.'):
                if hasattr(value, part):
                    value = getattr(value, part)
                elif isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    # Path not found in domains config
                    break
            else:
                # Successfully navigated entire path
                return value if value is not None else default
    except (AttributeError, TypeError, KeyError) as e:
        LOG.debug(f"Could not get {domain_name}.{path} from domains config: {e}")
    
    return default


# Specific helper functions for common domains

def get_decision_making_config(config: Any, param_path: str, default: Any = None) -> Any:
    """Get decision_making domain config value."""
    return get_config_value(config, 'decision_making', param_path, default)


def get_feature_engineering_config(config: Any, param_path: str, default: Any = None) -> Any:
    """Get feature_engineering domain config value."""
    return get_config_value(config, 'feature_engineering', param_path, default)


def get_risk_management_config(config: Any, param_path: str, default: Any = None) -> Any:
    """Get risk_management domain config value."""
    return get_config_value(config, 'risk_management', param_path, default)


def get_execution_position_config(config: Any, param_path: str, default: Any = None) -> Any:
    """Get execution_position domain config value."""
    return get_config_value(config, 'execution_position', param_path, default)


def get_account_observer_config(config: Any, param_path: str, default: Any = None) -> Any:
    """Get account_observer domain config value."""
    return get_config_value(config, 'account_observer', param_path, default)


def get_position_tracking_config(config: Any, param_path: str, default: Any = None) -> Any:
    """Get position_tracking domain config value."""
    return get_config_value(config, 'position_tracking', param_path, default)
