# Semantic Recall Benchmark

Command:

```powershell
python scripts/benchmark_semantic_recall.py --output C:\tmp\p41y_semantic_recall.json
```

Corpus: 12 deterministic facts plus 320 non-semantic market updates; 339 evidence events total. Facts cover position open/close, risk warning, instruction version, feature trust, agent disagreement, two order intents, FSM rejection, dispatch-in-doubt, and recovery resolution.

| Surface | Exact recall | Chronology | Agent | Symbol | Instruction | Critical | False | Missing refs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A raw evidence | 100% | pass | 100% | 100% | pass | 100% | 0 | 0 |
| B active context | 100% | pass | 100% | 100% | pass | 100% | 0 | 0 |
| C checkpoint + retrieval | 100% | pass | 100% | 100% | pass | 100% | 0 | 0 |
| D carryover bundle | 100% | pass | 100% | 100% | pass | 100% | 0 | 0 |

- Active context: 7,859 estimated tokens.
- Checkpoint source refs: 339/339.
- LLM judge: not used.
- Compression ratio: not used as semantic-quality evidence.

Every semantic fact has at least one source reference resolving to an immutable arena event. The result applies to structured, explicitly recorded facts only.
