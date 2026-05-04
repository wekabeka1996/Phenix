"""Phase 0: Add quarantine markers to all legacy_runtime files.

Rules:
- Add `# QUARANTINED: legacy_runtime` as first non-shebang, non-encoding line.
- Add `__quarantined__ = True` right after the module docstring / initial imports block.
- Do NOT break shebang, encoding comments, or `from __future__` placement.
- Idempotent: skip files that already have the markers.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NEOCORTEX_ROOT = REPO_ROOT / "apps" / "reference" / "domains" / "neocortex"

# All files classified as legacy_runtime in the inventory
LEGACY_RUNTIME_FILES = [
    "logic/dreamer.py",
    "logic/brain/core.py",
    "logic/brain/bridge.py",
    "logic/brain/worker.py",
    "logic/brain/vae.py",
    "logic/brain/world_model.py",
    "logic/ingest/tailer.py",
    "logic/ingest/multi_tailer.py",
    "logic/ingest/wal_replayer.py",
    "transport/__init__.py",
    "transport/adapter.py",
    "PPO/ppo_library_v2/ppo_system/__init__.py",
    "PPO/ppo_library_v2/ppo_system/agent.py",
    "PPO/ppo_library_v2/ppo_system/core/dataclasses.py",
    "PPO/ppo_library_v2/ppo_system/learning/__init__.py",
    "PPO/ppo_library_v2/ppo_system/learning/buffer.py",
    "PPO/ppo_library_v2/ppo_system/learning/controllers.py",
    "PPO/ppo_library_v2/ppo_system/learning/updater.py",
    "PPO/ppo_library_v2/ppo_system/models/__init__.py",
    "PPO/ppo_library_v2/ppo_system/models/actor_critic_lstm.py",
    "PPO/ppo_library_v2/ppo_system/models/base_model.py",
    "PPO/ppo_library_v2/ppo_system/training_loop.py",
    "PPO/ppo_library_v2/ppo_system/utils/__init__.py",
    "PPO/ppo_library_v2/ppo_system/utils/logging.py",
    "PPO/ppo_library_v2/ppo_system/utils/safety.py",
    "PPO/ppo_library_v2/ppo_system/utils/seed.py",
]

QUARANTINE_COMMENT = "# QUARANTINED: legacy_runtime"
QUARANTINE_FLAG = "__quarantined__ = True"


def add_quarantine_markers(filepath: Path) -> dict:
    """Add quarantine markers to a single file. Returns action taken."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    result = {"file": str(filepath.relative_to(REPO_ROOT)), "actions": []}

    has_comment = any(QUARANTINE_COMMENT in line for line in lines)
    has_flag = any(QUARANTINE_FLAG in line for line in lines)

    if has_comment and has_flag:
        result["actions"].append("already_marked")
        return result

    # Find the insertion point for the comment:
    # After shebang (#!) and encoding (# -*- coding) lines, but before everything else.
    insert_comment_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#!") or stripped.startswith("# -*-"):
            insert_comment_at = i + 1
        else:
            break

    # Find insertion point for __quarantined__ = True:
    # After the first module-level docstring closes (or after all initial comments
    # and imports if there's no docstring), but before the first real code.
    insert_flag_at = None
    in_docstring = False
    docstring_delim = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip already-inserted quarantine lines
        if QUARANTINE_COMMENT in stripped or QUARANTINE_FLAG in stripped:
            continue

        if not in_docstring:
            # Look for docstring start
            if stripped.startswith('"""') or stripped.startswith("'''"):
                delim = stripped[:3]
                # Check if single-line docstring
                if stripped.count(delim) >= 2 and len(stripped) > 3:
                    insert_flag_at = i + 1
                    break
                else:
                    in_docstring = True
                    docstring_delim = delim
            elif stripped.startswith("#") or stripped == "" or stripped.startswith("# "):
                continue  # Skip comments and blank lines
            else:
                # No docstring found, insert after comment block
                insert_flag_at = i
                break
        else:
            # Inside docstring, look for closing delimiter
            if docstring_delim and docstring_delim in stripped:
                insert_flag_at = i + 1
                in_docstring = False
                break

    if insert_flag_at is None:
        insert_flag_at = len(lines)

    # Add comment marker
    if not has_comment:
        # Check if existing [LEGACY QUARANTINE] comment exists
        existing_legacy_idx = None
        for i, line in enumerate(lines):
            if "[LEGACY QUARANTINE]" in line:
                existing_legacy_idx = i
                break

        if existing_legacy_idx is not None:
            # Replace existing comment
            lines[existing_legacy_idx] = QUARANTINE_COMMENT + "\n"
            result["actions"].append("replaced_legacy_comment")
        else:
            lines.insert(insert_comment_at, QUARANTINE_COMMENT + "\n")
            result["actions"].append("added_comment")
            # Adjust flag insertion point
            if insert_flag_at >= insert_comment_at:
                insert_flag_at += 1

    # Re-check: Find the correct insert_flag_at after modification
    # We want it right after the module docstring closes
    if not has_flag:
        # Re-scan for docstring end position
        actual_insert = None
        in_ds = False
        ds_delim = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if QUARANTINE_COMMENT in stripped or stripped == "":
                continue
            if stripped.startswith("#"):
                continue
            if not in_ds:
                if stripped.startswith('"""') or stripped.startswith("'''"):
                    delim = stripped[:3]
                    if stripped.count(delim) >= 2 and len(stripped) > 3:
                        actual_insert = i + 1
                        break
                    else:
                        in_ds = True
                        ds_delim = delim
                else:
                    actual_insert = i
                    break
            else:
                if ds_delim and ds_delim in stripped:
                    actual_insert = i + 1
                    break

        if actual_insert is None:
            actual_insert = len(lines)

        lines.insert(actual_insert, QUARANTINE_FLAG + "\n")
        result["actions"].append("added_flag")

    filepath.write_text("".join(lines), encoding="utf-8")
    return result


def main():
    print(f"Adding quarantine markers to {len(LEGACY_RUNTIME_FILES)} files...")
    results = []
    for rel_path in LEGACY_RUNTIME_FILES:
        filepath = NEOCORTEX_ROOT / rel_path
        if not filepath.exists():
            results.append({"file": rel_path, "actions": ["FILE_NOT_FOUND"]})
            continue
        result = add_quarantine_markers(filepath)
        results.append(result)

    print("\n=== Results ===")
    for r in results:
        print(f"  {r['file']}: {', '.join(r['actions'])}")

    already = sum(1 for r in results if "already_marked" in r["actions"])
    modified = sum(1 for r in results if "already_marked" not in r["actions"]
                   and "FILE_NOT_FOUND" not in r["actions"])
    missing = sum(1 for r in results if "FILE_NOT_FOUND" in r["actions"])
    print(f"\nSummary: {already} already marked, {modified} modified, {missing} missing")


if __name__ == "__main__":
    main()
