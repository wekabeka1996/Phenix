# PKG6 FINAL REPORT

## Decision

PKG-6 ends as an honest rejection package.

No new alpha winner is promoted from the bounded search on the hardened ETH+BTC proxy.

## What Was Proven

1. The PKG-5 hardened proxy harness remained valid.
2. Fail-closed fallback rejection remained clean in smoke, recovered March trials, and Jan/Feb sanity windows.
3. The v1 anchor stayed the correct optimization reference.
4. Completed March search runs did not produce a distinct candidate beyond the v1 anchor.

## Key Evidence

- Smoke validation: `20260314_180946`
- March v1 anchor: `20260314_172657`
- Recovered completed March search runs: `20260314_181857`, `20260314_183705`, `20260314_192436`, `20260314_201516`, `20260314_203520`
- January sanity window: `20260314_215848`
- February sanity window: `20260314_220436`

All recovered completed March search runs shared the same resolved config hash as the v1 anchor and therefore do not constitute honest distinct candidates.

## Why This Is A Rejection And Not A Failure To Finish

The package was finished end-to-end:

- bounded search was actually launched,
- completed March runs were recovered and classified,
- the over-budget live study was terminated instead of being misrepresented,
- candidate selection was performed honestly,
- Jan/Feb sanity windows were executed for the surviving reference only,
- final artifacts and reports were written.

What the package rejected was the existence of a new alpha hint, not the ability to measure the surface.

## Operational Outcome

The best evidence-bound reference remains the v1 overlay on the hardened ETH+BTC proxy.

If future work is attempted, the next package should first make long-running search orchestration persist per-trial overlays and per-trial metadata before the end-of-study epilogue so completed trials can never collapse into unrecoverable duplicates after termination.