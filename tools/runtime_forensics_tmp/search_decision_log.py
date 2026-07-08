import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("logs/domain_decision_making.log", "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f, 1):
        line_lower = line.lower()
        if "safety_gates" in line_lower or "price_motion" in line_lower or "nrr" in line_lower or "config" in line_lower:
            if "portfolio" not in line_lower and "calculated features" not in line_lower: # filter out noisy lines
                print(f"Line {i}: {line.strip()[:200]}")
