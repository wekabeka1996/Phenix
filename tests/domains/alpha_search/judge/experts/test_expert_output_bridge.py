"""
LLM Judge expert output bridge tests.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from apps.reference.domains.alpha_search.alpha_model import AlphaScore
from apps.reference.domains.alpha_search.judge.experts.expert_output_bridge import (
    alpha_score_to_expert_output,
    write_jsonl_shadow_log,
)

SIGNAL_THRESHOLD = 0.162


def _make_alpha_score(**overrides: object) -> AlphaScore:
    defaults = dict(
        model_name="judge.signal_weights_v1",
        symbol="BTCUSDT",
        score=Decimal("0.35"),
        confidence=Decimal("0.35"),
        features_used=["obi", "tfi"],
        why=["score=0.35 > threshold -> OPEN_LONG", "obi: w=0.42 c=0.50"],
    )
    defaults.update(overrides)
    return AlphaScore(**defaults)


class TestAlphaScoreToExpertOutput:
    def test_positive_score_above_threshold_open_long(self) -> None:
        score = _make_alpha_score(score=Decimal("0.30"), confidence=Decimal("0.30"))
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.entry_verdict == "OPEN_LONG"
        assert eo.signal_direction == "LONG"
        assert eo.lifecycle_verdict is None
        assert eo.reasoning[0].startswith("authoritative_entry_verdict:OPEN_LONG")

    def test_negative_score_above_threshold_open_short(self) -> None:
        score = _make_alpha_score(
            score=Decimal("-0.40"),
            confidence=Decimal("0.40"),
            why=["score=-0.4 -> OPEN_SHORT", "delta_price: bearish"],
        )
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.entry_verdict == "OPEN_SHORT"
        assert eo.signal_direction == "SHORT"

    def test_zero_score_no_entry(self) -> None:
        score = _make_alpha_score(
            score=Decimal("0"),
            confidence=Decimal("0.5"),
            why=["score=0 -> NO_ENTRY", "regime: mixed"],
        )
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.entry_verdict == "NO_ENTRY"
        assert eo.signal_direction == "NEUTRAL"

    def test_below_threshold_nonzero_score_maps_to_no_entry(self) -> None:
        score = _make_alpha_score(
            score=Decimal("0.10"),
            confidence=Decimal("0.10"),
            why=[
                "|score|=0.1000 <= threshold=0.162 -> NO_ENTRY",
                "obi: contribution=0.10",
            ],
        )
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.entry_verdict == "NO_ENTRY"
        assert eo.signal_direction == "NEUTRAL"
        assert eo.reasoning[0].startswith("authoritative_entry_verdict:NO_ENTRY")
        assert "obi: contribution=0.10" in eo.reasoning

    def test_deferred_unknown(self) -> None:
        score = _make_alpha_score(
            score=Decimal("0"),
            confidence=Decimal("0"),
            why=["DEFER:obi"],
            features_used=[],
        )
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.entry_verdict == "UNKNOWN"
        assert eo.signal_direction == "NEUTRAL"
        assert "DEFER:obi" in eo.reasoning

    def test_nrr_unknown(self) -> None:
        score = _make_alpha_score(
            score=Decimal("0"),
            confidence=Decimal("0"),
            why=["NRR-NO-FEATURES"],
            features_used=[],
        )
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.entry_verdict == "UNKNOWN"

    def test_reasoning_preserves_non_decision_lines_only(self) -> None:
        score = _make_alpha_score(
            why=[
                "|final|=0.3500 > threshold=0.162 -> OPEN_LONG",
                "obi: w=0.42 c=0.50",
                "delta_price: w=0.15 c=0.20",
            ]
        )
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.reasoning == [
            "authoritative_entry_verdict:OPEN_LONG score=0.3500 threshold=0.1620 confidence=0.3500",
            "obi: w=0.42 c=0.50",
            "delta_price: w=0.15 c=0.20",
        ]

    def test_contradictory_decision_text_is_removed(self) -> None:
        score = _make_alpha_score(
            score=Decimal("0.35"),
            confidence=Decimal("0.35"),
            why=[
                "|final|=0.0142 <= threshold=0.162 -> NO_ENTRY",
                "obi: w=0.42 c=0.50",
            ],
        )
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.entry_verdict == "OPEN_LONG"
        assert eo.reasoning[0].startswith("authoritative_entry_verdict:OPEN_LONG")
        assert all("NO_ENTRY" not in line for line in eo.reasoning)
        assert "obi: w=0.42 c=0.50" in eo.reasoning

    def test_confidence_preserved(self) -> None:
        score = _make_alpha_score(confidence=Decimal("0.75"))
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.confidence == 0.75

    def test_expert_id_and_cycle_key_propagated(self) -> None:
        score = _make_alpha_score(model_name="judge.feature_neutrals_v1")
        eo = alpha_score_to_expert_output(
            score,
            expert_version="2.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=60,
            ts_ms=1712000000000,
        )
        assert eo.expert_id == "judge.feature_neutrals_v1"
        assert eo.expert_version == "2.0.0"
        assert eo.tf_sec == 60
        assert eo.cycle_key == "ENTRY:BTCUSDT:60:1712000000000"

    def test_schema_version_is_1(self) -> None:
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
        )
        assert eo.schema_version == "1"

    def test_ts_ms_override(self) -> None:
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
            ts_ms=1712000000000,
        )
        assert eo.ts_ms == 1712000000000


class TestJSONLShadowLog:
    def test_write_creates_file_and_serializes_cycle_key(self) -> None:
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
            ts_ms=1712000000000,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            write_jsonl_shadow_log(eo, tmpdir)
            files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(files) == 1
            data = json.loads(files[0].read_text(encoding="utf-8").strip())
            assert data["expert_id"] == "judge.signal_weights_v1"
            assert data["symbol"] == "BTCUSDT"
            assert data["cycle_key"] == "ENTRY:BTCUSDT:300:1712000000000"

    def test_write_appends(self) -> None:
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
            ts_ms=1712000000000,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            write_jsonl_shadow_log(eo, tmpdir)
            write_jsonl_shadow_log(eo, tmpdir)
            files = list(Path(tmpdir).glob("*.jsonl"))
            assert len(files) == 1
            lines = files[0].read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2

    def test_partition_day_comes_from_ts_ms(self) -> None:
        ts_ms = 1711929600000
        score = _make_alpha_score()
        eo = alpha_score_to_expert_output(
            score,
            expert_version="1.0.0",
            signal_threshold=SIGNAL_THRESHOLD,
            tf_sec=300,
            ts_ms=ts_ms,
        )
        expected_day = datetime.fromtimestamp(
            ts_ms / 1000,
            tz=timezone.utc,
        ).strftime("%Y-%m-%d")
        with tempfile.TemporaryDirectory() as tmpdir:
            write_jsonl_shadow_log(eo, tmpdir)
            assert (Path(tmpdir) / f"judge.signal_weights_v1_BTCUSDT_{expected_day}.jsonl").is_file()
