import glob
import os

print("--- Looking for md_amr in all logs ---")
count = 0
found = False

for log_file in glob.glob("logs/*.log*"):
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "md_amr" in line:
                    print(f"[{os.path.basename(log_file)}] {line.strip()}")
                    count += 1
                    found = True
                    if count >= 30:
                        break
    except Exception:
        pass
    if count >= 30:
        break

if not found:
    print("No references to md_amr found in any logs.")
