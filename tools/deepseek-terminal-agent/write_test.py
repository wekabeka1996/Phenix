import os

with open('tests/test_frontend_cockpit.py', 'a', encoding='utf-8') as f:
    f.write('''
def test_simple_chat_mode_exists_and_has_structure():
    html = _html()
    assert 'data-layout-mode="simple"' in html
    assert 'layout-mode-simple' in html
    assert 'layout-mode-cockpit' in html
    assert 'layout-mode-board' in html
    
    assert 'id="simple-chat-shell"' in html
    assert 'simple-chat-shell' in html
    
    assert 'simple-chat-topbar' in html
    assert 'simple-chat-session-title' in html
    assert 'simple-chat-model-pill' in html
    assert 'simple-chat-mode-switch' in html
    
    assert 'id="simple-chat-thread"' in html
    
    assert 'simple-chat-composer' in html
    assert 'simple-chat-input' in html
    assert 'simple-chat-send-btn' in html
    assert 'simple-chat-plus-btn' in html
    
    assert 'id="simple-chat-advanced-drawer"' in html
''')
