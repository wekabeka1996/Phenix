"""optimization.research — research harness entrypoints.

Package imports must stay usable even when the legacy SelectiveOptimizer path has
optional runtime dependencies that are unavailable in a narrow test environment.
"""

from typing import Any

ResearchHarnessConfig = None
ResearchHarnessRunner = None
build_strategy_proxy_spec = None

SelectiveOptimizer = None
ResearchObjectiveMode = None
ResearchStudyConfig = None
ResearchGates = None

try:
    from optimization.research.selective_optimizer import (
        SelectiveOptimizer,
        ResearchObjectiveMode,
        ResearchStudyConfig,
        ResearchGates,
    )
except (ModuleNotFoundError, ImportError):
    # Optional legacy path: keep package importable for proxy-only harness usage.
    pass

__all__ = [
    "SelectiveOptimizer",
    "ResearchObjectiveMode",
    "ResearchStudyConfig",
    "ResearchGates",
    "ResearchHarnessConfig",
    "ResearchHarnessRunner",
    "build_strategy_proxy_spec",
]


def __getattr__(name: str) -> Any:
    if name in {"ResearchHarnessConfig", "ResearchHarnessRunner", "build_strategy_proxy_spec"}:
        from optimization.research.proxy_runner import (
            ResearchHarnessConfig as _ResearchHarnessConfig,
            ResearchHarnessRunner as _ResearchHarnessRunner,
            build_strategy_proxy_spec as _build_strategy_proxy_spec,
        )

        exports = {
            "ResearchHarnessConfig": _ResearchHarnessConfig,
            "ResearchHarnessRunner": _ResearchHarnessRunner,
            "build_strategy_proxy_spec": _build_strategy_proxy_spec,
        }
        return exports[name]
    raise AttributeError(name)
