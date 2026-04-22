import ast

with open('package6a_extracted_mapped.txt', 'r') as f:
    methods = f.read()

# Fix self._fsm -> self. for writer states
methods = methods.replace('self._fsm._restore_artifact_writer', 'self._restore_artifact_writer')
methods = methods.replace('self._fsm._startup_truth_artifact_writer', 'self._startup_truth_artifact_writer')
methods = methods.replace('self._fsm._restore_artifact_loop_started', 'self._restore_artifact_loop_started')
methods = methods.replace('self._fsm._append_bracket_ownership_record', 'self._fsm._bracket_ownership.append_bracket_ownership_record') # Oh wait, this isn't in 6a maybe? Just a precaution.

methods = methods.replace('self._fsm._manage_state_value', 'self._fsm._manage_state_value')
methods = methods.replace('self._fsm._close_state_value', 'self._fsm._close_state_value')
methods = methods.replace('self._fsm._manage_truth_source_for', 'self._fsm._manage_truth_source_for')

prefix = """import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

from apps.reference.core.time import get_clock
from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
)
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.fsm_close import CloseState
from apps.reference.domains.execution_position.restore_artifact import (
    ExecutionPositionRestoreArtifactWriter,
    ExecutionPositionRestoreArtifactDarkReader,
    ExecutionPositionRestoreLifecycleRecord,
    ExecutionPositionRestoreAuthoritativeStatus,
    ExecutionPositionRestoreAuthoritativeSymbolStatus,
    ExecutionPositionRestoreDarkReadStatus,
    ExecutionPositionRestoreDarkReadMismatchCounts,
    ExecutionPositionRestoreDarkReadMismatch,
    ExecutionPositionStartupTruthArtifactWriter,
    ExecutionPositionStartupTruthRecord,
    ExecutionPositionStartupTruthSymbolRecord,
    ExecutionPositionStartupTruthUnknownSymbolRecord,
    ExecutionPositionStartupTruthSummary,
    ExecutionPositionStartupTruthCacheStatus,
    ExecutionPositionStartupTruthRestoreArtifactStatus,
    ExecutionPositionStartupTruthInputSnapshot,
)

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(__name__)

RESTORE_PHASE_UNKNOWN = "UNKNOWN"
BRACKET_STATE_UNKNOWN = "UNKNOWN"
BRACKET_STATE_DEFERRED_PENDING_WAL = "DEFERRED_PENDING_WAL"
STARTUP_TRUTH_ARTIFACT_WRITER_COMPONENT = "execution_position"


class StartupTruthOrchestrator:
    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm
        self._restore_artifact_writer = self._create_restore_artifact_writer()
        self._startup_truth_artifact_writer = self._create_startup_truth_artifact_writer()
        self._restore_artifact_loop_started: bool = False

"""

with open('apps/reference/domains/execution_position/startup_truth_orchestrator.py', 'w') as f:
    f.write(prefix + methods)
