from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import yaml

from vfoundation.core.protocol import Op


def test_all_vfoundation_dictionary_yaml_parse() -> None:
    base = Path("vfoundation/dictionaries")
    assert base.exists(), "vfoundation/dictionaries directory missing"

    yaml_paths = sorted(base.rglob("*.yaml"))
    assert yaml_paths, "No vfoundation dictionary YAML files found"

    for path in yaml_paths:
        text = path.read_text(encoding="utf-8")
        try:
            obj = yaml.safe_load(text)
        except Exception as e:  # pragma: no cover
            raise AssertionError(f"YAML failed to parse: {path}: {type(e).__name__}: {e}") from e
        assert obj is not None, f"YAML parsed to None: {path}"


def test_all_domain_dict_json_valid() -> None:
    base = Path("apps/reference")
    assert base.exists(), "apps/reference directory missing"

    json_paths = sorted(base.rglob("domain_dict.json"))
    assert json_paths, "No apps/reference/**/domain_dict.json files found"

    for path in json_paths:
        text = path.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except Exception as e:  # pragma: no cover
            raise AssertionError(f"JSON failed to parse: {path}: {type(e).__name__}: {e}") from e
        assert isinstance(obj, dict), f"domain_dict.json must be object: {path}"


def test_global_dictionary_ops_matches_message_op_allowlist() -> None:
    allowed_ops = set(get_args(Op))

    # Treat all global_v2_2*.yaml as global dictionaries and ensure they agree with Message.Op
    global_paths = [
        Path("vfoundation/dictionaries/global_v2_2.yaml"),
        Path("vfoundation/dictionaries/global_v2_2_framework.yaml"),
        Path("apps/reference/dictionaries/global_v2_2.yaml"),
    ]

    for path in global_paths:
        assert path.exists(), f"Missing global dictionary: {path}"
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(obj, dict), f"Global dictionary must be YAML mapping: {path}"
        ops = obj.get("ops")
        assert isinstance(ops, list) and ops, f"Global dictionary missing ops list: {path}"
        assert set(ops) == allowed_ops, f"ops mismatch for {path}: {set(ops)} != {allowed_ops}"
