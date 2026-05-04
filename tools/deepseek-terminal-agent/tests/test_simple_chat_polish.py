import pytest
import os

def test_simple_chat_left_drawer_exists():
    path = 'src/deepseek_terminal_agent/dashboard/templates/chat.html'
    if not os.path.exists(path): pytest.skip("File not found")
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    assert 'id="simple-chat-left-drawer"' in html
    assert 'Панель управління чатами' in html

def test_simple_chat_menu_polish():
    path = 'src/deepseek_terminal_agent/dashboard/templates/chat.html'
    if not os.path.exists(path): pytest.skip("File not found")
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    assert 'id="simple-menu-left-drawer"' in html
    assert 'Очистити чат' not in html 

def test_js_drawer_independent_toggles():
    path = 'src/deepseek_terminal_agent/dashboard/static/chat.js'
    if not os.path.exists(path): pytest.skip("File not found")
    with open(path, 'r', encoding='utf-8') as f:
        js = f.read()
    # verify mutual exclusion was removed
    assert 'closeAllSimpleDrawers()' not in js
    # verify persistence keys
    assert 'localStorage.getItem(\'deepseekAgentOS.simpleChat.drawers.v1\')' in js
    assert 'simpleChatDrawerState' in js
    assert 'updateSimpleChatDrawersUI()' in js
    # verify toggles
    assert 'simpleChatDrawerState.left = !simpleChatDrawerState.left' in js
    assert 'simpleChatDrawerState.right = !simpleChatDrawerState.right' in js
    # verify glyphs
    assert "leftCollapseBtn.textContent = '❮'" in js
    assert "leftCollapseBtn.textContent = '❯'" in js

def test_css_drawer_styles():
    path = 'src/deepseek_terminal_agent/dashboard/static/dashboard.css'
    if not os.path.exists(path): pytest.skip("File not found")
    with open(path, 'r', encoding='utf-8') as f:
        css = f.read()
    assert '.simple-chat-drawer' in css
    assert '.simple-chat-drawer--left' in css
    assert '.simple-chat-drawer--right' in css
    assert '.simple-chat-drawer__collapse' in css
