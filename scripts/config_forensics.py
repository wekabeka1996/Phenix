from _compat import execute, reexport

_TARGET = "diagnostics/config_forensics.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())


def get_inventory():
    inventory = []

    # Process main YAML files
    for yaml_file in YAML_FILES:
        path = CONFIG_DIR / yaml_file
        if not path.exists():
            continue

        with open(path, "r") as f:
            try:
                data = yaml.safe_load(f)
                if data:
                    flat = flatten_dict(data)
                    for item in flat:
                        item["file"] = yaml_file
                        item["yaml_path"] = item["key"]
                        inventory.append(item)
            except Exception as e:
                print(f"Error parsing {yaml_file}: {e}")

    # Process strategy profiles
    if STRATEGY_PROFILES_DIR.exists():
        for path in STRATEGY_PROFILES_DIR.glob("*.yaml"):
            with open(path, "r") as f:
                try:
                    data = yaml.safe_load(f)
                    if data:
                        flat = flatten_dict(data)
                        for item in flat:
                            item["file"] = f"strategies/{path.name}"
                            item["yaml_path"] = item["key"]
                            inventory.append(item)
                except Exception as e:
                    print(f"Error parsing {path.name}: {e}")

    return inventory


def get_overlaps(inventory):
    overlaps = {}
    for item in inventory:
        key = item["key"]
        if key not in overlaps:
            overlaps[key] = []
        overlaps[key].append(item)

    report = []
    for key, items in overlaps.items():
        if len(items) > 1:
            report.append({
                "key": key,
                "files": [i["file"] for i in items],
                "values": [i["value_preview"] for i in items],
                "severity": "WARN"  # Default to WARN, elevate to CRITICAL if used in code
            })
    return report


def analyze_code_usage():
    # Regex for common config access patterns:
    # 1. cfg.path.to.key
    # 2. config.path.to.key
    # 3. ["key"] or .get("key")

    # We'll focus on structured access first as it's more reliable
    usage = {}

    patterns = [
        re.compile(r"(?:cfg|config)\.([a-zA-Z0-9_\.]+)"),
        re.compile(r"(?:cfg|config)\[['\"]([a-zA-Z0-9_\.]+)['\"]\]"),
        re.compile(r"\.get\(['\"]([a-zA-Z0-9_\.]+)['\"]\)"),
    ]

    for root, _, files in os.walk(REPO_ROOT / "apps"):
        for file in files:
            if not file.endswith(".py"):
                continue
            path = Path(root) / file
            rel_path = path.relative_to(REPO_ROOT)

            with open(path, "r", errors="ignore") as f:
                for i, line in enumerate(f, 1):
                    for pattern in patterns:
                        for match in pattern.finditer(line):
                            key = match.group(1)
                            # Basic heuristic to categorize domain
                            domain = "unknown"
                            if "decision_making" in str(rel_path):
                                domain = "decision_making"
                            elif "feature_engineering" in str(rel_path):
                                domain = "feature_engineering"
                            elif "execution_position" in str(rel_path):
                                domain = "execution_position"
                            elif "market_data" in str(rel_path):
                                domain = "market_data"

                            if key not in usage:
                                usage[key] = {
                                    "key": key, "locations": [], "domain": domain}

                            usage[key]["locations"].append({
                                "file": str(rel_path),
                                "line": i,
                                "expr": match.group(0).strip()
                            })

    return list(usage.values())


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    inventory = get_inventory()
    with open(REPORTS_DIR / "config_inventory.json", "w") as f:
        json.dump(inventory, f, indent=2)
    print(f"Generated {REPORTS_DIR / 'config_inventory.json'}")

    overlaps = get_overlaps(inventory)

    usage = analyze_code_usage()
    with open(REPORTS_DIR / "config_code_usage_report.json", "w") as f:
        json.dump(usage, f, indent=2)
    print(f"Generated {REPORTS_DIR / 'config_code_usage_report.json'}")

    # Mark overlaps as CRITICAL if they are in usage
    usage_keys = {u["key"] for u in usage}
    for overlap in overlaps:
        if overlap["key"] in usage_keys:
            overlap["severity"] = "CRITICAL"
        # Special attention: overlaps between trading.yaml and domains.yaml
        if "trading.yaml" in overlap["files"] and "domains.yaml" in overlap["files"]:
            overlap["severity"] = "CRITICAL"

    with open(REPORTS_DIR / "config_overlap_report.json", "w") as f:
        json.dump(overlaps, f, indent=2)
    print(f"Generated {REPORTS_DIR / 'config_overlap_report.json'}")


if __name__ == "__main__":
    main()
