with open("logs/domain_decision_making.log", "r", encoding="utf-8", errors="ignore") as f:
    for i, line in enumerate(f, 1):
        if "safety_gates" in line or "price_motion" in line or "nrr" in line or "config" in line or "gate" in line:
            print(f"Line {i}: {line.strip()[:200]}")
            if i > 1000:
                print("Truncated...")
                break
