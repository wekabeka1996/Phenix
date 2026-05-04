"""
Compatibility shim for tests expecting `vfoundation.obs.order_logger`.

Re-exports `order_logger` from apps.reference.telemetry.order_logger.
"""

try:
    from apps.reference.telemetry.order_logger import order_logger  # type: ignore
except Exception:  # pragma: no cover - fallback dummy
    class _DummyOrderLogger:
        def write(self, *args, **kwargs):
            pass

    order_logger = _DummyOrderLogger()

