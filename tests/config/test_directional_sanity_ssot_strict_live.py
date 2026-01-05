import shutil

import pytest


def test_live_config_fails_if_directional_sanity_missing(tmp_path):
    """DM-DIR-SSOT-STRICT-01: No silent defaults in LIVE.

    If domains.decision_making.directional_sanity is missing, live config validation must fail.
    """
    from apps.reference.config_loader import ConfigLoader

    src = tmp_path / "cfg"
    shutil.copytree("config/aurora", src)
    domains_yaml = src / "domains.yaml"

    import yaml

    data = yaml.safe_load(domains_yaml.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "decision_making" in data

    dm = data.get("decision_making")
    assert isinstance(dm, dict)
    assert "directional_sanity" in dm, "Test precondition: SSOT block must exist before deletion"

    del dm["directional_sanity"]
    domains_yaml.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match=r"directional_sanity"):
        ConfigLoader(config_dir=src).load_config(is_live_execution=True)
