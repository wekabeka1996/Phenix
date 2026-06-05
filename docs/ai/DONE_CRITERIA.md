# Done Criteria

A task is DONE only when all of the following are true:

1. The objective was addressed within the stated scope.
2. Every major claim is evidence-linked.
3. Facts, inferences, assumptions, and unknowns are separated explicitly.
4. Uncertainty is localized rather than hidden.
5. Root cause is not confused with symptom.
6. Proposed changes are minimal, operationally justified, and bounded.
7. Validation is defined and, when execution work was performed, actually run.
8. Residual risk is stated explicitly.
9. A final REPORT following `docs/ai/AGENT_REPORT_SCHEMA.md` is provided.
10. If docs or passports were affected, they were updated to reflect current verified reality in scope.

## Additional rules for code changes
- Do not call something fixed without naming the validation path.
- Do not treat unit tests alone as proof for runtime-sensitive paths.
- If runtime proof is unavailable, say so explicitly.

## Additional rules for audits / reviews
- Do not claim historical or project-wide truth from narrow evidence.
- Mark any unresolved uncertainty as unproven rather than resolved.
