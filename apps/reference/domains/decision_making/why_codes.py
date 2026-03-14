"""
WHY Codes — COMPATIBILITY RE-EXPORT.

DEPRECATED: This module is a compatibility shim. The canonical WhyCode
source of truth is ``vfoundation.core.why_codes``.

All new code must import directly from ``vfoundation.core.why_codes``.
This file re-exports the canonical symbols so existing relative imports
(``from .why_codes import WhyCode``) continue to work without breakage.

Migration: replace ``from .why_codes import …`` or
``from apps.reference.domains.decision_making.why_codes import …``
with ``from vfoundation.core.why_codes import …``.
"""

# Re-export canonical symbols for backward compatibility
from vfoundation.core.why_codes import (  # noqa: F401
    WhyCode,
    get_why_description,
    format_why_with_details,
    create_why_payload,
)
