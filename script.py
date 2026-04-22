import os

with open('bracket_health_methods.txt', 'r') as f:
    methods = f.read()

prefix = """import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.bracket_math import compute_bracket_targets
from apps.reference.domains.execution_position.fsm_manage import ManageState
from apps.reference.domains.execution_position.utils import (
    coerce_exchange_bool,
    generate_client_order_id,
    opposite_side,
    quantize_stop_price,
)

if TYPE_CHECKING:
    from apps.reference.domains.execution_position.fsm import ExecPosFSM

LOG = logging.getLogger(__name__)


class BracketHealth:
    def __init__(self, fsm: "ExecPosFSM") -> None:
        self._fsm = fsm
        self._bracket_health_started = False

"""

with open('apps/reference/domains/execution_position/bracket_health.py', 'w') as f:
    f.write(prefix + methods)
