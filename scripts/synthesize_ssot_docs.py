from _compat import execute, reexport

_TARGET = "docs_gen/synthesize_ssot_docs.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())

    for overlap in sorted(overlaps, key=lambda x: x["severity"], reverse=True):
        if overlap["severity"] == "CRITICAL":
            files = ", ".join(overlap["files"])
            output.append(
                f"| `{overlap['key']}` | {files} | **{overlap['severity']}** |")

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
        output.append(
            f"| `{key}` | {prov['source_file']} | {use_count} | {prov['merge_stage']} |")

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
            output.append(
                f"- ... and {len(u['locations']) - 5} more locations")
        output.append("")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with open(DOCS_DIR / "CONFIG_MAP_SSOT.md", "w") as f:
        f.write("\n".join(output))
    print(f"Generated {DOCS_DIR / 'CONFIG_MAP_SSOT.md'}")

if __name__ == "__main__":
    main()
