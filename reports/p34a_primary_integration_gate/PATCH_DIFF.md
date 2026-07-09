# Patch Diff

Here is the diff statistics of the unified integrated branch `agent-hub-integrated-2026-07-09` compared to baseline `agent-hub-sync-2026-07-08`:

```
 apps/reference/domains/agent_bridge/routes.py      |  11 +-
 .../agent_bridge/schemas/session_context_v1.json   |   7 +-
 .../agent_bridge/session_context_contract.py       |  24 ++-
 .../agent_bridge/session_context_read_model.py     |   8 +-
 .../p31_cockpit_browser_smoke_harness/REPORT.md    |   6 +-
 reports/p31_exact_cockpit_new_chat_fix/REPORT.md   |  30 ++--
 reports/p31_exact_cockpit_new_chat_fix/UI_TRACE.md |  30 ++++
 .../API_CONTRACT.md                                |  53 ++++++
 .../PATCH_DIFF.md                                  |  25 +++
 .../p32_session_attachment_api_routes/REPORT.md    |  48 ++++++
 reports/p32_session_attachment_api_routes/RISKS.md |   7 +
 .../VALIDATION.md                                  |  25 +++
 .../PATCH_DIFF.md                                  | Bin 0 -> 24648 bytes
 .../POLICY_REPAIR.md                               |  26 +++
 .../REMAINING_GAPS.md                              |  11 ++
 .../p33_shared_session_context_repair/REPORT.md    |  21 +++
 .../ROOT_PATH_DECISION.md                          |  20 +++
 .../VALIDATION.md                                  |  41 +++++
 .../p34d_secondary_p33_publication/PUSH_RESULT.md  |  43 +++++
 .../REMOTE_REF_PROOF.md                            |  30 ++++
 reports/p34d_secondary_p33_publication/REPORT.md   |  45 +++++
 reports/p34d_secondary_p33_publication/RISKS.md    |  23 +++
 .../p34d_secondary_p33_publication/VALIDATION.md   |  42 +++++
 .../agent_bridge/test_session_context_contract.py  |  77 +++++++--
 .../src/deepseek_terminal_agent/dashboard/app.py   |  92 ++++++++++-
 .../sessions/attachments.py                        | 168 +++++++++++++++++++
 .../sessions/context_builder.py                    |  28 ++++
 .../tests/test_attachments_api.py                  | 181 +++++++++++++++++++++
 28 files changed, 1077 insertions(+), 45 deletions(-)
```
