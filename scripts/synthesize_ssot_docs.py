#!/usr/bin/env python3
import json
from pathlib import Path

REPORTS_DIR = Path("reports")
DOCS_DIR = Path("docs")

def main():
    with open(REPORTS_DIR / "config_inventory.json", "r") as f:
        inventory = json.load(f)
    with open(REPORTS_DIR / "config_overlap_report.json", "r") as f:
        overlaps = json.load(f)
    with open(REPORTS_DIR / "config_code_usage_report.json", "r") as f:
        usage = json.load(f)
    with open(REPORTS_DIR / "config_effective_provenance.json", "r") as f:
        provenance = json.load(f)

    # Index usage by key
    usage_map = {u["key"]: u for u in usage}
    # Index overlaps by key
    overlap_map = {o["key"]: o for o in overlaps}
    # Index provenance by key
    prov_map = {p["key"]: p for p in provenance}

    output = [
        "# Aurora Configuration — Single Source of Truth (SSOT)",
        "",
        "This document is automatically generated from code-truth analytics.",
        "It establishes the definitive map of configuration parameters, their sources, and their readers.",
        "",
        "## Summary Statistics",
        f"- **Total Parameters (Inventory)**: {len(inventory)}",
        f"- **Effective Parameters (Unique Paths)**: {len(prov_map)}",
        f"- **Code-Referenced Parameters**: {len(usage)}",
        f"- **Contract Violations (Overlaps)**: {len(overlaps)}",
        "",
        "## Critical Overlaps (Action Required)",
        "The following keys appear in multiple YAML files and MUST be moved to a single SSOT location.",
        "",
        "| Key | Files | Severity |",
        "| :--- | :--- | :--- |"
    ]

    for overlap in sorted(overlaps, key=lambda x: x["severity"], reverse=True):
        if overlap["severity"] == "CRITICAL":
            files = ", ".join(overlap["files"])
            output.append(f"| `{overlap['key']}` | {files} | **{overlap['severity']}** |")

    output.extend([
        "",
        "## Effective Provenance Map",
        "Tracing each parameter to its definitive source file.",
        "",
        "| Parameter Path | Source File | Usage Count | Stage |",
        "| :--- | :--- | :--- | :--- |"
    ])

    # Show top 50 parameters or filtered list
    for key in sorted(prov_map.keys())[:100]:
        prov = prov_map[key]
        use = usage_map.get(key, {"locations": []})
        use_count = len(use["locations"])
        output.append(f"| `{key}` | {prov['source_file']} | {use_count} | {prov['merge_stage']} |")

    output.extend([
        "",
        "## Code Usage Details",
        "Mapping parameters to their implementation readers.",
        "",
    ])

    for key in sorted(usage_map.keys())[:50]:
        u = usage_map[key]
        output.append(f"### `{key}`")
        for loc in u["locations"][:5]:
            output.append(f"- `[{loc['file']}:{loc['line']}]` {loc['expr']}")
        if len(u["locations"]) > 5:
            output.append(f"- ... and {len(u['locations']) - 5} more locations")
        output.append("")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with open(DOCS_DIR / "CONFIG_MAP_SSOT.md", "w") as f:
        f.write("\n".join(output))
    print(f"Generated {DOCS_DIR / 'CONFIG_MAP_SSOT.md'}")

if __name__ == "__main__":
    main()
