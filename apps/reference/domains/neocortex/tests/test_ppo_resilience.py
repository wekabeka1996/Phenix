"""
Resilience tests for PPO / PyTorch optionality.

Goal: BrainCore should not crash if torch is missing; it should degrade gracefully.
"""

from pathlib import Path
from unittest.mock import MagicMock
import builtins
import importlib
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_braincore_no_torch_does_not_crash(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "torch" or name.startswith("torch."):
            raise ModuleNotFoundError("No module named 'torch'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    for mod in list(sys.modules.keys()):
        if mod == "torch" or mod.startswith("torch.") or mod.startswith("logic.brain"):
            sys.modules.pop(mod, None)

    import logic.brain.core as core

    importlib.reload(core)

    # BrainCore should initialize even without torch (mock mode).
    cfg = MagicMock()
    brain = core.BrainCore(cfg)
    assert brain is not None

    # PPO training should not crash, should no-op.
    assert brain.train_ppo([]) == {}

