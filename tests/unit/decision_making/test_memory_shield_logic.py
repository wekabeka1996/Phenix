"""
Unit tests for MemoryShield — Doctrine v2.6, S2-R1.
"""
from __future__ import annotations

import json
import os
import time
from unittest import mock

import pytest

from apps.reference.shared.decision_primitives.shields.base import ShieldResult
from apps.reference.shared.decision_primitives.shields.memory_shield import (
    MemoryShield,
)

_FULL = {
    "regime": "TREND_UP",
    "volatility": {"atr_pct": 0.003, "atr_14": 150.0, "atr_ready": True},
    "volatility_state": "0.5",
    "pillar_operator": 0.5,
    "pillar_strategist": 0.6,
    "bar_close_ts": 1_700_000_000,
}

class TestHashStability:
    def test_same_inputs_same_hash(self):
        h1, m1 = MemoryShield._get_state_hash(_FULL)
        h2, m2 = MemoryShield._get_state_hash(dict(_FULL))
        assert h1 == h2
        assert m1 == []

class TestProtocol:
    def test_returns_shield_result(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", _FULL, 0.5, 0.25)
        assert isinstance(result, ShieldResult)

    def test_missing_features_still_returns_valid(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", {}, 0.5, 0.25)
        assert isinstance(result, ShieldResult)
        assert "MISSING_FEATURES" in result.reasons[0]

    def test_missing_features_details_contains_keys(self):
        shield = MemoryShield()
        result = shield.evaluate("BTC", {}, 0.5, 0.25)
        assert "missing_keys" in result.details

class TestPureReadEvaluate:
    def test_evaluate_missing_features_no_side_effects(self):
        shield = MemoryShield()
        shield.evaluate("BTC", {}, 0.5, 0.25)
        assert shield.state_count() == 0
