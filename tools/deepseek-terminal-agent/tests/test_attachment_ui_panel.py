"""Static contract tests for the Cockpit attachment UI panel."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHAT_HTML = ROOT / "src" / "deepseek_terminal_agent" / "dashboard" / "templates" / "chat.html"
CHAT_JS = ROOT / "src" / "deepseek_terminal_agent" / "dashboard" / "static" / "chat.js"

ATTACHMENT_KINDS = [
    "operator_note",
    "pasted_text",
    "news_summary",
    "image_ref",
    "chart_snapshot",
    "market_screenshot",
    "file_ref",
]


def test_attachment_panel_markup_supports_required_kinds():
    html = CHAT_HTML.read_text(encoding="utf-8")

    assert 'id="attachments-panel"' in html
    assert 'id="attachment-add-btn"' in html
    assert 'id="attachment-list"' in html
    assert 'id="attachment-status"' in html
    assert 'type="file"' not in html
    for kind in ATTACHMENT_KINDS:
        assert f'value="{kind}"' in html


def test_attachment_panel_js_uses_p32b_routes_and_compact_rendering():
    js = CHAT_JS.read_text(encoding="utf-8")

    assert "function addAttachment()" in js
    assert "function loadAttachments(sessionId)" in js
    assert "'/chat/sessions/' + state.currentSessionId + '/attachments'" in js
    assert "'/chat/sessions/' + sessionId + '/attachments'" in js
    assert "Select or create a session first." in js
    assert "excerptText(attachment.summary || '', 180)" in js
    assert "excerptText(attachment.raw_ref, 120)" in js
    assert "image_bytes" not in js
    assert "content_base64" not in js
