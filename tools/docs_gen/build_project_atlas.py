#!/usr/bin/env python3
"""
tools/build_project_atlas.py

Simple project atlas builder — scans configs, schemas and python sources to extract
basic artefacts used by docs/PROJECT_ATLAS.md and reports/atlas/*.json

This is an incremental, best-effort tool per TASK.md. It intentionally avoids
runtime imports of project code and uses AST/regex to find event tokens and
emit(...) usages.
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except Exception:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT / "reports" / "atlas"
DIAGRAMS_DIR = ROOT / "docs" / "diagrams"
DOC_PATH = ROOT / "docs" / "PROJECT_ATLAS.md"

EXCLUDE_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "LLA"}

EVENT_TAGS = ("EVT:", "CMD:", "DEC:", "ERR:")


def ensure_dirs() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)


def is_excluded(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    return False


def scan_yaml_configs() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # Scan for YAML files in common config locations (configs/, config/, root)
    patterns = ["**/*.yml", "**/*.yaml"]
    for pat in patterns:
        for p in ROOT.rglob(pat):
            if is_excluded(p):
                continue
            # skip non-file entries
            if not p.is_file():
                continue
            try:
                if yaml:
                    with p.open("r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                else:
                    with p.open("r", encoding="utf-8") as f:
                        data = json.loads(f.read())
            except Exception:
                data = None
            out[str(p.relative_to(ROOT))] = {
                "keys": list(data.keys()) if isinstance(data, dict) else None,
                "raw": data,
            }
    return out


def scan_json_schemas() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    schema_root = ROOT / "config" / "_schemas"
    if not schema_root.exists():
        return out
    for p in schema_root.rglob("*.json"):
        if is_excluded(p):
            continue
        try:
            with p.open("r", encoding="utf-8") as f:
                j = json.load(f)
        except Exception:
            j = None
        item = {"path": str(p.relative_to(ROOT)), "$id": None,
                "$schema": None, "required": None, "defaults": {}}
        if isinstance(j, dict):
            item.update({"$id": j.get("$id"), "$schema": j.get(
                "$schema"), "required": j.get("required")})
            # collect property defaults when present
            props = j.get("properties", {})
            for k, v in props.items():
                if isinstance(v, dict) and "default" in v:
                    item["defaults"][k] = v["default"]
        out.append(item)
    return out


def extract_from_dict_literal(node: ast.Dict) -> List[str]:
    keys: List[str] = []
    for k in node.keys:
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            keys.append(k.value)
        elif isinstance(k, getattr(ast, "Str", ())):
            keys.append(k.s)
        else:
            keys.append("<computed_key>")
    return keys


class EventVisitor(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.events: List[Dict[str, Any]] = []
        self.handlers: List[Dict[str, Any]] = []

    def visit_Constant(self, node: ast.Constant) -> None:  # Python 3.8+
        if isinstance(node.value, str):
            for tag in EVENT_TAGS:
                if node.value.startswith(tag):
                    # record a string-literal event
                    self.events.append({
                        "file": str(self.path),
                        "literal": node.value,
                        "lineno": getattr(node, "lineno", None),
                    })

    def visit_Str(self, node: ast.Str) -> None:  # older nodes
        for tag in EVENT_TAGS:
            if node.s.startswith(tag):
                self.events.append({"file": str(
                    self.path), "literal": node.s, "lineno": getattr(node, "lineno", None)})

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("on_"):
            self.handlers.append(
                {"file": str(self.path), "name": node.name, "lineno": node.lineno})
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # find emit(...) and emit_compat(...) calls
        fn = node.func
        fname = None
        if isinstance(fn, ast.Name):
            fname = fn.id
        elif isinstance(fn, ast.Attribute):
            fname = fn.attr
        if fname in ("emit", "emit_compat"):
            ev: Dict[str, Any] = {"file": str(self.path), "lineno": getattr(
                node, "lineno", None), "fn": fname, "event": None, "payload_keys": [], "why": None}
            # first arg might be event name
            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    ev["event"] = first.value
                elif isinstance(first, getattr(ast, "Str", ())):
                    ev["event"] = first.s
            # payload often a dict literal in second arg or keyword
            # inspect args for dict
            for a in node.args[1:]:
                if isinstance(a, ast.Dict):
                    ev["payload_keys"] = extract_from_dict_literal(a)
            for kw in node.keywords:
                if isinstance(kw.value, ast.Dict):
                    ev["payload_keys"] = extract_from_dict_literal(kw.value)
                if kw.arg in ("event", "name") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    ev["event"] = kw.value.value
                if kw.arg == "why" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    ev["why"] = kw.value.value
            self.events.append(ev)
        self.generic_visit(node)


def scan_python_events() -> Dict[str, Any]:
    out_events: List[Dict[str, Any]] = []
    out_handlers: List[Dict[str, Any]] = []
    for p in ROOT.rglob("*.py"):
        if is_excluded(p):
            continue
        # skip generated directories often
        try:
            src = p.read_text(encoding="utf-8-sig")
            tree = ast.parse(src)
        except Exception:
            continue

        rel_path = str(p.relative_to(ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("on_"):
                out_handlers.append(
                    {"file": rel_path, "name": node.name, "lineno": node.lineno})
                continue

            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for tag in EVENT_TAGS:
                    if node.value.startswith(tag):
                        out_events.append({
                            "file": rel_path,
                            "literal": node.value,
                            "lineno": getattr(node, "lineno", None),
                        })
                continue

            if not isinstance(node, ast.Call):
                continue

            fn = node.func
            fname = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(
                fn, ast.Attribute) else None
            if fname not in ("emit", "emit_compat"):
                continue

            ev: Dict[str, Any] = {
                "file": rel_path,
                "lineno": getattr(node, "lineno", None),
                "fn": fname,
                "event": None,
                "payload_keys": [],
                "why": None,
            }

            if node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    ev["event"] = first.value
                elif isinstance(first, getattr(ast, "Str", ())):
                    ev["event"] = first.s

            for arg in node.args[1:]:
                if isinstance(arg, ast.Dict):
                    ev["payload_keys"] = extract_from_dict_literal(arg)

            for kw in node.keywords:
                if isinstance(kw.value, ast.Dict):
                    ev["payload_keys"] = extract_from_dict_literal(kw.value)
                if kw.arg in ("event", "name") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    ev["event"] = kw.value.value
                if kw.arg == "why" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    ev["why"] = kw.value.value

            out_events.append(ev)
    return {"events": out_events, "handlers": out_handlers}


def scan_instruments_from_configs(configs: Dict[str, Any]) -> List[Dict[str, Any]]:
    instruments: List[Dict[str, Any]] = []
    # look through loaded config dicts for `instruments` keys
    for path, info in configs.items():
        raw = info.get("raw") if isinstance(info, dict) else None
        if not isinstance(raw, dict):
            continue
        # support nested keys like raw.get('aurora', {}).get('instruments') or raw.get('trading', {}).get('instruments')
        # check common places for instruments definitions
        candidates = []
        if "instruments" in raw and isinstance(raw["instruments"], dict):
            candidates.append((path, raw["instruments"]))
        # check trading.<instruments>
        if "trading" in raw and isinstance(raw["trading"], dict) and "instruments" in raw["trading"]:
            c = raw["trading"]["instruments"]
            if isinstance(c, dict):
                candidates.append((path, c))
        # check nested aurora key
        if "aurora" in raw and isinstance(raw["aurora"], dict) and "instruments" in raw["aurora"]:
            c = raw["aurora"]["instruments"]
            if isinstance(c, dict):
                candidates.append((path, c))
        for pth, table in candidates:
            for sym, props in table.items():
                if not isinstance(props, dict):
                    continue
                entry = {"symbol": sym}
                for k in ("leverage", "step_size", "tick_size", "min_qty", "min_notional", "quote"):
                    if k in props:
                        entry[k] = props[k]
                entry["source_config"] = pth
                instruments.append(entry)
    return instruments


def scan_gates_policies_from_configs(configs: Dict[str, Any]) -> Dict[str, Any]:
    gates: Dict[str, Any] = {"files": {}}
    keys_of_interest = ["execution", "risk", "ops", "decision"]
    for path, info in configs.items():
        raw = info.get("raw") if isinstance(info, dict) else None
        if not isinstance(raw, dict):
            continue
        gates["files"][path] = {}
        for k in keys_of_interest:
            if k in raw:
                gates["files"][path][k] = raw[k]
    # also compute merged defaults / current by scanning top-level master config if present
    master = configs.get("configs\\master_config_v1.yaml") or configs.get(
        "configs/master_config_v1.yaml")
    merged: Dict[str, Any] = {}
    if master and isinstance(master.get("raw"), dict):
        raw = master["raw"]
        for k in keys_of_interest:
            if k in raw:
                merged[k] = raw[k]
    gates["merged_master"] = merged
    return gates


def infer_domain_from_path(path: str) -> Optional[str]:
    # crude heuristic: apps/reference/domains/<domain>/...
    m = re.search(r"apps/reference/domains/([^/\\]+)", path)
    if m:
        return m.group(1)
    return None


def build_reports() -> None:
    ensure_dirs()
    configs = scan_yaml_configs()
    schemas = scan_json_schemas()
    py = scan_python_events()

    # Compose extracted_configs.json
    cfg_path = REPORTS_DIR / "extracted_configs.json"
    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2, ensure_ascii=False)

    # Compose extracted_contracts.json
    contracts_path = REPORTS_DIR / "extracted_contracts.json"
    with contracts_path.open("w", encoding="utf-8") as f:
        json.dump(schemas, f, indent=2, ensure_ascii=False)

    # Compose extracted_events.json
    events_list: List[Dict[str, Any]] = []
    for e in py.get("events", []):
        event_name = e.get("event") or e.get("literal") or "<unknown>"
        domain = infer_domain_from_path(e.get("file", ""))
        # split type/verb if possible: like EVT:ORDER_STATE_CHANGED
        typ = None
        verb = None
        for tag in EVENT_TAGS:
            if isinstance(event_name, str) and event_name.startswith(tag):
                typ = tag[:-1]
                verb = event_name[len(tag):]
        events_list.append({
            "source_file": e.get("file"),
            "lineno": e.get("lineno"),
            "type": typ,
            "verb": verb,
            "event": event_name,
            "payload_keys": e.get("payload_keys", []),
            "domain": domain,
        })
    events_path = REPORTS_DIR / "extracted_events.json"
    with events_path.open("w", encoding="utf-8") as f:
        json.dump(events_list, f, indent=2, ensure_ascii=False)

    # Compose instruments table
    instruments = scan_instruments_from_configs(configs)
    instr_path = REPORTS_DIR / "instruments_table.json"
    with instr_path.open("w", encoding="utf-8") as f:
        json.dump(instruments, f, indent=2, ensure_ascii=False)

    # Compose gates/policies
    gates = scan_gates_policies_from_configs(configs)
    gates_path = REPORTS_DIR / "gates_policies.json"
    with gates_path.open("w", encoding="utf-8") as f:
        json.dump(gates, f, indent=2, ensure_ascii=False)

    # Generate a lightweight docs/PROJECT_ATLAS.md
    generate_docs(configs, schemas, events_list)
    # write diagrams placeholders
    write_diagrams()


def generate_docs(configs: Dict[str, Any], schemas: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> None:
    lines: List[str] = []
    lines.append("# PROJECT ATLAS\n")
    lines.append("## Overview\n")
    lines.append("This document was generated by `tools/build_project_atlas.py` — a best-effort project atlas that extracts configs, schemas and events.\n")

    lines.append("## Configs (SSOT)\n")
    if not configs:
        lines.append("No configs found under `configs/`\n")
    else:
        for path, info in sorted(configs.items()):
            lines.append(f"- `{path}` — top keys: {info.get('keys')}`\n")

    lines.append("## JSON Schemas\n")
    if not schemas:
        lines.append("No JSON schemas found under `config/_schemas/`\n")
    else:
        for s in schemas:
            lines.append(
                f"- `{s.get('path')}` — $id: {s.get('$id')} required: {s.get('required')}\n")

    lines.append("## Events and Contracts\n")
    if not events:
        lines.append("No events detected in Python sources.\n")
    else:
        lines.append("| event | type | domain | payload_keys | source |")
        lines.append("|---|---|---|---|---|")
        for e in events:
            ev = e.get("event")
            typ = e.get("type")
            domain = e.get("domain") or "-"
            pk = ", ".join(e.get("payload_keys", [])) or "-"
            src = f"{e.get('source_file')}:{e.get('lineno')}"
            lines.append(f"| `{ev}` | {typ} | {domain} | {pk} | {src} |")

    lines.append("\n## Diagrams\n")
    lines.append("Mermaid diagrams are available in `docs/diagrams/*.mmd`.\n")

    # Instruments section
    instr_path = REPORTS_DIR / "instruments_table.json"
    lines.append("## Instruments / Symbols\n")
    if instr_path.exists():
        try:
            instr = json.loads(instr_path.read_text(encoding="utf-8"))
        except Exception:
            instr = None
        if instr:
            lines.append(
                "| symbol | step_size | tick_size | min_qty | min_notional | quote | source |\n")
            lines.append("|---|---|---|---|---|---|---|")
            for it in instr:
                lines.append(
                    f"| {it.get('symbol')} | {it.get('step_size', '-')} | {it.get('tick_size', '-')} | {it.get('min_qty', '-')} | {it.get('min_notional', '-')} | {it.get('quote', '-')} | {it.get('source_config')} |")
        else:
            lines.append("No instruments discovered.\n")
    else:
        lines.append("No instruments table generated.\n")

    # Gates & policies
    gates_path = REPORTS_DIR / "gates_policies.json"
    lines.append("## Gates & Policies\n")
    if gates_path.exists():
        try:
            gp = json.loads(gates_path.read_text(encoding="utf-8"))
        except Exception:
            gp = None
        if gp:
            lines.append(
                "Merged master values (if master_config_v1.yaml present):\n")
            lines.append("```")
            try:
                md = json.dumps(gp.get('merged_master', {}),
                                indent=2, ensure_ascii=False)
            except Exception:
                md = "{}"
            lines.append(md)
            lines.append("```")
        else:
            lines.append("No gates/policies data available.\n")
    else:
        lines.append("No gates/policies report generated.\n")

    DOC_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_diagrams() -> None:
    events_flow = DIAGRAMS_DIR / "events_flow.mmd"
    events_flow.write_text("""---
