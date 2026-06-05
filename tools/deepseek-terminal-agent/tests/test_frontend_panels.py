"""Tests that chat.html contains required Agent OS panel mount points."""
from __future__ import annotations

from pathlib import Path

_HTML = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "deepseek_terminal_agent"
    / "dashboard"
    / "templates"
    / "chat.html"
)
_JS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "deepseek_terminal_agent"
    / "dashboard"
    / "static"
    / "chat.js"
)


def _html():
    return _HTML.read_text(encoding="utf-8")


def _js():
    return _JS.read_text(encoding="utf-8")


# ── HTML mount points ──────────────────────────────────────────────────────────

def test_playbooks_panel_present():
    assert "id=\"playbooks-panel\"" in _html()
    assert "id=\"playbooks-list\"" in _html()


def test_tools_panel_present():
    assert "id=\"tools-panel\"" in _html()
    assert "id=\"tools-list\"" in _html()


def test_approvals_panel_present():
    assert "id=\"approvals-panel\"" in _html()
    assert "id=\"approvals-list\"" in _html()
    assert "id=\"approval-create-btn\"" in _html()


def test_reports_panel_present():
    assert "id=\"reports-panel\"" in _html()
    assert "id=\"reports-scan-btn\"" in _html()
    assert "id=\"reports-list\"" in _html()


def test_decisions_panel_present():
    assert "id=\"decisions-panel\"" in _html()
    assert "id=\"decision-add-btn\"" in _html()
    assert "id=\"decisions-list\"" in _html()


def test_memory_patches_panel_present():
    assert "id=\"memory-patches-panel\"" in _html()
    assert "id=\"patch-create-btn\"" in _html()
    assert "id=\"patches-list\"" in _html()


def test_evidence_bundles_panel_present():
    assert "id=\"evidence-bundles-panel\"" in _html()
    assert "id=\"bundles-scan-btn\"" in _html()
    assert "id=\"bundles-list\"" in _html()


def test_no_raw_reasoning_content_in_html():
    html = _html()
    assert "internal_reasoning_content" not in html
    assert "<think>" not in html
    assert "reasoning_content" not in html


# ── JS API call routes ─────────────────────────────────────────────────────────

def test_js_calls_playbooks_route():
    assert "/chat/playbooks" in _js()


def test_js_calls_tools_route():
    assert "/chat/tools" in _js()


def test_js_calls_approvals_route():
    js = _js()
    assert "/chat/approvals" in js
    assert "/approve" in js
    assert "/reject" in js


def test_js_calls_reports_route():
    js = _js()
    assert "/chat/reports" in js
    assert "/chat/reports/scan" in js


def test_js_calls_decisions_route():
    js = _js()
    assert "/chat/decisions" in js
    assert "/deprecate" in js


def test_js_calls_patches_route():
    js = _js()
    assert "/chat/memory-patches" in js
    assert "/approve" in js


def test_js_calls_bundles_route():
    js = _js()
    assert "/chat/evidence-bundles" in js
    assert "/chat/evidence-bundles/scan" in js


def test_js_no_raw_reasoning_content():
    js = _js()
    assert "internal_reasoning_content" not in js
    assert "<think>" not in js
