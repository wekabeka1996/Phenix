"""
In-Flight Order Configuration.

TASK51-C: Configuration for in-flight order TTL and reconciliation.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class InFlightConfig:
    """
    Configuration for in-flight order management.
    
    TASK51-C: Configurable TTL and reconciliation behavior.
    PURGE-DEAD-CONFIG-03: reconcile_retries/backoff_ms removed (never read in reconciler.py)
    """
    
    # TTL for in-flight orders before reconciliation (seconds)
    inflight_ttl_sec: int = 60
    
    # Maximum TTL before forced expiry (seconds)
    max_ttl_sec: int = 120
    
    # Interval for reconciliation checks (seconds)
    reconcile_interval_sec: int = 10
    
    # Whether to log detailed reconciliation info
    verbose_logging: bool = True
    
    @classmethod
    def from_yaml_dict(cls, data: dict) -> "InFlightConfig":
        """Parse config from YAML dict."""
        return cls(
            inflight_ttl_sec=int(data.get("inflight_ttl_sec", 60)),
            max_ttl_sec=int(data.get("max_ttl_sec", 120)),
            reconcile_interval_sec=int(data.get("reconcile_interval_sec", 10)),
            verbose_logging=bool(data.get("verbose_logging", True)),
        )
    
    @classmethod
    def from_ssot(cls, domains_config: Optional[dict] = None) -> "InFlightConfig":
        """
        Create config from SSOT (domains.yaml).
        
        Looks for inflight_reconcile section in execution_position.
        """
        if not domains_config:
            return cls()
        
        exec_pos = domains_config.get("execution_position", {})
        inflight = exec_pos.get("inflight_reconcile", {})
        
        return cls.from_yaml_dict(inflight)
