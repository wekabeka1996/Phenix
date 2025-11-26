"""
Detailed analysis of ERROR and WARNING signatures for LOG AUDIT.
Reads JSON and displays critical errors related to TP/SL, duplicates, and race conditions.
"""

import json
from pathlib import Path

# Load raw data
json_path = Path("docs/EXEC_R2_LOG_ERRORS_RAW.json")
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

errors = data['errors']
warnings = data['warnings']

print("=" * 100)
print("CRITICAL ERROR ANALYSIS - Focus on TP/SL, Duplicates, Race Conditions")
print("=" * 100)
print()

# Categories
duplicate_errors = []
bracket_errors = []
timeout_errors = []
state_errors = []
other_errors = []

for i, err in enumerate(errors, 1):
    sig_lower = err['signature'].lower()
    
    if 'duplicate' in sig_lower or '-4116' in err['signature']:
        duplicate_errors.append((i, err))
    elif 'bracket' in sig_lower or 'tp' in sig_lower or 'sl' in sig_lower:
        bracket_errors.append((i, err))
    elif 'timeout' in sig_lower or 'adapter' in sig_lower:
        timeout_errors.append((i, err))
    elif 'state' in sig_lower or 'divergence' in sig_lower or 'race' in sig_lower:
        state_errors.append((i, err))
    else:
        other_errors.append((i, err))

# Print categories
print(f"📊 КАТЕГОРИЗАЦІЯ {len(errors)} ERROR SIGNATURES:")
print(f"   🔴 Duplicate errors: {len(duplicate_errors)}")
print(f"   🟠 Bracket/TP/SL errors: {len(bracket_errors)}")
print(f"   🟡 Timeout/Adapter errors: {len(timeout_errors)}")
print(f"   🟣 State/Divergence errors: {len(state_errors)}")
print(f"   ⚪ Other errors: {len(other_errors)}")
print()

# Detail each category
if duplicate_errors:
    print("=" * 100)
    print("🔴 DUPLICATE ERRORS (потенційна причина 2 TP на BTC)")
    print("=" * 100)
    for idx, err in duplicate_errors:
        print(f"\n[E-{idx:02d}] Count: {err['count']}")
        print(f"  Logger: {err['logger']}")
        print(f"  Sig: {err['signature']}")
        print(f"  Sample: {err['sample_line'][:200]}...")
    print()

if bracket_errors:
    print("=" * 100)
    print("🟠 BRACKET/TP/SL ERRORS (потенційна причина SOL без TP/SL)")
    print("=" * 100)
    for idx, err in bracket_errors:
        print(f"\n[E-{idx:02d}] Count: {err['count']}")
        print(f"  Logger: {err['logger']}")
        print(f"  Sig: {err['signature']}")
        print(f"  Sample: {err['sample_line'][:200]}...")
    print()

if timeout_errors:
    print("=" * 100)
    print("🟡 TIMEOUT/ADAPTER ERRORS (потенційна причина повільної роботи)")
    print("=" * 100)
    for idx, err in timeout_errors:
        print(f"\n[E-{idx:02d}] Count: {err['count']}")
        print(f"  Logger: {err['logger']}")
        print(f"  Sig: {err['signature']}")
        print(f"  Sample: {err['sample_line'][:200]}...")
    print()

if state_errors:
    print("=" * 100)
    print("🟣 STATE/DIVERGENCE ERRORS (race conditions)")
    print("=" * 100)
    for idx, err in state_errors:
        print(f"\n[E-{idx:02d}] Count: {err['count']}")
        print(f"  Logger: {err['logger']}")
        print(f"  Sig: {err['signature']}")
        print(f"  Sample: {err['sample_line'][:200]}...")
    print()

print("=" * 100)
print("TOP 10 WARNING PATTERNS (high frequency)")
print("=" * 100)

for i, warn in enumerate(warnings[:10], 1):
    print(f"\n[W-{i:02d}] Count: {warn['count']:5d}")
    print(f"  Logger: {warn['logger']}")
    print(f"  Sig: {warn['signature'][:120]}")

print()
print("=" * 100)
print("NEXT STEPS:")
print("=" * 100)
print("1. Map each ERROR signature to source code (git grep)")
print("2. Analyze timing of duplicate errors vs TP/SL creation")
print("3. Check if watchdog/healing runs concurrently with bracket creation")
print("4. Verify idempotency logic in _make_bracket_client_order_id")
print("5. Look for missing locks/semaphores in _apply_bracket_plan")
print("=" * 100)
