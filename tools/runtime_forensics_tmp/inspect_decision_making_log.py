from pathlib import Path

path = Path("logs/domain_decision_making.log")
if not path.exists():
    print("Log not found")
else:
    print(f"Log: {path.name} (Size: {path.stat().st_size} bytes)")
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
        print(f"Total lines: {len(lines)}")
        for l in lines[-20:]:
            print(l.strip())
