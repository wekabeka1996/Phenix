"""
Compatibility shim for tests expecting `vfoundation.adapters.binance_adapter`.

Re-exports Binance adapter implementation from apps.reference.adapters.binance_adapter.
"""

try:
    # Re-export everything that tests might use
    from apps.reference.adapters.binance_adapter import *  # noqa: F401,F403
except Exception:
    # Minimal placeholder to avoid import errors in collection; tests that rely on
    # real behavior will still fail which is desired in absence of implementation.
    pass