title: Events flow
---
graph LR
  LiveData --> MarketDataConnector
  MarketDataConnector --> FeatureEngineering
  FeatureEngineering --> RiskManagement
  RiskManagement --> DecisionMaking
  DecisionMaking --> AuroraBridge
  AuroraBridge --> ExecPosFSM
  ExecPosFSM --> Adapter
  Adapter --> Binance
  Binance --> UserStream
  UserStream --> PositionTracking
""", encoding="utf-8")

    order_lifecycle = DIAGRAMS_DIR / "order_lifecycle.mmd"
    order_lifecycle.write_text("""---
title: Order lifecycle
---
sequenceDiagram
    participant Client
    participant Bridge
    participant ExecPosFSM
    participant Adapter
    Client->>Bridge: CMD:OPEN
    Bridge->>ExecPosFSM: DEC:OPEN
    ExecPosFSM->>Adapter: SEND_ORDER
    Adapter->>Exchange: place
    Exchange-->>Adapter: ack/fill/cancel
    Adapter-->>ExecPosFSM: ORDER_STATE_CHANGED
""", encoding="utf-8")

    guards = DIAGRAMS_DIR / "guards.mmd"
    guards.write_text("""---
title: Guards order
---
flowchart TD
  Ops[Killswitch/QuietHours] --> Exposure[Exposure Guard]
  Exposure --> Daily[Daily Loss/Drawdown]
  Daily --> PostFill[Post-fill hold]
  PostFill --> FailClosed[Fail-Closed reasons]
""", encoding="utf-8")


def main() -> None:
    print("Building project atlas...")
    build_reports()
    print("Wrote:")
    for p in REPORTS_DIR.glob("*.json"):
        print(" -", p)
    print("Docs:", DOC_PATH)


if __name__ == "__main__":
    main()
