# RUN READY GATE SCHEMA

This document details the configuration schema fields for the release gate and the generated pre-submit gate records.

---

## 1. RUN_READY_GATE.md Schema Fields

The `reports/p42g_unified_dual_agent_runtime/RUN_READY_GATE.md` file defines:

- **runtime_code_sha**: The code-complete commit SHA (`c55489003d891bf8e0b223fa4e12391452f6eda1`).
- **release_branch**: The target git branch (`p42-dual-agent-runtime-integrated-primary-20260710`).
- **gate_schema_version**: Schema version (`2.0.0`).
- **allowed_post_runtime_paths**: List of directories or files allowed to change after `runtime_code_sha` (defaults to `reports/**` and `PRE_SUBMIT_GATE.json`).
- **required_source_diff_policy**: The validation diff policy (`strict_no_src_changes`).
- **allowed_agent**: `cli_agent_01` (Only Agent 2 is allowed to submit).
- **allowed_symbol**: `XRPUSDT` (Only XRPUSDT trades are allowed).
- **maximum_order_count**: The trade count limit (`1`).
- **environment**: Target exchange environment (`testnet`).
- **credentials_required**: Boolean status (`true`).
- **actual_checkout_sha_recorded_at_runtime**: Dynamic verification check (must match actual checkout HEAD).

---

## 2. PRE_SUBMIT_GATE.json Structure

When `verify_preflight` executes successfully, the runner outputs `PRE_SUBMIT_GATE.json` in the root directory:

```json
{
  "schema_version": "2.0.0",
  "checkout_sha": "c55489003d891bf8e0b223fa4e12391452f6eda1",
  "runtime_code_sha": "c55489003d891bf8e0b223fa4e12391452f6eda1",
  "verified_at": "2026-07-10T11:25:00.000000Z"
}
```

---

## 3. Self-Referential Check Avoidance

We explicitly avoid requiring the checkout `HEAD` SHA to match the `Integration SHA` inside the *same* commit. Since updating the SHA in a file modifies its contents, committing that modification changes the HEAD commit hash, making equality checks impossible without amending loops. Instead:
- We record `runtime_code_sha` (the code-complete hash) in the gate file.
- The runner verifies that `runtime_code_sha` is a git ancestor of `HEAD`, allowing report updates to modify `HEAD` hash without breaking validation.
