"""
Resilience tests for PPO / PyTorch optionality.

Goal: BrainCore should not crash if torch is missing; it should degrade gracefully.
"""

from unittest.mock import MagicMock

import pytest



def test_braincore_no_torch_does_not_crash(monkeypatch):
    from apps.reference.domains.neocortex.logic.brain import core

    # Simulate no-torch mode without monkeypatching global import machinery.
    monkeypatch.setattr(core, "HAS_TORCH", False, raising=False)
    monkeypatch.setattr(core, "HAS_PPO", False, raising=False)

    # BrainCore should initialize even without torch (mock mode).
    cfg = MagicMock()
    brain = core.BrainCore(cfg)
    assert brain is not None

    # PPO training should not crash, should no-op.
    assert brain.train_ppo([]) == {}


