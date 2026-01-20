"""
Configuration Strictness Policy.

Defines the allowed (whitelisted) and forbidden patterns for configuration usage.
Used by static analysis tests to enforce the Strict Config Contract.
"""

from typing import List, Union

class ConfigStrictnessPolicy:
    """
    Policy definition for AST-based configuration strictness checks.
    """
    
    # Whitelist of default allowed values for .get() or getattr()
    # strictly restricted to SENTINELs or DIAGNOSTIC strings.
    # NO numeric trading parameters allowed here.
    ALLOWED_DEFAULTS: List[Union[str, int, float]] = [
        "UNKNOWN",          # Diagnostic default for logging
        "N/A",              # Diagnostic default for logging
        999,                # Strategy Priority sentinel (lowest priority = 999)
        None,               # None is generally safe if handled explicitly
        False,              # Boolean flags defaulting to False are usually safe (disable feature)
        0.0,                # Floating point zeros (confidence, etc.) are safe
        "EMPTY_DICT",       # Empty dict literal {} used for recursive traversal
        10000,              # BAR_TTL_MS fallback when sys_md not configured (T2B safe default)
        "received",         # bar_event_age_mode sentinel
    ]
    
    # Forbidden patterns description for error messages
    FORBIDDEN_GET_MSG = ".get(..., default={val}) forbidden. Must raise ConfigContractError or use SSOT."
    FORBIDDEN_GETATTR_MSG = "getattr(..., default={val}) forbidden. Must raise ConfigContractError."

    @staticmethod
    def is_allowed_default(value: Union[str, int, float, None]) -> bool:
        """Check if a default value is in the whitelist."""
        if value is None:
            return True # Explicit None often implies "optional, handle later" -> acceptable if not dangerous
            
        if value in ConfigStrictnessPolicy.ALLOWED_DEFAULTS:
            return True
            
        # Common safe empty strings/zeros logic if actually benign?
        # Task 17 says "Strict". "0" was allowed for logging in previous task.
        # "0" as string is benign. 0 as int might be dangerous (price, size).
        if value == "0": 
            return True
            
        return False
