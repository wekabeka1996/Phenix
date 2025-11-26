import json

# Load the raw JSON
with open('docs/EXEC_R2_LOG_ERRORS_RAW.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=" * 80)
print("ERROR SIGNATURES (ALL 18)")
print("=" * 80)

for i, err in enumerate(data['errors'], 1):
    print(f"\n[E-{i:02d}] Count: {err['count']:4d}")
    print(f"      Logger: {err['logger']}")
    print(f"      Signature: {err['signature']}")
    print(f"      Sample: {err['sample_line'][:150]}...")

print("\n" + "=" * 80)
print("TOP 20 WARNING SIGNATURES")
print("=" * 80)

for i, warn in enumerate(data['warnings'][:20], 1):
    print(f"\n[W-{i:02d}] Count: {warn['count']:4d}")
    print(f"      Logger: {warn['logger']}")
    print(f"      Signature: {warn['signature'][:120]}")
