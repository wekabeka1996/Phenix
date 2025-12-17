"""
Reject Reasons Registry.

Normalizes reasons for blocking trades due to configuration contract violations.
Ensures deterministic and observable failures.
"""

from typing import Optional
from apps.reference.config_contract import ConfigContractError

class RejectReason:
    """Standardized rejection reasons."""
    
    # Configuration Contract Violations
    CFG_MISSING = "CFG_MISSING"
    CFG_INVALID = "CFG_INVALID"
    
    # Generic
    UNKNOWN = "UNKNOWN_REJECTION"

def normalize_config_error(e: ConfigContractError) -> str:
    """
    Convert a ConfigContractError into a normalized reject reason string.
    Format: CFG_MISSING:<path> or CFG_INVALID:<path>
    Max length: 80 chars
    """
    prefix = RejectReason.CFG_MISSING # Default to missing for contract errors
    # If we had distinct types in ConfigContractError, we could map them here.
    # For now, most are missing keys.
    
    path = e.path or "unknown_path"
    
    # Ensure reasonable length
    # reason string format: "CFG_MISSING:domains.risk...max_risk"
    reason = f"{prefix}:{path}"
    
    if len(reason) > 80:
        # Truncate path from the left to keep the specific leaf node visible
        # e.g. CFG_MISSING:...sk_management.max_risk
        allowed_len = 80 - len(prefix) - 1 - 3 # -1 for colon, -3 for dots
        truncated_path = "..." + path[-allowed_len:]
        reason = f"{prefix}:{truncated_path}"
        
    return reason
