from __future__ import annotations

from pathlib import Path

import yaml

from vfoundation.core.protocol import Op


def test_parse_all_dictionary_yaml_files() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    yaml_roots = [
        repo_root / "vfoundation" / "dictionaries",
        repo_root / "apps" / "reference" / "dictionaries",
    ]

    yaml_files: list[Path] = []
    for root in yaml_roots:
        if root.exists():
            yaml_files.extend(sorted(root.rglob("*.yaml")))

    assert yaml_files, "No dictionary YAML files found to parse"

    bad: list[str] = []
    for path in yaml_files:
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            bad.append(f"{path.relative_to(repo_root)}: {type(e).__name__}: {e}")

    assert not bad, "Some dictionary YAML files failed to parse:\n" + "\n".join(bad)


def test_global_dictionary_invariants_ops_and_ttl_profiles() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    # Prefer framework dictionary if present; it's the strictest baseline.
    candidates = [
        repo_root / "vfoundation" / "dictionaries" / "global_v2_2_framework.yaml",
        repo_root / "vfoundation" / "dictionaries" / "global_v2_2.yaml",
        repo_root / "apps" / "reference" / "dictionaries" / "global_v2_2.yaml",
    ]

    data = None
    used = None
    for path in candidates:
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            used = path
            break

    assert isinstance(data, dict) and used is not None, "No global dictionary YAML found"

    ops = data.get("ops")
    assert isinstance(ops, list) and all(isinstance(x, str) for x in ops), f"{used}: ops must be a list[str]"

    # Invariant: dictionary ops should cover the protocol allowlist.
    op_allowlist = set(Op.__args__)  # type: ignore[attr-defined]
    missing = sorted(op_allowlist - set(ops))
    assert not missing, f"{used}: ops missing protocol allowlist entries: {missing}"

    ttl_profiles = data.get("ttl_profiles")
    assert isinstance(ttl_profiles, dict), f"{used}: ttl_profiles must be a mapping"

    bad_ttl: list[str] = []
    for name, ttl in ttl_profiles.items():
        if not isinstance(name, str):
            bad_ttl.append(f"{name!r}=<bad key>")
            continue
        if not isinstance(ttl, int):
            bad_ttl.append(f"{name}={ttl!r}")
            continue
        if ttl < 1 or ttl > 30000:
            bad_ttl.append(f"{name}={ttl}")

    assert not bad_ttl, f"{used}: ttl_profiles out of range (1..30000) or invalid: {bad_ttl}"
