"""
DEPRECATED: This module has been moved to tests/domains/execution_position/shadow_execpos/ab_replay.py

ab_replay.py is a TEST UTILITY, not business logic. It should not be in the domain package.

For backward compatibility, this stub re-exports from the new location.
Remove this file after all imports are updated.
"""

import warnings

warnings.warn(
    "ab_replay has been moved to tests/domains/execution_position/shadow_execpos/ab_replay.py. "
    "Update your imports.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export for backward compatibility
from tests.domains.execution_position.shadow_execpos.ab_replay import (
    AdapterCall,
    AdapterDiffReport,
    ABReplayResult,
    diff_adapter_calls,
    ExecPosReplay,
)

__all__ = [
    "AdapterCall",
    "AdapterDiffReport",
    "ABReplayResult",
    "diff_adapter_calls",
    "ExecPosReplay",
]

