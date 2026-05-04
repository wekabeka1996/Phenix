# COCKPIT_CENTRAL_WORKSPACE_INVENTORY_v1

## 1. Current DOM Map

| Section Name | Selector/ID | Visible Title | Body Container | JS Handlers | CSS Classes | Test Assertions |
|--------------|-------------|---------------|----------------|-------------|-------------|-----------------|
| Scenarios | `.workspace-section--scenarios` | Сценарії / швидкі кнопки | `#scenario-rail-body` | `renderScenarios` | `workspace-section`, `collapsible-card` | `test_scenario_buttons_bar_exists` |
| Chat Stream | `.workspace-section--chat` | Чат-потік | `#chat-thread-panel` | `renderChatStream` | `workspace-section`, `collapsible-card`, `thread-card` | `test_ukrainian_agent_workspace` |
| Work Trace | `.workspace-section--trace` | Міркування / хід роботи | `#reasoning-body` | `renderWorkTrace`, `reasoning-toggle-btn` | `workspace-section`, `collapsible-card`, `reasoning-card` | `test_ukrainian_decision_ledger` |
| Result | `.workspace-section--result` | Результат / статус | `#output-panel-body` | `renderResult`, `result-copy-btn` | `workspace-section`, `collapsible-card`, `output-panel-card` | `test_ukrainian_evidence_bundle` |

## 2. Current Content Map

### Scenarios
- **Rendered:** A bar of buttons (`#scenario-buttons-bar`) grouped by category (Код, Тести, Логи, Звіти) and a preview panel (`#scenario-preview-panel`).
- **Data Source:** Hardcoded in HTML or partially dynamic from session metadata.
- **Buttons:** scenario buttons, "Вставити в composer", "Швидкий запуск", "Показати source".
- **Mechanics:** Vertical resize, collapse, move up/down.

### Chat Stream
- **Rendered:** A list of chat messages (`#chat-thread`) and a placeholder for subagents.
- **Data Source:** `state.currentSession.timeline`.
- **Buttons:** None inside body (usually).
- **Mechanics:** Vertical resize, collapse, move up/down.

### Work Trace
- **Rendered:** A tree of reasoning events (`#reasoning-tree`) and a mode switcher.
- **Data Source:** `state.currentSession.timeline` (events filtered by type).
- **Buttons:** "Компактний", "Робочий", "Детальний trace".
- **Mechanics:** Vertical resize, collapse, toggle mode.

### Result
- **Rendered:** A status badge, a text summary, a preformatted output box, and action buttons.
- **Data Source:** `state.currentSession.session.status` and last response.
- **Buttons:** "Copy", "Memory", "До trace", "Артефакти".
- **Mechanics:** Vertical resize, collapse.

## 3. Dependency Map

- **JS (`chat.js`):** 
  - `renderSessionDetail` calls individual section renderers.
  - `document.getElementById` for each body container ID.
  - Event listeners for scenario buttons and action buttons.
- **Tests:** `tests/test_frontend_cockpit.py` checks for specific IDs and text content (e.g., `Сценарії`, `Чат-потік`).
- **CSS (`dashboard.css`):**
  - Layout definitions for `.workspace-section`.
  - Specific styling for `.reasoning-body`, `.chat-thread`, etc.

## 4. Cleanup Plan

- **Cleared:** All children of the 4 body containers (`#scenario-rail-body`, `#chat-thread-panel`, `#reasoning-body`, `#output-panel-body`).
- **Preserved:**
  - Section headers, titles, and control buttons (collapse, menu).
  - Main structural containers and their IDs for JS compatibility.
  - Layout-critical classes.
- **Compatibility:** JS functions will still find the elements but will find them empty. I will add guards to prevent JS from re-rendering content into these sections in Cockpit mode if necessary.

## 5. Risks

- **Null-reference:** Minimal, as the container elements themselves remain.
- **Test breakage:** Tests that assert on *specific buttons* (like `Зібрати контекст`) will fail. These will need to be updated or mocked.
- **Layout/Scroll:** Empty sections might collapse visually if not given a min-height or placeholder. I will ensure they look like "empty shells".
- **Mode Isolation:** MUST ensure `simple-chat-shell` and Board Mode panels remain untouched.
