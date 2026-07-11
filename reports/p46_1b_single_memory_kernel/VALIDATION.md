# Validation

## FACTS

Commands run:

```powershell
python -m pytest tests/test_single_memory_kernel.py -q
python -m pytest tests/test_single_memory_kernel.py tests/test_agent_trading_memory.py tests/test_memory_atoms.py tests/test_decision_ledger.py tests/test_context_builder.py -q
python -m compileall -q src/deepseek_terminal_agent/sessions/collective_memory.py src/deepseek_terminal_agent/sessions/collective_memory_models.py
rg -n "AgentMemoryLifecycle|SessionStore|MemoryAtomStore|DecisionLedger|Binance|exchange|qty|quantity|notional|leverage|os\.environ|getenv" src/deepseek_terminal_agent/sessions/collective_memory.py
git diff --check
```

Results:

- focused: `6 passed`;
- focused plus adjacent memory/context suites: `29 passed`;
- compile: passed;
- forbidden import/authority scan: no matches;
- whitespace validation: passed.

Covered: append/order, duplicate rejection, missing/mismatched identity, reopen recovery, deterministic summary/carryover, event/command/source preservation, explicit storage/config, and no competing store instantiated by canonical API.

## INFERENCES

- Unit proof supports the selected kernel contract but does not prove full runtime cutover or multiprocess durability.

## ASSUMPTIONS

- CI uses a compatible Python/Pydantic environment.

## UNKNOWNS

- Full repository suite and external runtime were not required or run.

