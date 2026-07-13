# Validation

## FACTS

| Command | Result |
|---|---|
| `python -m pytest tests/domains/execution_position/test_p46_1g_s1_async_dispatch.py -q -W error::RuntimeWarning` | `6 passed` |
| P46-1F + P46-1E + P46-1D focused tests | `44 passed` |
| E2E order placement + recovery + startup/shutdown subset | `47 passed, 14 skipped` |
| `python -m pytest tools/deepseek-terminal-agent/tests -q` | `578 passed, 13 skipped`; three development-config warnings |
| `python -m pytest tests/domains/execution_position -q --tb=short` | Suite stopped after no progress at `55%`; last visible file was `test_guardian_pre_close_cleanup_package11.py`. No pass claim. |
| `python -m pytest tests/domains/execution_position/test_guardian_pre_close_cleanup_package11.py -q --tb=short` | `12 passed in 24.45s`; the isolated file does not reproduce the suite-level stall. |
| `python -m scripts.p46_1g_s1_canonical_venue_proof` | Failed closed before submit: `SOFT_LIMIT_BELOW_CLIP_MIN`; final venue reads clean. |
| `git diff --check` | Recorded in final package closure. |

## INFERENCES

- Unit/integration coverage validates the dispatch repair; it does not substitute for venue lifecycle proof.

## ASSUMPTIONS

- Test selections cover the runtime surfaces touched by this narrow patch.

## UNKNOWNS

- Skipped tests provide no evidence. The cause of the broad suite-level stall after 55% is unproven.
