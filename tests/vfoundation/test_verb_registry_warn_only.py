from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import yaml


RUNTIME_TOKEN_RE = re.compile(r"\b(?:EVT|CMD|DEC|ASK|UPD|ERR):[A-Za-z0-9_\-*]+\b")


def _scan_runtime_tokens(repo_root: Path) -> set[str]:
    tokens: set[str] = set()

    scan_roots = [
        repo_root / "apps",
        repo_root / "vfoundation",
        repo_root / "bridge",
        repo_root / "alysha_core",
    ]

    for root in scan_roots:
        if not root.exists():
            continue

        for path in root.rglob("*.py"):
            if ".venv" in path.parts:
                continue
            if "tests" in path.parts:
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8", errors="ignore")

            for m in RUNTIME_TOKEN_RE.finditer(text):
                tokens.add(m.group(0))

    return tokens


def _load_registry_tokens(registry_path: Path) -> set[str]:
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError("verb registry: expected top-level 'registry' list")

    tokens: set[str] = set()
    for entry in registry:
        if not isinstance(entry, dict):
            raise AssertionError("verb registry: registry entry must be mapping")
        op = entry.get("op")
        verb = entry.get("verb")
        if not isinstance(op, str) or not isinstance(verb, str):
            raise AssertionError("verb registry: each entry must have string 'op' and 'verb'")
        tokens.add(f"{op}:{verb}")

    return tokens


def test_verb_registry_covers_runtime_warn_only() -> None:
    """Warn-only drift detector.

    - If runtime has tokens missing in registry -> do NOT fail (yet).
    - If registry is missing/unparseable -> FAIL (toolchain broken).

    Always writes a report to reports/ so drift is visible in CI logs.
    """

    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "apps" / "reference" / "dictionaries" / "verb_registry_v1.yaml"
    if not registry_path.exists():
        raise AssertionError(f"Missing registry file: {registry_path}")

    runtime_tokens = sorted(_scan_runtime_tokens(repo_root))
    registry_tokens = sorted(_load_registry_tokens(registry_path))

    runtime_set = set(runtime_tokens)
    registry_set = set(registry_tokens)

    runtime_not_in_registry = sorted(runtime_set - registry_set)
    registry_not_in_runtime = sorted(registry_set - runtime_set)

    coverage = (len(runtime_set & registry_set) / len(runtime_set)) if runtime_set else 1.0

    today = date(2026, 1, 8).isoformat()

    payload = {
        "date": today,
        "registry_path": str(registry_path.relative_to(repo_root)),
        "counts": {
            "runtime_tokens": len(runtime_tokens),
            "registry_tokens": len(registry_tokens),
            "runtime_not_in_registry": len(runtime_not_in_registry),
            "registry_not_in_runtime": len(registry_not_in_runtime),
            "coverage": round(coverage, 6),
        },
        "runtime_not_in_registry": runtime_not_in_registry,
        "registry_not_in_runtime": registry_not_in_runtime,
    }

    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)

    diff_json_path = reports_dir / "VF-VERB-REG-02_diff.json"
    diff_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md_path = reports_dir / "VF-VERB-REG-02.md"
    md_path.write_text(
        "# VF-VERB-REG-02 — Registry coverage vs runtime (warn-only)\n"
        f"Дата: {today}\n\n"
        "## Итоги\n"
        f"- runtime tokens (без tests): **{payload['counts']['runtime_tokens']}**\n"
        f"- registry tokens: **{payload['counts']['registry_tokens']}**\n"
        f"- runtime_not_in_registry: **{payload['counts']['runtime_not_in_registry']}**\n"
        f"- registry_not_in_runtime: **{payload['counts']['registry_not_in_runtime']}**\n\n"
        "## Артефакты\n"
        "- `reports/VF-VERB-REG-02_diff.json`\n\n"
        "## Режим\n"
        "- Warn-only: тест не падает при `runtime_not_in_registry > 0`, но печатает репорт в stdout.\n",
        encoding="utf-8",
    )

    if runtime_not_in_registry:
        print("\n[WARN] Verb registry does NOT cover runtime tokens yet")
        print(f"coverage={coverage:.3%} missing={len(runtime_not_in_registry)}")
        for token in runtime_not_in_registry[:30]:
            print(f"- {token}")
        print(f"Full diff: {diff_json_path}")

    # VF-VERB-REG-05: start failing only after registry is essentially complete.
    threshold = 0.98
    if coverage >= threshold and runtime_not_in_registry:
        raise AssertionError(
            "Verb registry coverage gate failed: coverage>=98% but runtime has tokens missing in registry. "
            f"coverage={coverage:.3%} missing={len(runtime_not_in_registry)}. "
            f"See {diff_json_path}"
        )
