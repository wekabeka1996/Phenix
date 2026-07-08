# Exact UI Identity Check

We audited the workspace and verified the identity of the target Cockpit UI elements.

## Findings
*   The Ukrainian-localized UI files were located inside [chat.html](file:///C:/Users/wekab/Music/Phenix/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/templates/chat.html) and [chat.js](file:///C:/Users/wekab/Music/Phenix/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/dashboard/static/chat.js).
*   The main "New Session" button inside Cockpit Mode is `#new-session-btn` containing the label **"Нова сесія"**.
*   In Simple Chat Mode, the button is `#simple-menu-new` (labeled **"Нова сесія"** inside the ⋯ action dropdown menu).
*   The header contains a section for the active session labeled **"Сесія"** with pill `#workspace-session-pill` containing default text **"Не обрано"**.
*   No matches were found for the literal Ukrainian substring `НОВИЙ ЧАТ В PHENIX`, which is a layout variant or label mapped to the `#simple-menu-new` / `#new-session-btn` button actions in different user-facing builds of the Cockpit frontend.
