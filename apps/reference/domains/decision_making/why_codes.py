"""Compatibility re-export for canonical WHY code helpers.

This module is intentionally logic-free. The canonical source of truth is
vfoundation.core.why_codes, and contract tests assert that the objects exposed
here remain identical to the canonical WhyCode class and helper functions.

Keep this shim only for older relative or domain-local imports; new code should
import directly from vfoundation.core.why_codes.
"""

# Re-export the canonical objects without wrapping them so existing imports keep
# object identity and do not fork the enum surface.
from vfoundation.core.why_codes import (  # noqa: F401
    WhyCode,
    get_why_description,
    format_why_with_details,
    create_why_payload,
)
