import re

with open('src/deepseek_terminal_agent/dashboard/static/chat.js', 'r', encoding='utf-8') as f:
    js = f.read()

# 1. Update BOARD_PANEL_KEYS
js = js.replace(
    "var BOARD_PANEL_KEYS = ['sessions', 'scenarios', 'chat', 'workTrace', 'result', 'composer', 'inspector', 'artifacts'];",
    "var BOARD_PANEL_KEYS = ['sessions', 'chat', 'inspector', 'artifacts'];"
)

# 2. Update BOARD_SECTION_PANEL_KEYS
js = js.replace(
    "var BOARD_SECTION_PANEL_KEYS = ['scenarios', 'chat', 'workTrace', 'result', 'composer'];",
    "var BOARD_SECTION_PANEL_KEYS = ['chat'];"
)

# 3. Add default layout for the new unified 'chat' board panel which represents central-workspace
# In createDefaultBoardLayoutState():
# It currently has sessions, scenarios, chat, workTrace, result, composer, inspector, artifacts
js = re.sub(
    r"scenarios:\s*\{[^}]+\},\s*chat:\s*\{[^}]+\},\s*workTrace:\s*\{[^}]+\},\s*result:\s*\{[^}]+\},\s*composer:\s*\{[^}]+\},",
    "chat: { x: workAreaX, y: 48, width: 800, height: 700, zIndex: 2, minimized: false, collapsed: false, visible: true, pinned: false },",
    js
)

# 4. In BOARD_PANEL_LIMITS
js = re.sub(
    r"scenarios:\s*\{[^}]+\},\s*chat:\s*\{[^}]+\},\s*workTrace:\s*\{[^}]+\},\s*result:\s*\{[^}]+\},\s*composer:\s*\{[^}]+\},",
    "chat: { minWidth: 400, minHeight: 300, maxWidth: 1600, maxHeight: 1200 },",
    js
)

# 5. In initPanelResize, add centralWorkspace handling
# Currently there is:
# } else if (target === 'rightInspector') {
# ...
# We need to add centralWorkspace
resize_handler = """
        } else if (target === 'rightInspector') {
          var newWidth = Math.max(0, startWidth - deltaX);
          document.documentElement.style.setProperty('--right-inspector-width', newWidth + 'px');
        } else if (target === 'centralWorkspace') {
          var newHeight = Math.max(200, startHeight + deltaY); // Allow resizing height
          document.documentElement.style.setProperty('--central-workspace-height', newHeight + 'px');
          state.layoutState.centralWorkspaceHeight = newHeight;
        }
"""
js = js.replace(
    "} else if (target === 'rightInspector') {\n          var newWidth = Math.max(0, startWidth - deltaX);\n          document.documentElement.style.setProperty('--right-inspector-width', newWidth + 'px');\n        }",
    resize_handler
)

# In layoutState structure:
js = js.replace(
    "leftNavWidth: 220,",
    "leftNavWidth: 220,\n      centralWorkspaceHeight: 0,"
)

js = js.replace(
    "layout.rightInspectorWidth = clampNumber(raw.rightInspectorWidth || 360, 0, 800, 360);",
    "layout.rightInspectorWidth = clampNumber(raw.rightInspectorWidth || 360, 0, 800, 360);\n    layout.centralWorkspaceHeight = clampNumber(raw.centralWorkspaceHeight || 0, 0, 2000, 0);"
)

js = js.replace(
    "document.documentElement.style.setProperty('--right-inspector-width', layout.rightInspectorWidth + 'px');",
    "document.documentElement.style.setProperty('--right-inspector-width', layout.rightInspectorWidth + 'px');\n    if (layout.centralWorkspaceHeight > 0) {\n      document.documentElement.style.setProperty('--central-workspace-height', layout.centralWorkspaceHeight + 'px');\n    }"
)

# 6. Add navCollapsed and inspectorCollapsed state properties if they are not already managed fully
# There's setInspectorCollapsed and setNavCollapsed probably? Let's check if they exist or if we should add toggle behavior.
# The user wants inward collapse for panels.

with open('src/deepseek_terminal_agent/dashboard/static/chat.js', 'w', encoding='utf-8') as f:
    f.write(js)
print('Updated chat.js')
