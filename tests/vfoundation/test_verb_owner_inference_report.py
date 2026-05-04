from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml


TOKEN_RE = re.compile(r"\b(?:EVT|CMD|DEC|ASK|UPD|ERR):[A-Za-z0-9_\-*]+\b")


def _iter_runtime_py_files(repo_root: Path) -> list[Path]:
    scan_roots = [
        repo_root / "apps",
        repo_root / "vfoundation",
        repo_root / "bridge",
        repo_root / "alysha_core",
    ]

    files: list[Path] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if ".venv" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            files.append(path)
    return files


def _domain_from_path(repo_root: Path, file_path: Path) -> str | None:
    # owner inference is ONLY by path:
    # apps/reference/domains/<X>/...
    try:
        rel = file_path.relative_to(repo_root).as_posix()
    except ValueError:
        return None

    prefix = "apps/reference/domains/"
    if not rel.startswith(prefix):
        return None

    rest = rel[len(prefix) :]
    parts = rest.split("/", 1)
    if not parts or not parts[0]:
        return None

    return parts[0]


def _load_unknown_registry_tokens(registry_path: Path) -> list[str]:
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry = data.get("registry")
    if not isinstance(registry, list):
        raise AssertionError("verb registry: expected top-level 'registry' list")

    tokens: list[str] = []
    for entry in registry:
        if not isinstance(entry, dict):
            continue
        if entry.get("owner") != "unknown":
            continue
        op = entry.get("op")
        verb = entry.get("verb")
        if isinstance(op, str) and isinstance(verb, str):
            tokens.append(f"{op}:{verb}")

    return sorted(tokens)


def test_owner_inference_report_no_autofix() -> None:
    """VF-VERB-REG-04: доказовий heuristic report.

    - НЕ змінює registry.
    - Лише пише reports/* артефакти.
    """

    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "apps" / "reference" / "dictionaries" / "verb_registry_v1.yaml"
    if not registry_path.exists():
        raise AssertionError(f"Missing registry file: {registry_path}")

    unknown_tokens = _load_unknown_registry_tokens(registry_path)

    # One-pass scan over runtime files for evidence.
    file_counter_by_token: dict[str, Counter[str]] = defaultdict(Counter)
    domain_counter_by_token: dict[str, Counter[str]] = defaultdict(Counter)
    total_counter_by_token: Counter[str] = Counter()

    runtime_files = _iter_runtime_py_files(repo_root)
    for path in runtime_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")

        rel_path = path.relative_to(repo_root).as_posix()
        domain = _domain_from_path(repo_root, path)

        for m in TOKEN_RE.finditer(text):
            token = m.group(0)
            total_counter_by_token[token] += 1
            file_counter_by_token[token][rel_path] += 1
            if domain is not None:
                domain_counter_by_token[token][domain] += 1

    suggestions = []
    for token in unknown_tokens:
        total = total_counter_by_token.get(token, 0)
        per_file = file_counter_by_token.get(token, Counter())
        per_domain = domain_counter_by_token.get(token, Counter())

        top_files = per_file.most_common(10)
        top_domains = per_domain.most_common(3)

        suggested_owner = "unknown"
        candidates = []

        if total > 0 and top_domains:
            for dom, cnt in top_domains:
                candidates.append(
                    {
                        "owner": dom,
                        "count": cnt,
                        "pct": round((cnt / total) * 100.0, 2),
                    }
                )

            if candidates[0]["pct"] >= 70.0:
                suggested_owner = candidates[0]["owner"]

        op, verb = token.split(":", 1)
        suggestions.append(
            {
                "op": op,
                "verb": verb,
                "token": token,
                "total_occurrences": total,
                "suggested_owner": suggested_owner,
                "candidates": candidates,
                "top_files": [{"path": p, "count": c} for p, c in top_files],
            }
        )

    today = date(2026, 1, 8).isoformat()
    reports_dir = repo_root / "reports"
    reports_dir.mkdir(exist_ok=True)

    json_path = reports_dir / "VF-VERB-REG-04_owner_suggestions.json"
    payload = {
        "date": today,
        "registry_path": str(registry_path.relative_to(repo_root)),
        "unknown_tokens": len(unknown_tokens),
        "generated": len(suggestions),
        "rules": {
            "path_owner_prefix": "apps/reference/domains/<X>/",
            "threshold_pct": 70.0,
            "top_files": 10,
            "top_candidates": 3,
        },
        "suggestions": suggestions,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md_path = reports_dir / "VF-VERB-REG-04.md"
    lines: list[str] = []
    lines.append("# VF-VERB-REG-04 — Owner inference report (heuristic, evidence-based)")
    lines.append(f"Дата: {today}")
    lines.append("")
    lines.append("## Правила")
    lines.append("- Owner визначається лише по шляху файлів.")
    lines.append("- Якщо ≥70% входжень токена знаходяться в `apps/reference/domains/<X>/`, то suggested_owner = `<X>`. ")
    lines.append("- Інакше suggested_owner лишається `unknown`, але показуються top-3 кандидати з %.")
    lines.append("")
    lines.append("## Сводка")
    lines.append(f"- unknown tokens in registry: **{len(unknown_tokens)}**")
    lines.append(f"- report rows: **{len(suggestions)}**")
    lines.append("")
    lines.append("## Таблица (token → suggested_owner → candidates → evidence)")
    lines.append("| token | total | suggested_owner | candidates (owner:pct,count) | top_files (path:count) |")
    lines.append("|---|---:|---|---|---|")

    for row in suggestions:
        token = row["token"]
        total = row["total_occurrences"]
        suggested = row["suggested_owner"]
        cand = ", ".join([f"{c['owner']}:{c['pct']}%({c['count']})" for c in row["candidates"]]) or "-"
        top_files = ", ".join([f"{f['path']}:{f['count']}" for f in row["top_files"][:3]]) or "-"
        lines.append(f"| {token} | {total} | {suggested} | {cand} | {top_files} |")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Make the run visible in CI logs
    print(f"[VF-VERB-REG-04] wrote {json_path} and {md_path}")
    print(f"[VF-VERB-REG-04] unknown tokens: {len(unknown_tokens)}")
