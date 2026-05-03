import re

with open('src/deepseek_terminal_agent/dashboard/templates/chat.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update central-workspace to be a board-panel
html = html.replace(
    '<main class="chat-column shell-column central-workspace" id="central-workspace" data-layout-preset="balanced" data-board-surface="workspace">',
    '<main class="chat-column shell-column central-workspace board-panel board-panel--window" id="central-workspace" data-layout-preset="balanced" data-board-surface="workspace" data-board-panel="chat" data-board-title="Unified Chat">\n              <div class="board-panel-header board-panel-header--shell" data-board-drag-handle style="display:none;"><div class="board-panel-heading"><h2>Unified Chat</h2></div></div>'
)

# 2. Remove board-panel classes and attributes from the 5 sections
def strip_board_panel(content):
    content = re.sub(r'\s*board-panel--window', '', content)
    content = re.sub(r'\s*board-panel', '', content)
    content = re.sub(r'\s*data-board-panel="[^"]+"', '', content)
    content = re.sub(r'\s*data-board-title="[^"]+"', '', content)
    content = re.sub(r'\s*data-board-drag-handle', '', content)
    return content

for section in ['scenarios', 'chat', 'workTrace', 'result', 'composer']:
    # Find the section tag
    pattern = r'(<section[^>]*workspace-section--' + section + r'[^>]*>)'
    def repl(m):
        return strip_board_panel(m.group(1))
    html = re.sub(pattern, repl, html)

# 3. Add vertical resize handle to central workspace
# We'll put it just inside the main tag, at the end.
html = html.replace('</main>', '  <div class="panel-resizer panel-resizer--central-vertical resize-handle resize-handle--vertical" id="central-workspace-resizer" data-panel-resize="centralWorkspace" role="separator" aria-label="Змінити висоту центральної області" tabindex="0"></div>\n            </main>')

# 4. Add collapse toggles to side panels (if not already there)
# They have resizers, let's add an inward collapse button to left-nav header and inspector header.
# Actually, left-nav already has: <button type="button" class="btn-ghost" id="nav-collapse-btn">Згорнути</button>
# And inspector has: <button type="button" class="btn-ghost inspector-toggle-btn" id="inspector-toggle-btn">Сховати</button>
# We can use those for collapse-inward behavior.

with open('src/deepseek_terminal_agent/dashboard/templates/chat.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Updated chat.html')
