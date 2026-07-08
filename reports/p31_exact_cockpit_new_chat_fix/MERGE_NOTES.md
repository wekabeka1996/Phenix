# Merge Notes

## Verification Status
- Both custom tests (`test_simple_chat_polish.py` and `test_frontend_cockpit.py`) validate layout state changes and passed successfully.
- Code compiles without syntax warnings.

## Merging Steps
1.  Verify target branch is clean.
2.  Switch to `main` and execute merge:
    `git merge p31-new-chat-fix`
3.  Ensure `config/project_capsule.yaml` is carried over, as it is required at the workspace root to prevent FastAPI startup failures.
4.  No migrations or database changes are required.
