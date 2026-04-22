import os
import re
from collections import defaultdict

log_dir = r"C:\Users\user\Music\Phenix\logs"
pattern = re.compile(r"(WARNING|ERROR|CRITICAL)\s*\|(.*?)\|(.*)")

unique_logs = defaultdict(list)

for root, _, files in os.walk(log_dir):
    for file in files:
        if file.endswith(".log"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        match = pattern.search(line)
                        if match:
                            level = match.group(1).strip()
                            module = match.group(2).strip()
                            message = match.group(3).strip()
                            
                            # Normalize message by removing specific numbers to group duplicates
                            norm_msg = re.sub(r'\d+', 'X', message)
                            # Remove specific symbols if needed, but X is usually enough
                            
                            key = f"[{level}] {module} : {norm_msg}"
                            if len(unique_logs[key]) < 2:
                                unique_logs[key].append((path, message))
            except Exception as e:
                pass

for key, instances in unique_logs.items():
    print(f"=== {key} ===")
    print(f"  Example: {instances[0][1]}")
    print(f"  Found in: {', '.join(set(os.path.basename(p) for p, _ in instances))}")
    print()
