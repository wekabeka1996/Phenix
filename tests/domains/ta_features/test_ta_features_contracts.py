from __future__ import annotations

import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TA_DIR = PROJECT_ROOT / "apps" / "reference" / "domains" / "ta_features"
REGISTRY_PATH = PROJECT_ROOT / "apps" / "reference" / \
    "dictionaries" / "verb_registry_v1.yaml"
DOMAINS_YAML = PROJECT_ROOT / "config" / "aurora" / "domains.yaml"
RETIRED_CONFIG = PROJECT_ROOT / "config" / "ta_features.yaml"


def _load_registry() -> list[dict]:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data


class TestTAFeaturesContracts:
    def test_domains_yaml_declares_ta_features_block(self):
        data = yaml.safe_load(DOMAINS_YAML.read_text(encoding="utf-8"))
        ta_features = data.get("ta_features")
        assert isinstance(ta_features, dict)
        assert ta_features["enabled"] is True
        assert ta_features["timeframes_sec"] == [180, 300, 900]
        assert ta_features["warm_up_bars"] == 20
        assert ta_features["buffer_max_bars"] >= ta_features["warm_up_bars"]

    def test_retired_sidechannel_config_removed(self):
        assert not RETIRED_CONFIG.exists()

    def test_registry_entry_points_to_ta_schema(self):
        match = next(
            entry
            for entry in _load_registry()
            if entry.get("op") == "EVT" and entry.get("verb") == "TA_FEATURES_CALCULATED"
        )
        assert match["owner"] == "ta_features"
        assert match["schema"] == "apps/reference/domains/ta_features/schemas/ta_features_calculated_v1.json"

    def test_schema_requires_explicit_readiness_fields(self):
        schema = json.loads(
            (TA_DIR / "schemas" /
             "ta_features_calculated_v1.json").read_text(encoding="utf-8")
        )
        required = set(schema.get("required", []))
        assert {"ts", "close", "warm_up_bars",
                "required_warm_up_bars", "is_warm"}.issubset(required)

    def test_domain_dict_declares_ssot_and_separate_event_plane(self):
        domain_dict = json.loads(
            (TA_DIR / "domain_dict.json").read_text(encoding="utf-8"))
        assert domain_dict["domain_name"] == "ta_features"
        assert "ssot_notes" in domain_dict
        assert domain_dict["ssot_notes"]["config"] == "config/aurora/domains.yaml -> config.domains.ta_features"
        assert "does not co-emit into EVT:FEATURES_CALCULATED" in domain_dict["ssot_notes"]["coexistence"]
        export_names = {entry["event_name"]
                        for entry in domain_dict.get("exports", [])}
        assert export_names == {"EVT:TA_FEATURES_CALCULATED"}
