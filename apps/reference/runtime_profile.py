"""Repository-owned launch profiles for the Aurora composition root."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict


RUNTIME_PROFILE_ENV = "AURORA_RUNTIME_PROFILE"
RuntimeProfileName = Literal["normal", "agent_bridge_observation_only", "deepseek_agent_only_testnet"]


class RuntimeLaunchProfile(BaseModel):
    """Typed, fail-closed process launch profile.

    This is deliberately separate from the trading mode. The observation
    profile never changes production/testnet policy; it only removes execution
    authority from the process composition.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: RuntimeProfileName

    @property
    def no_order_observation(self) -> bool:
        return self.name == "agent_bridge_observation_only"

    @property
    def deepseek_agent_only_testnet_active(self) -> bool:
        return self.name == "deepseek_agent_only_testnet"


def resolve_runtime_launch_profile(
    environ: Mapping[str, str] | None = None,
) -> RuntimeLaunchProfile:
    import os

    source = os.environ if environ is None else environ
    raw = source.get(RUNTIME_PROFILE_ENV)
    if raw is None:
        return RuntimeLaunchProfile(name="normal")
    candidate = str(raw).strip().lower()
    if not candidate:
        raise ValueError(f"{RUNTIME_PROFILE_ENV} must not be empty when set")
    try:
        return RuntimeLaunchProfile(name=candidate)  # type: ignore[arg-type]
    except Exception as exc:
        raise ValueError(
            f"Unsupported {RUNTIME_PROFILE_ENV}={candidate!r}; "
            "allowed values are 'normal', 'agent_bridge_observation_only', and 'deepseek_agent_only_testnet'"
        ) from exc
