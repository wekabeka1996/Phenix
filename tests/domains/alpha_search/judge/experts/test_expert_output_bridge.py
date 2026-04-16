"""
LLM Judge Phase 2 — Expert Output Bridge Tests

Tests AlphaScore → ExpertOutput translation, verdict mapping, confidence
handling, and JSONL shadow log writer.
"""

import json
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from apps.reference.domains.alpha_search.alpha_model import AlphaScore
from apps.reference.domains.alpha_search.judge.experts.expert_output_bridge import (
    alpha_score_to_expert_output,
    write_jsonl_shadow_log,
)


def _make_alpha_score(**overrides):
    defaults = dict(
        model_name="judge.signal_weights_v1",
        symbol="BTCUSDT",
        score=Decimal("0.35"),
        confidence=Decimal("0.35"),
        features_used=["obi", "tfi"],
        why=["score=0.35 > threshold → OPEN_LONG", "obi: w=0.42 c=0.50"],
    )
    defaults.update(overrides)
    return AlphaScore(**defaults)


class TestAlphaScoreToExpertOutput:
    def test_positive_score_open_long(self):
        score = _make_alpha_score(score=Decimal("0.3"), confidence=Decimal("0.3"))
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.entry_verdict == "OPEN_LONG"
        assert eo.signal_direction == "LONG"
        assert eo.lifecycle_verdict is None

    def test_negative_score_open_short(self):
        score = _make_alpha_score(
            score=Decimal("-0.4"), confidence=Decimal("0.4"),
            why=["score=-0.4 → OPEN_SHORT"],
        )
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.entry_verdict == "OPEN_SHORT"
        assert eo.signal_direction == "SHORT"

    def test_zero_score_no_entry(self):
        score = _make_alpha_score(
            score=Decimal("0"), confidence=Decimal("0.5"),
            why=["score=0 → NO_ENTRY"],
        )
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.entry_verdict == "NO_ENTRY"
        assert eo.signal_direction == "NEUTRAL"

    def test_deferred_unknown(self):
        score = _make_alpha_score(
            score=Decimal("0"), confidence=Decimal("0"),
            why=["DEFER:obi"],
            features_used=[],
        )
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.entry_verdict == "UNKNOWN"
        assert eo.signal_direction == "NEUTRAL"

    def test_nrr_unknown(self):
        score = _make_alpha_score(
            score=Decimal("0"), confidence=Decimal("0"),
            why=["NRR-NO-FEATURES"],
            features_used=[],
        )
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.entry_verdict == "UNKNOWN"

    def test_confidence_preserved(self):
        score = _make_alpha_score(confidence=Decimal("0.75"))
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.confidence == 0.75

    def test_expert_id_propagated(self):
        score = _make_alpha_score(model_name="judge.feature_neutrals_v1")
        eo = alpha_score_to_expert_output(score, expert_version="2.0.0", tf_sec=60)
        assert eo.expert_id == "judge.feature_neutrals_v1"
        assert eo.expert_version == "2.0.0"
        assert eo.tf_sec == 60

    def test_reasoning_preserved(self):
        score = _make_alpha_score(why=["reason1", "reason2"])
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.reasoning == ["reason1", "reason2"]

    def test_schema_version_is_1(self):
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(score, expert_version="1.0.0", tf_sec=300)
        assert eo.schema_version == "1"

    def test_ts_ms_override(self):
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score, expert_version="1.0.0", tf_sec=300, ts_ms=1712000000000
        )
        assert eo.ts_ms == 1712000000000


class TestJSONLShadowLog:
    def test_write_creates_file(self):
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score, expert_version="1.0.0", tf_sec=300, ts_ms=1712000000000
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            write_jsonl_shadow_log(eo, tmpdir)
            files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(files) == 1
            content = files[0].read_text()
            data = json.loads(content.strip())
            assert data["expert_id"] == "judge.signal_weights_v1"
            assert data["symbol"] == "BTCUSDT"

    def test_write_appends(self):
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score, expert_version="1.0.0", tf_sec=300, ts_ms=1712000000000
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            write_jsonl_shadow_log(eo, tmpdir)
            write_jsonl_shadow_log(eo, tmpdir)
            files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(files) == 1
            lines = files[0].read_text().strip().split("\n")
            assert len(lines) == 2
