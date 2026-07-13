# Validation

| Command | Result |
|---|---|
| `python -m pytest tests/domains/shadow_telemetry/test_p46_2d_s1_authority_query.py -q` | 6 passed |
| focused S1/P46-2D/P46-2C/config set | 34 passed |
| `python -m pytest tests/domains/shadow_telemetry -q` | 139 passed |
| `python -m pytest tools/deepseek-terminal-agent/tests -q` | 578 passed, 13 skipped; skips not counted as proof |
| P46-1D/1E/1F/S1/S2 regression selection | 71 passed, 1 pre-existing proof-target mismatch (`11.0` vs old `10.0`) |
| Cockpit `npm run test:trading-agent` | 44 passed, 1 allowed known EZE failure |
| Cockpit `npm run lint` | passed |
| Cockpit `npm run build` | passed |
| `git diff --check` | passed before reports |
| `python -m ruff check ...` | not run: `ruff` is not installed in this environment |

No skipped test is counted as proof. No provider, FSM execution, adapter network, exchange, Testnet, or mainnet call occurred.
