from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from apps.reference.domains.neocortex.contracts.observation_envelope import ObservationEnvelope


class AuthorityMode(str, Enum):
    SHADOW = "shadow"
    ADVISORY = "advisory"
    GATED = "gated"


class ControlDecisionRequestKind(str, Enum):
    NEW_RISK_INTENT = "new_risk_intent"


class ControlDecisionAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    BLOCK = "deny"
    MODULATE = "modulate"
    FALLBACK = "fallback"


class ControlDecisionApplyResult(str, Enum):
    TRUST_DISABLED_FASTPATH = "TRUST_DISABLED_FASTPATH"
    SHADOW_RECORDED = "SHADOW_RECORDED"
    ADVISORY_RECORDED = "ADVISORY_RECORDED"
    GATED_ALLOW = "GATED_ALLOW"
    GATED_DENY = "GATED_DENY"
    GATED_MODULATE_RECORDED = "GATED_MODULATE_RECORDED"
    FALLBACK_BASELINE = "FALLBACK_BASELINE"
    LATE_IGNORED = "LATE_IGNORED"


class ControlDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(min_length=1)
    rid: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    request_kind: ControlDecisionRequestKind = ControlDecisionRequestKind.NEW_RISK_INTENT
    authority_mode: AuthorityMode
    decision_basis_ts_ms: int = Field(ge=1)
    deadline_ms: int = Field(ge=1)
    expires_at_ms: int = Field(ge=1)
    observation: ObservationEnvelope
    candidate_intent_summary: dict[str, object] = Field(default_factory=dict)
    idempotent_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "ControlDecisionRequest":
        if self.idempotent_key != self.decision_id:
            raise ValueError("idempotent_key must equal decision_id")
        if self.expires_at_ms != self.decision_basis_ts_ms + self.deadline_ms:
            raise ValueError(
                "expires_at_ms must equal decision_basis_ts_ms + deadline_ms"
            )
        return self


class ControlDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(min_length=1)
    action: ControlDecisionAction
    reason_code: str = Field(min_length=1)
    reason_text: str = Field(min_length=1)
    returned_at_ms: int = Field(ge=1)
    model_ref: str = Field(min_length=1)
    policy_ref: str = Field(min_length=1)
    idempotent_key: str = Field(min_length=1)
    overlay_patch: dict[str, object] | None = None
    apply_result: ControlDecisionApplyResult | None = None

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "block":
                return "deny"
            return lowered
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "ControlDecisionResponse":
        if self.idempotent_key != self.decision_id:
            raise ValueError("idempotent_key must echo decision_id")
        if self.action == ControlDecisionAction.MODULATE and not self.overlay_patch:
            raise ValueError("overlay_patch is required when action=modulate")
        if self.action != ControlDecisionAction.MODULATE and self.overlay_patch is not None:
            raise ValueError(
                "overlay_patch is only valid when action=modulate")
        return self


__all__ = [
    "AuthorityMode",
    "ControlDecisionRequestKind",
    "ControlDecisionAction",
    "ControlDecisionApplyResult",
    "ControlDecisionRequest",
    "ControlDecisionResponse",
]
