# Long Session Benchmark

Command:

```powershell
python scripts/benchmark_collective_memory.py --events 600 --output C:\tmp\p41x_benchmark.json
```

The script used an automatically deleted isolated temp root and generated both agents, four symbols, 30-second market updates, publications, explicit decisions, subagent reviews, order intents, risk warnings, instruction changes, private reflections, feature updates, portfolio reconciliation, and a checkpoint.

| Metric | Result |
|---|---:|
| configured market events | 600 |
| total raw evidence events | 664 |
| raw tokens | 146,810 estimate |
| active-context tokens | 11,008 estimate |
| configured active limit | 12,000 |
| checkpoint size | 784,491 bytes |
| active/raw token ratio | 0.07498 |
| critical retention | 22 / 22 |
| source-reference retention | 664 / 664 |
| checkpoint time | 0.178 s |
| recovery time | 0.070 s |
| replay | success |

Both agents' latest instruction version survived recovery. Five pending command records survived and were not dispatched. No semantic-quality claim is made from the ratio.
