from pathlib import Path
import re

ROOT = Path(r"C:\Users\wekab\Music\Phenix")
LOG_DIR = ROOT / "logs"

def search_text_logs(keyword):
    print(f"\nSearching for '{keyword}' in text logs...")
    found = 0
    for p in LOG_DIR.glob("*.log*"):
        try:
            with open(p, 'r', encoding='utf-8', errors='replace') as fh:
                for idx, line in enumerate(fh, 1):
                    if keyword in line:
                        print(f"Found in {p.name} Line {idx}: {line.strip()[:200]}")
                        found += 1
                        if found >= 5:
                            return
        except Exception as e:
            pass

search_text_logs("trend")
search_text_logs("run_length")
search_text_logs("pm_norm")
