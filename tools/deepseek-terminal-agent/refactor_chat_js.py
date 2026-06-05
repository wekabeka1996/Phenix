import re

with open('src/deepseek_terminal_agent/dashboard/static/chat.js', 'r', encoding='utf-8') as f:
    js = f.read()

# 1. syncLayoutModeControls
sync_logic = '''function syncLayoutModeControls() {
    var mode = state.layoutMode || 'simple';
    document.body.classList.toggle('layout-mode--board', mode === 'board');
    document.body.classList.toggle('layout-mode--cockpit', mode === 'cockpit');
    document.body.classList.toggle('layout-mode--simple', mode === 'simple');
    
    if (workspaceModeSwitch) {
      workspaceModeSwitch.setAttribute('data-active-mode', mode);
    }
    
    var btns = [
      document.getElementById('layout-mode-cockpit'),
      document.getElementById('layout-mode-board'),
      document.getElementById('layout-mode-simple')
    ];
    btns.forEach(function (button) {
      if (!button) return;
      var active = button.getAttribute('data-layout-mode') === mode;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });

    var select = document.getElementById('simple-chat-mode-switch');
    if (select) select.value = mode;
}'''
js = re.sub(r'function syncLayoutModeControls\(\) \{[\s\S]*?(?=function \w+\()', sync_logic + '\n\n', js)

# 2. setLayoutMode
set_logic = '''function setLayoutMode(mode, options) {
    options = options || {};
    state.layoutMode = mode;
    syncLayoutModeControls();
    if (!options.skipPersist) {
      writeStoredValue(STORAGE_KEYS.mode, state.layoutMode);
    }
    
    if (state.layoutMode !== 'board') {
      BOARD_PANEL_KEYS.forEach(function(key) {
        var p = getBoardPanelElement(key);
        if (p) {
          p.style.width = '';
          p.style.height = '';
          p.style.left = '';
          p.style.top = '';
          p.style.position = '';
          p.style.zIndex = '';
        }
      });
    }

    if (state.layoutMode === 'board') {
      applyBoardLayoutState(state.boardLayoutState || loadBoardLayoutState(), { skipSave: !!options.skipSave, skipScroll: !!options.skipScroll });
      setDrawerOpen(true, { skipSave: true, skipLegacyStorage: true });
    } else if (state.layoutMode === 'cockpit') {
      applyLayoutState(state.layoutState || loadLayoutState(), { skipSave: !!options.skipSave });
    } else {
      // simple mode
    }
}'''
js = re.sub(r'function setLayoutMode\(mode, options\) \{[\s\S]*?(?=function syncLayoutModeControls\()', set_logic + '\n\n', js)

# 3. Simple Chat rendering logic
simple_render_logic = '''
function renderSimpleChatThread(detail) {
    var simpleThread = document.getElementById('simple-chat-thread');
    if (!simpleThread) return;
    
    var items = buildTimelineItems(detail || {});
    if (!items.length) {
      simpleThread.innerHTML = '<div class="chat-empty">No messages yet. Write a prompt below to start.</div>';
      return;
    }
    
    var html = [];
    var currentGroup = [];
    
    function flushGroup() {
       if (currentGroup.length === 0) return;
       html.push('<div class="simple-chat-details"><details><summary>▸ Деталі роботи агентів (' + currentGroup.length + ' подій)</summary><div class="simple-chat-details__body">');
       currentGroup.forEach(function(ev) {
          html.push('<div><span class="muted">' + (ev.source || ev.kind) + ':</span> ' + escapeHtml(ev.status || '') + '</div>');
       });
       html.push('</div></details></div>');
       currentGroup = [];
    }

    items.forEach(function(item) {
        if (item.kind === 'message') {
            flushGroup();
            var isUser = item.role === 'user';
            var roleClass = isUser ? 'simple-chat-message--user' : 'simple-chat-message--assistant';
            html.push('<div class="simple-chat-message ' + roleClass + '">');
            html.push('<div class="simple-chat-message__content">' + escapeHtml(item.content || '') + '</div>');
            html.push('</div>');
        } else {
            // events, subagents, tools, results
            currentGroup.push(item);
        }
    });
    flushGroup();
    
    simpleThread.innerHTML = html.join('');
    simpleThread.scrollTop = simpleThread.scrollHeight;
}
'''
js = js.replace('function renderThread(detail) {', simple_render_logic + '\nfunction renderThread(detail) {')

# Hook renderSimpleChatThread inside renderThread
js = js.replace('const items = buildTimelineItems(detail || {});', 'renderSimpleChatThread(detail);\n    const items = buildTimelineItems(detail || {});')

# 4. Simple chat input logic & Mode switch bindings
bindings = '''
  var simpleModeBtn = document.getElementById('layout-mode-simple');
  if (simpleModeBtn) {
    simpleModeBtn.addEventListener('click', function() { setLayoutMode('simple'); });
  }
  var simpleModeSelect = document.getElementById('simple-chat-mode-switch');
  if (simpleModeSelect) {
    simpleModeSelect.addEventListener('change', function() { setLayoutMode(this.value); });
  }
  var simpleInput = document.getElementById('simple-chat-input');
  var simpleSendBtn = document.getElementById('simple-chat-send-btn');
  if (simpleSendBtn && simpleInput) {
    simpleSendBtn.addEventListener('click', function() {
       if (!simpleInput.value.trim()) return;
       if (promptArea) promptArea.value = simpleInput.value;
       simpleInput.value = '';
       sendChat();
    });
    simpleInput.addEventListener('keydown', function(e) {
       if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          simpleSendBtn.click();
       }
    });
  }
'''
js = js.replace('function initBoardInteractions() {', bindings + '\n  function initBoardInteractions() {')

# 5. initLayoutMode default logic modification
js = js.replace("var loadedMode = readStoredValue(STORAGE_KEYS.mode) || 'cockpit';", "var loadedMode = readStoredValue(STORAGE_KEYS.mode) || 'simple';")

with open('src/deepseek_terminal_agent/dashboard/static/chat.js', 'w', encoding='utf-8') as f:
    f.write(js)
print('updated chat.js')
