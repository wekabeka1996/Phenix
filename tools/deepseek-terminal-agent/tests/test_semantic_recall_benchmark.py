"""Deterministic acceptance test for the P41Y semantic recall benchmark."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_semantic_recall_surfaces_are_exact_and_source_bound(tmp_path):
    script = Path(__file__).parents[1] / "scripts" / "benchmark_semantic_recall.py"
    output = tmp_path / "semantic_recall.json"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["llm_judge_used"] is False
    assert payload["compression_ratio_used_as_quality_proof"] is False
    assert payload["critical_source_reference_retention"] is True
    for score in payload["scores"].values():
        assert score["exact_factual_recall"] == 1.0
        assert score["chronology_correct"] is True
        assert score["agent_attribution"] == 1.0
        assert score["symbol_attribution"] == 1.0
        assert score["instruction_version_correct"] is True
        assert score["critical_event_recall"] == 1.0
        assert score["false_claim_count"] == 0
        assert score["missing_source_reference_count"] == 0
