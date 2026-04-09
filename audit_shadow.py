import json
from collections import defaultdict


PLACEHOLDER_TEXT_VALUES = frozenset({"unknown"})


def is_placeholder_value(value):
    return isinstance(value, str) and value.strip().lower() in PLACEHOLDER_TEXT_VALUES


def is_useful_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and not is_placeholder_value(stripped)
    return True


def analyze_journal():
    filepath = r"c:\Users\user\Music\Phenix\logs\shadow_critical_event_journal_v1.jsonl"
    outpath = r"c:\Users\user\Music\Phenix\shadow_audit_result.json"

    stats = {
        "total_records": 0,
        "unique_event_names": set(),
        "unique_op_verb_pairs": set(),
        "family_counts": defaultdict(int),
        "family_fields": defaultdict(lambda: defaultdict(int)),
        "family_placeholder_fields": defaultdict(lambda: defaultdict(int)),
        "record_types": defaultdict(int),
    }

    fields_to_check = [
        "source_component", "source_path", "event_origin_type", "rid", "causation_rid",
        "order_id", "client_order_id", "position_id", "lifecycle_id", "strategy_id",
        "side", "qty", "price", "truth_owner", "local_state_before", "local_state_after",
        "restore_marker"
    ]

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    stats["total_records"] += 1

                    event_name = record.get("event_name", "UNKNOWN")
                    op = record.get("op", "UNKNOWN")
                    verb = record.get("verb", "UNKNOWN")
                    record_type = record.get("record_type", "UNKNOWN")

                    stats["unique_event_names"].add(event_name)
                    stats["unique_op_verb_pairs"].add(f"{op}:{verb}")
                    stats["family_counts"][event_name] += 1
                    stats["record_types"][record_type] += 1

                    # Track fields
                    for field in fields_to_check:
                        val = record.get(field)
                        if is_placeholder_value(val):
                            stats["family_placeholder_fields"][event_name][field] += 1
                        elif is_useful_value(val):
                            stats["family_fields"][event_name][field] += 1

                except json.JSONDecodeError:
                    pass
    except Exception as e:
        with open(outpath, 'w', encoding='utf-8') as f:
            json.dump({"error": str(e)}, f)
        return

    # convert sets to lists
    stats["unique_event_names"] = list(stats["unique_event_names"])
    stats["unique_op_verb_pairs"] = list(stats["unique_op_verb_pairs"])
    stats["family_counts"] = dict(stats["family_counts"])

    # format fields dict
    formatted_fields = {}
    for family, fields in stats["family_fields"].items():
        formatted_fields[family] = dict(fields)
    stats["family_fields"] = formatted_fields

    formatted_placeholder_fields = {}
    for family, fields in stats["family_placeholder_fields"].items():
        formatted_placeholder_fields[family] = dict(fields)
    stats["family_placeholder_fields"] = formatted_placeholder_fields

    with open(outpath, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    analyze_journal()
