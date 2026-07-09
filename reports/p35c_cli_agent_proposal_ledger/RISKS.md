# Risks

- No UI panel was added in P35C; this is API/store foundation only.
- Proposal status transition routes are not implemented.
- Store is filesystem JSON; no cross-process index lock beyond atomic file writes.
- GET by proposal id scans session proposal directories.
- trade_intent_draft payload remains flexible metadata, with execution-like fields blocked by key validation.
