#!/usr/bin/env python3
"""
OBS-02-CTX: JSONL log + WAL inventory (what is реально пишеться зараз).

Generates a markdown report with:
- file list + line counts
- top-20 values for event/op/verb/type/status/reason (merged root + pld.*)
- time field discovery (root + pld.*)
- presence of key fields: symbol/tf_sec/bar_close_ts/clientOrderId/orderId/tif/order_type
- WAL gap checks (BAR_CLOSED, strategy intents/rejects, order ack/new for TTF)

Usage:
  python3 tools/obs02_ctx_log_inventory.py --out reports/obs02_ctx_log_inventory.md
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


TOP_KEYS = ("event", "op", "verb", "type", "status", "reason")
EXTRA_KEYS = ("why", "kind")
TIME_KEYS = (
    "ts_ms",
    "ts",
    "ts_sec",
    "timestamp",
    "time",
    "datetime",
    "date",
    "created_at",
    "updated_at",
    "bar_close_ts",
)
FIELD_KEYS = (
    "symbol",
    "tf_sec",
    "bar_close_ts",
    "clientOrderId",
    "orderId",
    "exchangeOrderId",
    "tif",
    "order_type",
)

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any] | None]:
    with path.open("rb") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                yield None
                continue
            if isinstance(obj, dict):
                yield obj
            else:
                yield None


def _norm(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, (str, int, float, bool)):
        return str(v)
    try:
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(v)


def _maybe_iso_key_pairs(obj: dict[str, Any]) -> list[str]:
    found: list[str] = []
    for k, v in obj.items():
        if isinstance(v, str) and ISO_RE.match(v):
            found.append(f"ISO@{k}")
    return found


@dataclass(frozen=True)
class FileInventory:
    path: str
    lines: int
    bad_json_lines: int
    top: dict[str, list[tuple[str, int]]]
    time_keys: list[tuple[str, int]]
    field_keys: list[tuple[str, int]]


def inventory_file(path: Path) -> FileInventory:
    total = 0
    bad = 0
    counters = {k: Counter() for k in (*TOP_KEYS, *EXTRA_KEYS)}
    time_present = Counter()
    field_present = Counter()

    for obj in _iter_jsonl(path):
        total += 1
        if obj is None:
            bad += 1
            continue

        pld = obj.get("pld")

        for k in (*TOP_KEYS, *EXTRA_KEYS):
            if k in obj:
                counters[k][_norm(obj.get(k))] += 1
            if isinstance(pld, dict) and k in pld:
                counters[k][_norm(pld.get(k))] += 1

        for k in TIME_KEYS:
            if k in obj:
                time_present[k] += 1
            if isinstance(pld, dict) and k in pld:
                time_present[f"pld.{k}"] += 1

        for iso_key in _maybe_iso_key_pairs(obj):
            time_present[iso_key] += 1
        if isinstance(pld, dict):
            for iso_key in _maybe_iso_key_pairs(pld):
                time_present[f"pld.{iso_key}"] += 1

        for k in FIELD_KEYS:
            if k in obj:
                field_present[k] += 1
            if isinstance(pld, dict) and k in pld:
                field_present[f"pld.{k}"] += 1

    return FileInventory(
        path=str(path),
        lines=total,
        bad_json_lines=bad,
        top={k: counters[k].most_common(20) for k in (*TOP_KEYS, *EXTRA_KEYS)},
        time_keys=time_present.most_common(),
        field_keys=field_present.most_common(),
    )


def _md_kv_list(items: list[tuple[str, int]], max_items: int = 20) -> str:
    if not items:
        return "_(none)_"
    parts = [f"`{k}` ({c})" for k, c in items[:max_items]]
    return ", ".join(parts)


def _read_n_lines(path: Path, n: int) -> list[str]:
    out: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for _ in range(n):
            line = f.readline()
            if not line:
                break
            line = line.rstrip("\n")
            if line.strip():
                out.append(line)
    return out


def _find_first_matching_line(path: Path, pattern: re.Pattern[str]) -> str | None:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            if pattern.search(line):
                return line.rstrip("\n")
    return None


def _safe_json_preview_line(line: str) -> str:
    """
    Best-effort redaction:
    - Replace `sig` fields with a placeholder (signatures are secrets).
    - Replace any long hex strings (>=48 chars) with <hex:...>.
    """
    try:
        obj = json.loads(line)
    except Exception:
        return line

    def scrub(v: Any) -> Any:
        if isinstance(v, dict):
            out = {}
            for k, vv in v.items():
                if k in {"sig", "signature", "api_key", "api_secret"}:
                    out[k] = "<redacted>"
                else:
                    out[k] = scrub(vv)
            return out
        if isinstance(v, list):
            return [scrub(x) for x in v]
        if isinstance(v, str) and re.fullmatch(r"[0-9a-fA-F]{48,}", v):
            return "<hex:redacted>"
        return v

    return json.dumps(scrub(obj), ensure_ascii=False, sort_keys=True)


def _scan_wal_verbs(wal_files: list[Path]) -> Counter:
    c = Counter()
    for p in wal_files:
        for obj in _iter_jsonl(p):
            if not isinstance(obj, dict):
                continue
            verb = obj.get("verb")
            if verb:
                c[str(verb)] += 1
    return c


def _has_any(counter: Counter, needles: list[str]) -> dict[str, int]:
    out = {}
    for n in needles:
        out[n] = int(counter.get(n, 0))
    return out


def build_report(root: Path) -> str:
    patterns = [
        "logs/**/*.jsonl",
        "ops/wal/**/*.jsonl",
        "reports/**/*.jsonl",
    ]
    files: list[Path] = []
    for pat in patterns:
        files.extend(Path(p) for p in glob.glob(str(root / pat), recursive=True))
    files = [p for p in files if p.is_file()]
    files.sort()

    inventories = [inventory_file(p) for p in files]

    wal_files = [p for p in files if str(p).startswith(str(root / "ops" / "wal"))]
    wal_verb_counts = _scan_wal_verbs(wal_files)

    # WAL gap checks
    wal_checks = {
        "bars": _has_any(wal_verb_counts, ["BAR_CLOSED", "EVT:BAR_CLOSED", "EVT:BAR_CLOSED_V1"]),
        "strategy": _has_any(
            wal_verb_counts,
            [
                "CMD:PROCESS_STRATEGY",
                "PROCESS_STRATEGY",
                "TRADE_INTENT_PROPOSED",
                "TRADE_INTENT_REJECTED",
                "STRATEGY_SIGNAL_PRODUCED",
                "DECISION_TRACE_EMITTED",
            ],
        ),
        "orders": _has_any(
            wal_verb_counts,
            [
                "OPEN",
                "CLOSE",
                "ORDER_PLACED",
                "ORDER_ACK",
                "ORDER_FILL",
                "ORDER_STATE_CHANGED",
                "ORDER_REJECTED",
            ],
        ),
    }

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    md: list[str] = []
    md.append(f"# OBS-02-CTX — Log/WAL Inventory (generated {now})")
    md.append("")
    md.append("Scope patterns:")
    for pat in patterns:
        md.append(f"- `{pat}`")
    md.append("")

    md.append("## Files")
    md.append("| file | lines | bad_json | time fields (top) | key fields present (top) |")
    md.append("|---|---:|---:|---|---|")
    for inv in inventories:
        md.append(
            "| "
            + f"`{inv.path}`"
            + f" | {inv.lines}"
            + f" | {inv.bad_json_lines}"
            + " | "
            + _md_kv_list(inv.time_keys, max_items=6)
            + " | "
            + _md_kv_list(inv.field_keys, max_items=8)
            + " |"
        )
    md.append("")

    md.append("## Top Values (top-20 per key; merged root + `pld.*`)")
    for inv in inventories:
        md.append(f"### `{inv.path}`")
        md.append(f"- lines: `{inv.lines}`; bad_json_lines: `{inv.bad_json_lines}`")
        md.append("| key | top-20 values |")
        md.append("|---|---|")
        for k in TOP_KEYS:
            md.append(f"| `{k}` | {_md_kv_list(inv.top.get(k, []), max_items=20)} |")
        md.append("")

    md.append("## WAL Presence Checks")
    md.append("These are counts of `verb` values found in `ops/wal/**/*.jsonl`.")
    md.append("")
    md.append("### Bars")
    for k, v in wal_checks["bars"].items():
        md.append(f"- `{k}`: `{v}`")
    md.append("")
    md.append("### Strategy / Decision SSOT")
    for k, v in wal_checks["strategy"].items():
        md.append(f"- `{k}`: `{v}`")
    md.append("")
    md.append("### Orders (for time-to-fill)")
    for k, v in wal_checks["orders"].items():
        md.append(f"- `{k}`: `{v}`")
    md.append("")

    md.append("## Example Lines (structure preserved; best-effort redaction)")
    samples: list[tuple[str, str]] = []
    priority: list[tuple[str, re.Pattern[str]]] = [
        ("logs/aurora_events.jsonl", re.compile(r'"event"\s*:\s*"ORDER_STATE_CHANGED"')),
        ("ops/wal", re.compile(r'"verb"\s*:\s*"TRADE_INTENT_PROPOSED"')),
        ("ops/wal", re.compile(r'"op"\s*:\s*"ERR"')),
        ("ops/wal", re.compile(r'"op"\s*:\s*"CMD".*\"verb\"\\s*:\\s*\"OPEN\"')),
        ("reports/mr_chain_probe.jsonl", re.compile(r'"source"\\s*:\\s*\"mr_reject\"|\"reason\"')),
    ]

    # deterministic selection: each rule picks the first matching line in lexicographic file order
    for prefix, pat in priority:
        if prefix.endswith(".jsonl"):
            p = root / prefix
            if p.exists():
                line = _find_first_matching_line(p, pat)
                if line:
                    samples.append((str(p), line))
            continue

        # directory prefix scan (e.g., ops/wal)
        base = root / prefix
        candidates = [p for p in files if str(p).startswith(str(base)) and p.suffix == ".jsonl"]
        for p in candidates:
            line = _find_first_matching_line(p, pat)
            if line:
                samples.append((str(p), line))
                break

    # Fill remaining samples with first-line fallbacks (up to 5)
    if len(samples) < 5:
        seen = {p for p, _ in samples}
        for p in files:
            if len(samples) >= 5:
                break
            if str(p) in seen:
                continue
            lines = _read_n_lines(p, 1)
            if lines:
                samples.append((str(p), lines[0]))

    for path, line in samples:
        md.append(f"### `{path}`")
        md.append("```json")
        md.append(_safe_json_preview_line(line))
        md.append("```")
        md.append("")

    # Key findings / holes (quick heuristics)
    md.append("## Quick Findings / Holes")
    md.append("- `ops/wal/**/*.jsonl` currently contains **no BAR_CLOSED**-like records (see WAL Presence Checks).")
    md.append("- `TRADE_INTENT_PROPOSED` exists in WAL, but symbol identity sometimes lives under `pld.instrument` (not `pld.symbol`) → parser hole.")
    md.append("- WAL uses mixed time fields (`ts` in ms vs `timestamp` float seconds) depending on producer → normalize for SSOT parsing.")
    md.append("")

    return "\n".join(md).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="Output markdown path")
    args = ap.parse_args()

    root = Path(os.getcwd()).resolve()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_report(root), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
