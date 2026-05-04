import json
import os
from collections import defaultdict

log_dir = "logs/judge_experts"
symbol = "BTCUSDT"
date_str = "2026-04-26"

plan_file = os.path.join(log_dir, f"shadow_entry_plan_{symbol}_{date_str}.jsonl")
verdict_file = os.path.join(log_dir, f"verdict_{symbol}_{date_str}.jsonl")
chamber_file = os.path.join(log_dir, f"chamber_{symbol}_{date_str}.jsonl")

# Load verdicts
verdicts = {}
if os.path.exists(verdict_file):
    with open(verdict_file, "r") as f:
        for line in f:
            v = json.loads(line)
            verdicts[v["cycle_key"]] = v

# Load plans
plans = []
if os.path.exists(plan_file):
    with open(plan_file, "r") as f:
        for line in f:
            plans.append(json.loads(line))

# Load chambers
chambers = {}
if os.path.exists(chamber_file):
    with open(chamber_file, "r") as f:
        for line in f:
            c = json.loads(line)
            chambers[c["cycle_key"]] = c

print("=======================================")
print(f"STEP 5: Count-level sanity for {symbol}")
print("=======================================")

num_plans = len(plans)
distinct_cycles = len(set(p["cycle_key"] for p in plans))
plan_cycles_in_verdict = sum(1 for p in plans if p["cycle_key"] in verdicts)
plan_cycles_without_verdict = sum(1 for p in plans if p["cycle_key"] not in verdicts)

actionable_counts = defaultdict(int)
verdict_counts = defaultdict(int)
tier_counts = defaultdict(int)
missing_price_ref = 0
suppressed_reasons = defaultdict(int)

for p in plans:
    actionable_counts[p["actionable"]] += 1
    verdict_counts[p["final_entry_verdict"]] += 1
    tier_counts[p["confidence_tier"]] += 1
    if p["entry_price_ref"] is None:
        missing_price_ref += 1
    if p["suppressed"]:
        suppressed_reasons[p["suppression_reason"]] += 1

print(f"Number of shadow_entry_plan rows: {num_plans}")
print(f"Number of distinct cycle_key: {distinct_cycles}")
print(f"Number of matching verdict cycle_key: {plan_cycles_in_verdict}")
print(f"Number of plan rows without matching verdict: {plan_cycles_without_verdict}")
print(f"Actionability distribution: {dict(actionable_counts)}")
print(f"Verdict distribution inside plan rows: {dict(verdict_counts)}")
print(f"Tier distribution: {dict(tier_counts)}")
print(f"Missing/invalid price_ref count: {missing_price_ref}")
print(f"Suppressed count by reason: {dict(suppressed_reasons)}")

print("\n=======================================")
print(f"STEP 4: One-symbol linked row audit ({symbol})")
print("=======================================")

if num_plans > 0:
    target_cycle = plans[0]["cycle_key"]
    print(f"Target cycle_key: {target_cycle}")
    
    # Chamber
    if target_cycle in chambers:
        print("\nCHAMBER:")
        c = chambers[target_cycle]
        print(f"  chamber_id: {c.get('chamber_id')}")
        print(f"  quorum: {c.get('quorum_reached')} ({c.get('active_experts')}/{c.get('solicited_experts')})")
        print(f"  consensus: {c.get('consensus')}")
    else:
        print("  Chamber not found")
        
    # Verdict
    if target_cycle in verdicts:
        print("\nVERDICT:")
        v = verdicts[target_cycle]
        print(f"  verdict_id: {v.get('verdict_id')}")
        print(f"  entry_verdict: {v.get('entry_verdict')}")
        print(f"  confidence: {v.get('confidence')}")
        print(f"  reasoning: {v.get('reasoning')}")
    else:
        print("  Verdict not found")
        
    # Plans for this cycle
    print("\nSHADOW PLANS:")
    cycle_plans = [p for p in plans if p["cycle_key"] == target_cycle]
    for p in cycle_plans:
        print(f"  tier: {p['confidence_tier']} (actionable={p['actionable']}, suppressed={p['suppressed']})")
        if p['actionable']:
            print(f"    limit_price: {p.get('limit_price')} (offset: {p.get('limit_offset_bps')} bps)")
            print(f"    tp_price: {p.get('tp_price')} ({p.get('tp_offset_pct')} pct)")
            print(f"    sl_price: {p.get('sl_price')} ({p.get('sl_offset_pct')} pct)")
            print(f"    risk_reward: {p.get('risk_reward')}")
            print(f"    shadow_invariants: auth={p.get('authority_mode')}, applied={p.get('applied')}, shadow_only={p.get('shadow_only')}")
else:
    print("No plans found to audit.")
