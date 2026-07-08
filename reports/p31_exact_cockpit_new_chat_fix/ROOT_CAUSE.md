# Root Cause Analysis

## Classification
`post_201_ui_not_refreshed` (plus a minor layout integration oversight in Simple Chat Mode).

## Explanation
1.  **Cockpit Mode**:
    - When `createSession()` executes, it unshifts the newly created session into the frontend's local `state.sessions` array and then calls `loadSession()`.
    - `loadSession()` fetches the session details and calls `renderSessions()`, which updates `#session-list` successfully.
    - If the user was in Cockpit mode, the session list was refreshed. However, if any network exception or profile validation failure occurred, `loadSession()` was aborted, causing `renderSessions()` to never run.
2.  **Simple Chat Mode**:
    - In Simple Chat Mode, the left drawer (`simple-chat-left-drawer`) acts as the primary chat control panel containing the Ukraine-localized placeholder message: *"Тут з’являться елементи керування чатами та сесіями."*.
    - However, `chat.js` completely lacked any reference to the drawer's body class/id or elements, meaning **the session list was never rendered inside Simple Chat Mode**.
    - Furthermore, `simple-chat-session-title` (which should display the loaded active session name in simple mode) was never selected or updated by `loadSession()`, keeping the interface state completely static on "Нова сесія" regardless of backend session state.
