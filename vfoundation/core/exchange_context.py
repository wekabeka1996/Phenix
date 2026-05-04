"""
ExchangeContext — Phase 14C shared exchange session context.

Encapsulates exchange target, account sub-IDs, and risk parameters
to avoid repetition in Message.pld.

Constitution v2.2 §8: message protocol must support contextual routing.
"""
from __future__ import annotations

from typing import Any, Dict
from pydantic import BaseModel, Field, ConfigDict


class ExchangeContext(BaseModel):
    """
    Shared context for exchange operations.
    Can be embedded in Message.pld under 'ctx' key or handled by adapters.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    exchange: str
    account_id: str = "default"
    is_paper: bool = False
    leverage: float = Field(default=1.0, gt=0)
    extra_meta: Dict[str, Any] = Field(default_factory=dict)
