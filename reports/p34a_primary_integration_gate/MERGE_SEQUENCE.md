# Merge Sequence

The candidate branches were merged sequentially using no-ff commits.

## Sequence Details

1.  **Merge 1: Simple Chat New Session UI Fix**
    - Branch: `p31a-new-chat-primary-20260708`
    - Command: `git merge --no-ff -m "Merge branch p31a-new-chat-primary-20260708..."`
    - Result: Clean merge (Ort strategy). Added UI elements for Simple Chat drawer switches.
2.  **Merge 2: Smoke Harness Configuration**
    - Branch: `p31b-smoke-primary-20260708`
    - Command: `git merge --no-ff -m "Merge branch p31b-smoke-primary-20260708..."`
    - Result: Clean merge. Updates project capsule smoke settings.
3.  **Merge 3: Attachment Ingestion API**
    - Branch: `p32b-attachments-api-primary-20260708`
    - Command: `git merge --no-ff -m "Merge branch p32b-attachments-api-primary-20260708..."`
    - Result: Clean merge. Registers attachment file ingest routes and validations.
4.  **Merge 4: Session Memory Repair**
    - Branch: `origin/p33b-memory-repair-secondary-20260708`
    - Command: `git merge --no-ff -m "Merge branch origin/p33b-memory-repair-secondary-20260708..."`
    - Result: Clean merge. Validates Pydantic ge constraints and fail-closed store fallbacks.
