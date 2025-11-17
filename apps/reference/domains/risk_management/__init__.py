"""risk_management package export helpers."""

from typing import TYPE_CHECKING, Any

__all__ = ["RiskManagement"]

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .risk_management import RiskManagement  # noqa: F401


def __getattr__(name: str) -> Any:
    """Lazily import RiskManagement to avoid circular import with config_risk."""
    if name == "RiskManagement":
        from .risk_management import RiskManagement as _RiskManagement

        return _RiskManagement
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
