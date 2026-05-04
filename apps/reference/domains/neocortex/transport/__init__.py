"""Hot-path transport package markers for the Phase 5 authority seam.

The legacy adapter remains quarantined in transport.adapter. This package
marker must stay import-safe so boundary smoke tests can import the new
authority bridge without pulling legacy runtime surfaces.
"""

__all__ = []
