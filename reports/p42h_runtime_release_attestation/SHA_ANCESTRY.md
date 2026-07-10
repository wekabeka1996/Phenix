# SHA ANCESTRY VERIFICATION

This document verifies the git history, ancestry checks, and immutable code tags for the release.

---

## 1. Verified Commit Hashes

- **Runtime Code Commit SHA**: `e82ceff877ba83f7affdb8659b2ba2b38d76e09c`
  - *Title*: "P42 Release: Add unified runtime documentation reports and test suite smoke verification"
  - *Role*: The last commit containing runtime source code, configs, or test suites before report additions.
- **Immutable Code Tag**: `p42g-runtime-code-v1`
  - Created pointing directly to `e82ceff877ba83f7affdb8659b2ba2b38d76e09c`.
- **Checkout HEAD SHA**: The commit containing the final P42H reports (which is a descendant child of `e82ceff877ba83f7affdb8659b2ba2b38d76e09c`).

---

## 2. Ancestry & Diff Validation

- **Ancestry Check**:
  ```powershell
  git merge-base --is-ancestor e82ceff877ba83f7affdb8659b2ba2b38d76e09c HEAD
  ```
  Exits with code `0`, proving `e82ceff8` is a direct ancestor of our final checkout HEAD.
- **Diff Bound Check**:
  ```powershell
  git diff --name-only e82ceff877ba83f7affdb8659b2ba2b38d76e09c..HEAD
  ```
  Returns only paths located under `reports/` (such as `reports/p42g_unified_dual_agent_runtime/RUN_READY_GATE.md` and `reports/p42h_runtime_release_attestation/*`), ensuring zero modification in any source files under `apps/`, `config/`, `tools/`, or `tests/`.
- **Verification Rule**: Any source file difference after the `runtime_code_sha` results in a preflight block, causing the runner to fail closed.
