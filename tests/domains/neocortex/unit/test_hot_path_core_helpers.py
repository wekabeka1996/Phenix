from __future__ import annotations

from dataclasses import FrozenInstanceError
from collections.abc import Mapping
import builtins
import importlib
import sys

import numpy as np
import pytest

from apps.reference.domains.neocortex.contracts.causal_time import (
    CausalTimeDecision,
    CausalTimeProvenance,
    NON_CAUSAL_REASON_CODE,
    get_non_causal_counter,
    make_causal_decision,
    reset_non_causal_counter,
)
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcome,
    FailureOutcomeTaxonomy,
    FailureReasonCode,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    coerce_causal_time_provenance,
    is_causal_time_provenance,
)
from apps.reference.domains.neocortex.logic.failure_ledger import FailureLedger
from apps.reference.domains.neocortex.logic.ingest import observation as observation_mod
from apps.reference.domains.neocortex.logic.ingest.observation import MarketObservation


def test_coerce_causal_time_provenance_handles_instance_and_blank_string() -> None:
    assert (
        coerce_causal_time_provenance(CausalTimeProvenance.AURORA_EVENT)
        is CausalTimeProvenance.AURORA_EVENT
    )
    assert coerce_causal_time_provenance("   ") is CausalTimeProvenance.UNKNOWN
    assert is_causal_time_provenance(CausalTimeProvenance.AURORA_EVENT) is True
    assert is_causal_time_provenance(
        CausalTimeProvenance.CAPTURED_WALLCLOCK) is False


@pytest.mark.parametrize(
    ("event_time_is_causal", "trainable", "dataset_visibility"),
    [
        (True, False, "trainable"),
        (True, True, "diagnostics_only"),
        (False, True, "diagnostics_only"),
        (False, False, "trainable"),
    ],
)
def test_causal_time_decision_invariants_raise(
    event_time_is_causal: bool,
    trainable: bool,
    dataset_visibility: str,
) -> None:
    with pytest.raises(ValueError):
        CausalTimeDecision(
            event_ts_ms=1,
            event_time_source=CausalTimeProvenance.AURORA_EVENT,
            event_time_is_causal=event_time_is_causal,
            trainable=trainable,
            dataset_visibility=dataset_visibility,  # type: ignore[arg-type]
            reason_code=None if event_time_is_causal else NON_CAUSAL_REASON_CODE,
        )


def test_make_causal_decision_tracks_non_causal_counter() -> None:
    reset_non_causal_counter()
    causal = make_causal_decision(
        1_700_000_000_000, CausalTimeProvenance.AURORA_EVENT)
    assert causal.event_time_is_causal is True
    assert causal.reason_code is None

    non_causal = make_causal_decision(
        1_700_000_000_000,
        CausalTimeProvenance.CAPTURED_WALLCLOCK,
    )
    assert non_causal.event_time_is_causal is False
    assert non_causal.reason_code == NON_CAUSAL_REASON_CODE
    assert get_non_causal_counter() == 1


def test_failure_ledger_records_counts_and_reset() -> None:
    ledger = FailureLedger()
    outcome = FailureOutcome(
        taxonomy=FailureOutcomeTaxonomy.FALLBACK,
        reason_code=FailureReasonCode.HANDLER_FAILURE,
        source="tests",
        message="boom",
        recoverable=False,
        fallback_applied=True,
    )

    ledger.record_failure(outcome)
    counts = ledger.get_failure_counts()
    assert counts[(FailureOutcomeTaxonomy.FALLBACK,
                   FailureReasonCode.HANDLER_FAILURE)] == 1
    assert ledger.get_total_count() == 1

    ledger.reset_failure_counts()
    assert ledger.get_failure_counts() == {}
    assert ledger.get_total_count() == 0


def test_market_observation_requires_float32_and_can_fail_closed_without_torch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="float32"):
        MarketObservation(
            ts=1.0,
            mid_price=100.0,
            volatility=0.5,
            obi=0.1,
            features_vector=np.asarray([1.0, 2.0], dtype=np.float64),
        )

    monkeypatch.setattr(observation_mod, "HAS_TORCH", False)
    obs = MarketObservation(
        ts=1.0,
        mid_price=100.0,
        volatility=0.5,
        obi=0.1,
        features_vector=np.asarray([1.0, 2.0], dtype=np.float32),
        normalized=True,
    )
    assert "normalized=True" in repr(obs)
    with pytest.raises(ImportError, match="PyTorch not installed"):
        obs.to_tensor()


def test_market_observation_to_tensor_success_and_import_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeTensor:
        def __init__(self, array: np.ndarray) -> None:
            self.array = array
            self.devices: list[str] = []

        def to(self, device: str) -> "_FakeTensor":
            self.devices.append(device)
            return self

        def unsqueeze(self, dim: int) -> tuple[int, tuple[float, ...]]:
            return dim, tuple(float(value) for value in self.array.tolist())

    class _FakeTorch:
        def from_numpy(self, array: np.ndarray) -> _FakeTensor:
            return _FakeTensor(array)

    monkeypatch.setattr(observation_mod, "HAS_TORCH", True)
    monkeypatch.setattr(observation_mod, "torch", _FakeTorch())
    obs = MarketObservation(
        ts=1.0,
        mid_price=100.0,
        volatility=0.5,
        obi=0.1,
        features_vector=np.asarray([1.0, 2.0], dtype=np.float32),
    )
    assert obs.to_tensor("cuda") == (0, (1.0, 2.0))

    fake_torch_module = _FakeTorch()
    monkeypatch.setitem(sys.modules, "torch", fake_torch_module)
    reloaded = importlib.reload(observation_mod)
    assert reloaded.HAS_TORCH is True
    assert reloaded.torch is fake_torch_module

    original_import = builtins.__import__

    def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "torch":
            raise ImportError("torch blocked for test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr(builtins, "__import__", _blocked_import)
    reloaded = importlib.reload(observation_mod)
    assert reloaded.HAS_TORCH is False

    monkeypatch.setattr(builtins, "__import__", original_import)
    importlib.reload(observation_mod)
