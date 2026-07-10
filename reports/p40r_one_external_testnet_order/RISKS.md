# Risks (P40R Rerun)

## 1. Local Commit SHA Divergence
- **Risk**: Local HEAD SHA (`9af369b7`) differs from the pre-push SHA (`e443549be4d3d81b3793df6034e405a30a84e27f`) recorded inside `RUN_READY_GATE.md` due to post-merge commits aligning test harness schema and reports.
- **Mitigation**: History inspection confirms that `9af369b7` is the exact tip of `origin/p40-runtime-order-proof-integrated-primary-20260710`.

## 2. Shadow Mode stub limits
- **Risk**: Since `ExchangeACL` shadow mode returns immediate placement stubs, live exchange networking errors or timeouts were not triggered.
- **Mitigation**: Fail-closed guards inside FSM gate audit layers verify descriptor environments continuously, preventing live domain requests.
