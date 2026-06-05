from pathlib import Path

from apps.reference.domains.neocortex.config_models import load_config
from apps.reference.domains.neocortex.logic.evaluation import ShadowDisagreementSample, ShadowOfflineEvaluator


def _config():
    return load_config(Path("apps/reference/domains/neocortex/config"))


def test_disagreement_report_is_deterministic_and_bucketed():
    config = _config()
    evaluator = ShadowOfflineEvaluator(config.neuro.evaluation)
    comparisons = [
        ShadowDisagreementSample(
            comparison_id="cmp-1",
            event_ts_ms=1_700_000_000_100,
            symbol="BTCUSDT",
            shadow_action="LONG",
            aurora_action="SHORT",
            shadow_confidence=0.92,
            regime="trend_up",
            severity="high",
            comparison_status="comparable",
        ),
        ShadowDisagreementSample(
            comparison_id="cmp-2",
            event_ts_ms=1_700_000_000_200,
            symbol="ETHUSDT",
            shadow_action="FLAT",
            aurora_action="LONG",
            shadow_confidence=0.41,
            regime="mean_reversion",
            severity="low",
            comparison_status="comparable",
        ),
        ShadowDisagreementSample(
            comparison_id="cmp-3",
            event_ts_ms=1_700_000_000_300,
            symbol="BTCUSDT",
            shadow_action="LONG",
            aurora_action="LONG",
            shadow_confidence=0.88,
            regime="trend_up",
            severity="high",
            comparison_status="comparable",
        ),
        ShadowDisagreementSample(
            comparison_id="cmp-4",
            event_ts_ms=1_700_000_000_400,
            symbol="SOLUSDT",
            shadow_action="SHORT",
            aurora_action=None,
            shadow_confidence=None,
            regime=None,
            severity=None,
            comparison_status="unresolved",
        ),
    ]

    first = evaluator.evaluate_disagreement(
        comparisons,
        evaluated_at_ms=1_700_000_100_000,
    )
    second = evaluator.evaluate_disagreement(
        comparisons,
        evaluated_at_ms=1_700_000_100_000,
    )

    assert first.model_dump(mode="python") == second.model_dump(mode="python")
    assert first.total_compared == 3
    assert first.disagreement_count == 2
    assert first.disagreement_rate == 2 / 3
    assert first.by_symbol == {"BTCUSDT": 1, "ETHUSDT": 1}
    assert first.by_regime == {"mean_reversion": 1, "trend_up": 1}
    assert first.severity_buckets == {"high": 1, "low": 1}
    assert first.unresolved_comparison_count == 1
    assert sum(first.by_confidence_bucket.values()) == 2
