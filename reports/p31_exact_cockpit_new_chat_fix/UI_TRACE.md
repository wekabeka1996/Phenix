# UI Trace

We traced the active session visibility state in the user interface during our validation checks.

## UI Elements Involved
1.  **Menu Trigger**:
    - Selector: `#simple-menu-new` (located in the topbar dropdown menu of Simple Chat Mode).
    - Event: When clicked, it calls `createSession()` by forwarding the trigger to `#new-session-btn`.
2.  **Session List Container**:
    - Selector: `#simple-session-list` (the body of the left drawer panel).
    - Expected Behavior: Renders `.session-row` buttons for all active sessions in the database.
3.  **Active Session Header Title**:
    - Selector: `#simple-chat-session-title` (located in the topbar header).
    - Expected Behavior: Displays the name/title of the active session.

## Observed Flow Trace
1.  **Page Boot**:
    - Simple Chat Mode renders the left drawer `#simple-chat-left-drawer` in a hidden state.
    - Title in header displays default placeholder text: **"Нова сесія"**.
    - Left drawer lists no sessions and displays: *"Тут з’являться елементи керування чатами та сесіями."*
2.  **Click "Нова сесія"**:
    - User expands the action menu and clicks `#simple-menu-new`.
    - Event handler triggers `createSession()`, which sends `POST /chat/sessions` to the backend.
    - Server returns 201 Created and unshifts the new session into `state.sessions`.
    - `loadSession()` is automatically called with the new session ID.
3.  **Refreshed UI Render**:
    - `renderSessions()` executes. It successfully selects `#simple-session-list` and injects the session row button:
      `<button type="button" class="session-row is-active" data-session-id="...">...`
    - `loadSession()` updates the title header `#simple-chat-session-title` to display **"New Session"** (or custom session title).
    - The active session is now fully visible and interactive in the user interface.
