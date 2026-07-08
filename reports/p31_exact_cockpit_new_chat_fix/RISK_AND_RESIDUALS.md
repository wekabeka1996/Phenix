# Risk and Residual Analysis

## Identified Risks
1.  **Empty Session List rendering in Simple Chat Mode**:
    - **Risk**: If there are no sessions, the left drawer in simple chat mode shows *"Тут з’являться елементи керування чатами та сесіями."* which matches the expected behavior.
    - **Mitigation**: Once a session is created or loaded, it correctly replaces the empty state placeholder with interactive session buttons.
2.  **FastAPI startup missing project capsule**:
    - **Risk**: Running the app inside the sandboxed workspace requires `config/project_capsule.yaml` to be present at the workspace root directory.
    - **Mitigation**: We copied the default project capsule file to `config/project_capsule.yaml` to ensure the server launches without `FileNotFoundError`.
3.  **Local Storage key consistency**:
    - **Risk**: Drawer toggles and layouts are stored under local storage namespaces.
    - **Mitigation**: Toggles operate independently without resetting other workspace layout structures, preserving custom layout presets.

## Residuals
*   All strategy variables and execution routes in the Aurora trading framework remain untouched.
*   Zero live orders or market accesses were performed during this fix.
