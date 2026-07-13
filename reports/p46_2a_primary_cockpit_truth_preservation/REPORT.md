# P46-2A Primary Cockpit Truth and Preservation

## FACTS

- Task: `P46_2A_PRIMARY_COCKPIT_TRUTH_PRESERVATION_AND_PORT_MAP`.
- Phenix report branch starts at `2caae9d3f11987f8fe089003eeb0ad7e7e04abe9`; required ancestors `3848890e`, `4bf55d16`, `605d66c8`, and `a68d8749` are present.
- The current canonical execution branch was observed at `5fb8b928923d6a2a14fca84d283548b92777ac45`, synchronized `0/0` with origin, with only the known untracked forensic script.
- GitHub `wekabeka1996/deepseek-agent-os` branch `workspace-changes` resolves to `15e63ce57a5be75b6f08a594259ba517428cff1f`.
- The only additional primary source-bearing Cockpit found is the non-Git snapshot `C:\Users\wekab\Music\deepseek-agent-os-workspace-changes`.
- Byte manifests contain 422 baseline and 432 snapshot source/config/test/doc files. Normalized comparison finds 10 snapshot-only files, 4 substantive modifications, 418 line-ending-only differences, and 0 baseline-only files.
- Exactly those 14 substantive files were preserved on `p46-preserve/primary-cockpit-preintegration-20260713`.
- Cockpit commits `7862947` and `b9726ac` were pushed; the preservation branch is synchronized with origin.
- `npm run lint`, 9 focused Agent Feed/Dry Run tests, and `npm run build` passed. No provider, Testnet, or exchange call was made.

## INFERENCES

- The non-Git snapshot is a later working copy of the GitHub baseline, not an independent Cockpit architecture.
- The 14-file package is bounded read-only projection work and can be reviewed independently of the older V1 trading service.
- Cockpit local SQLite is presentation/orchestration state, not Phenix trading, venue, memory, session, lease, or lifecycle authority.

## ASSUMPTIONS

- The active `p2-agent-feed-observation-host.ts` process was launched from the primary snapshot because that script exists only there among discovered candidates.
- No source-bearing Cockpit exists outside the reasonable project roots searched under `C:\Users\wekab\Music`.

## UNKNOWNS

- Live end-to-end behavior of the preserved React panel was not tested because the active process was not disturbed.
- Provider billing attribution and parent/subagent shared budgets are not unified.
- V2 Cockpit execution integration remains unimplemented.

## Verdict

`P46_2A_PRIMARY_COCKPIT_TRUTH_AND_PRESERVATION_VALIDATED`

This verdict records repository truth, preservation, validation, and a selective-port map. It does not claim Cockpit runtime integration or execution authority migration.
