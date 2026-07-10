# SHA ANCESTRY VERIFICATION

This document verifies the git history, ancestry checks, and immutable code tags for the release.

---

## 1. Verified Commit Hashes

- **Runtime Code Commit SHA**: `c55489003d891bf8e0b223fa4e12391452f6eda1`
  - *Title*: "P42 Release: Add unified runtime documentation reports and test suite smoke verification"
  - *Role*: The last commit containing runtime source code, configs, or test suites before report additions.
- **Immutable Code Tag**: `p42g-runtime-code-v1`
  - Created pointing directly to `c55489003d891bf8e0b223fa4e12391452f6eda1`.
- **Checkout HEAD SHA**: The commit containing the final P42H reports (which is a descendant child of `c55489003d891bf8e0b223fa4e12391452f6eda1`).

---

## 2. Ancestry & Diff Validation

- **Ancestry Check**:
  ```powershell
  git merge-base --is-ancestor c55489003d891bf8e0b223fa4e12391452f6eda1 HEAD
  ```
  Exits with code `0`, proving `e82ceff8` is a direct ancestor of our final checkout HEAD.
- **Diff Bound Check**:
  ```powershell
  git diff --name-only c55489003d891bf8e0b223fa4e12391452f6eda1..HEAD
  ```
  Returns only paths located under `reports/` (such as `reports/p42g_unified_dual_agent_runtime/RUN_READY_GATE.md` and `reports/p42h_runtime_release_attestation/*`), ensuring zero modification in any source files under `apps/`, `config/`, `tools/`, or `tests/`.
- **Verification Rule**: Any source file difference after the `runtime_code_sha` results in a preflight block, causing the runner to fail closed.
