"""Tests for the Agent OS cockpit UI (chat.html / chat.js).

Phase 15 requirements: global header, left nav, workspace, right inspector
tabs, bottom drawer, Ukrainian localisation, composer, scenario buttons,
monitoring placeholder, security.
"""
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
_CSS = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "deepseek_terminal_agent"
    / "dashboard"
    / "static"
    / "dashboard.css"
)


def _html() -> str:
    return _HTML.read_text(encoding="utf-8")


def _js() -> str:
    return _JS.read_text(encoding="utf-8")


def _css() -> str:
    return _CSS.read_text(encoding="utf-8")


def _css_rule(selector: str) -> str:
    css = _css()
    marker = f"{selector} {{"
    start = css.index(marker) + len(marker)
    end = css.index("}", start)
    return css[start:end]


# ── HTML structure ─────────────────────────────────────────────────────────────

def test_global_header_exists():
    html = _html()
    assert 'id="global-header"' in html


def test_left_nav_exists():
    assert 'id="left-nav"' in _html()


def test_agent_workspace_tab_exists():
    assert 'id="ws-tab-agent"' in _html()


def test_right_inspector_exists():
    assert 'id="inspector-tabs"' in _html()


def test_bottom_drawer_exists():
    assert 'id="bottom-drawer"' in _html()


def test_monitoring_tab_exists():
    html = _html()
    # workspace monitoring tab
    assert 'ws-tab-monitoring' in html


def test_cmd_palette_modal_exists():
    assert 'id="cmd-palette-modal"' in _html()


def test_cockpit_layout_exists():
    assert 'cockpit-layout' in _html()


def test_header_control_surface_exists():
    html = _html()
    assert 'id="project-selector-btn"' in html
    assert 'id="header-model-btn"' in html
    assert 'id="header-reasoning-btn"' in html
    assert 'id="header-inspector-toggle"' in html


def test_left_nav_footer_controls_exist():
    html = _html()
    assert 'class="nav-footer"' in html
    assert 'id="nav-collapse-btn"' in html


def test_workspace_session_pill_exists():
    assert 'id="workspace-session-pill"' in _html()


def test_central_workspace_exists():
    html = _html()
    assert 'id="central-workspace"' in html
    assert 'id="central-workspace-stack"' in html


def test_central_workspace_has_five_primary_sections():
    html = _html()
    assert 'workspace-section--scenarios' in html
    assert 'workspace-section--chat' in html
    assert 'workspace-section--trace' in html
    assert 'workspace-section--result' in html
    assert 'workspace-section--composer' in html


def test_workspace_layout_controls_exist():
    html = _html()
    assert 'id="workspace-preset-select"' in html
    assert 'id="workspace-reset-btn"' in html
    assert 'value="debug"' in html
    assert 'value="custom"' in html


def test_workspace_mode_switch_exists():
    html = _html()
    assert 'id="layout-mode-cockpit"' in html
    assert 'id="layout-mode-board"' in html
    assert 'id="workspace-mode-switch"' in html
    assert 'Cockpit Mode' in html
    assert 'Board Mode' in html


def test_board_canvas_dom_exists():
    html = _html()
    assert 'id="board-canvas-shell"' in html
    assert 'id="board-canvas"' in html
    assert 'data-board-root="true"' in html


def test_board_panels_exist_for_required_windows():
    html = _html()
    for panel_key in (
        "sessions",
        "chat",
        "inspector",
        "artifacts",
    ):
        assert f'data-board-panel="{panel_key}"' in html


def test_board_drag_resize_and_reset_hooks_exist():
    html = _html()
    assert 'data-board-drag-handle' in html
    assert 'data-board-resize="se"' in html
    assert 'id="board-reset-btn"' in html


# ── Ukrainian localisation ─────────────────────────────────────────────────────

def test_ukrainian_agent_workspace():
    assert "Агентна робоча область" in _html()


def test_ukrainian_scenarios():
    assert "Сценарії" in _html()


def test_ukrainian_tool_registry():
    html = _html()
    assert "Реєстр інструментів" in html or "Інструменти" in html


def test_ukrainian_approval_queue():
    assert "Черга підтверджень" in _html()


def test_ukrainian_decision_ledger():
    assert "Журнал рішень" in _html()


def test_ukrainian_evidence_bundle():
    assert "Пакет доказів" in _html()


def test_ukrainian_monitoring():
    assert "Моніторинг" in _html()


def test_ukrainian_send_button():
    assert "Запустити" in _html()


def test_ukrainian_sessions_label():
    assert "Сесії" in _html()


def test_ukrainian_memory_label():
    assert "Пам'ять" in _html()


# ── Right inspector tabs ───────────────────────────────────────────────────────

def test_inspector_tab_inspector():
    assert "Інспектор" in _html()


def test_inspector_tab_context():
    assert "Контекст" in _html()


def test_inspector_tab_run():
    assert "Запуск" in _html()


def test_inspector_tab_artifacts():
    assert "Артефакти" in _html()


def test_inspector_tab_approval():
    assert "Approval" in _html()


def test_inspector_tab_memory():
    assert "Пам'ять" in _html()


def test_inspector_loaded_context_card():
    assert 'id="context-usage"' in _html()


def test_inspector_ssot_card():
    assert 'id="ssot-rules-list"' in _html()


def test_inspector_tool_permissions_card():
    assert 'id="tools-panel"' in _html()
    assert 'id="tools-list"' in _html()


def test_inspector_current_run_card():
    assert 'id="current-run-status"' in _html()


def test_inspector_agent_graph_card():
    assert 'id="agent-graph"' in _html()


def test_inspector_artifacts_card():
    assert 'id="evidence-bundles-panel"' in _html()


def test_inspector_approval_tab_content():
    assert 'id="approvals-panel"' in _html()


def test_inspector_memory_tab_content():
    assert 'id="memory-patches-panel"' in _html()


# ── Bottom drawer ──────────────────────────────────────────────────────────────

def test_drawer_tab_recent_runs():
    assert "Останні запуски" in _html()


def test_drawer_tab_event_log():
    assert "Журнал подій" in _html()


def test_drawer_tab_artifacts():
    assert 'id="drawer-tab-artifacts"' in _html()


def test_drawer_tab_tests():
    assert "Тести" in _html()


def test_drawer_tab_trace():
    assert "Trace" in _html()


def test_drawer_toggle_btn_exists():
    assert 'id="drawer-toggle-btn"' in _html()


def test_drawer_refresh_btn_exists():
    assert 'id="drawer-refresh-btn"' in _html()


def test_recent_runs_table_mount_exists():
    assert 'id="recent-runs-body"' in _html()


# ── Composer elements ──────────────────────────────────────────────────────────

def test_composer_send_btn():
    assert 'id="send-btn"' in _html()


def test_composer_cancel_btn():
    assert 'id="cancel-subagent-btn"' in _html()


def test_composer_model_selector():
    assert 'id="model-selector"' in _html()


def test_composer_context_preview_btn():
    assert 'id="context-preview-btn"' in _html()


def test_composer_workspace_controls_exist():
    html = _html()
    assert 'id="composer-body"' in html
    assert 'id="composer-clear-btn"' in html
    assert 'id="composer-default-btn"' in html
    assert 'id="composer-expand-btn"' in html
    assert 'id="composer-use-scenario-btn"' in html
    assert 'id="composer-resize-handle"' in html


def test_central_section_resize_handles_exist():
    html = _html()
    assert 'data-layout-resize="scenarios"' in html
    assert 'data-layout-resize="chat"' in html
    assert 'data-layout-resize="workTrace"' in html
    assert 'data-layout-resize="result"' in html
    assert 'data-layout-resize="composer"' in html


def test_central_sections_expose_layout_metadata():
    html = _html()
    assert 'data-layout-section="scenarios"' in html
    assert 'data-layout-section="chat"' in html
    assert 'data-layout-section="workTrace"' in html
    assert 'data-layout-section="result"' in html
    assert 'data-layout-section="composer"' in html
    assert 'data-min-height=' in html
    assert 'data-max-height=' in html


def test_central_section_move_actions_live_in_overflow_menus():
    html = _html()
    assert 'data-section-actions-menu="scenarios"' in html
    assert 'data-section-actions-menu="chat"' in html
    assert 'data-section-actions-menu="workTrace"' in html
    assert 'data-section-actions-menu="result"' in html
    assert 'data-section-actions-menu="composer"' in html
    assert 'data-section-move="up"' in html
    assert 'data-section-move="down"' in html
    assert 'data-section-key="scenarios"' in html
    assert 'data-section-key="composer"' in html
    assert "Перемістити вище" in html
    assert "Перемістити нижче" in html
    assert ">↑<" not in html
    assert ">↓<" not in html


def test_side_panel_resizers_exist():
    html = _html()
    assert 'id="left-nav-resizer"' in html
    assert 'id="session-panel-resizer"' in html
    assert 'id="inspector-panel-resizer"' in html
    assert 'id="bottom-drawer-resizer"' in html


def test_composer_shift_enter_hint():
    # textarea placeholder mentions Ctrl+Enter
    assert "Ctrl+Enter" in _html()


def test_output_surface_exists():
    html = _html()
    assert 'id="output-status-badge"' in html
    assert 'id="output-status-line"' in html
    assert 'id="output-result-box"' in html


def test_result_surface_action_mounts_exist():
    html = _html()
    assert 'id="result-copy-btn"' in html
    assert 'id="result-add-memory-btn"' in html
    assert 'id="result-focus-trace-btn"' in html
    assert 'id="result-focus-artifacts-btn"' in html
    assert 'id="result-artifact-links"' in html


def test_central_workspace_button_matrix_exists():
    html = _html()
    for button_id in (
        "refresh-session-btn",
        "inspect-context-btn",
        "compress-btn",
        "spawn-scout-btn",
        "scenario-apply-btn",
        "scenario-run-btn",
        "scenario-open-source-btn",
        "result-copy-btn",
        "result-add-memory-btn",
        "result-focus-trace-btn",
        "result-focus-artifacts-btn",
        "context-preview-btn",
        "composer-use-scenario-btn",
        "composer-clear-btn",
        "composer-default-btn",
        "composer-expand-btn",
        "send-btn",
        "cancel-subagent-btn",
    ):
        assert f'id="{button_id}"' in html


# ── Scenario buttons ───────────────────────────────────────────────────────────

def test_scenario_buttons_bar_exists():
    assert 'id="scenario-buttons-bar"' in _html()


def test_scenario_btn_data_playbook():
    assert 'data-playbook=' in _html()


def test_scenario_metadata_attributes_exist():
    html = _html()
    assert 'data-template-id=' in html
    assert 'data-source-file=' in html
    assert 'data-group=' in html
    assert 'data-mode=' in html
    assert 'data-risk-level=' in html
    assert 'data-quick-run=' in html


def test_scenario_preview_mount_exists():
    html = _html()
    assert 'id="scenario-preview-panel"' in html
    assert 'id="scenario-preview-empty"' in html


# Scenario bar labels removed for cockpit cleanup requirement.


def test_trace_mode_controls_exist_in_html():
    html = _html()
    assert 'data-trace-mode="compact"' in html
    assert 'data-trace-mode="working"' in html
    assert 'data-trace-mode="detailed"' in html
    assert "Повний reasoning" not in html


# ── Monitoring placeholder ─────────────────────────────────────────────────────

def test_monitoring_placeholder_text():
    assert "Моніторинг" in _html()


def test_monitoring_anomaly_actions():
    html = _html()
    assert "Пояснити аномалію" in html or "Знайти причину" in html


# ── JS: cockpit wiring ──────────────────────────────────────────────────────────

def test_js_ctrl_enter_handler():
    js = _js()
    assert "ctrlKey" in js
    assert "Enter" in js


def test_js_cmd_palette_open():
    js = _js()
    assert "cmd-palette-modal" in js
    assert "openCmdPalette" in js


def test_js_tab_switching():
    js = _js()
    assert "data-ws-tab" in js or "ws-tab" in js


def test_js_inspector_tab_switching():
    js = _js()
    assert "data-inspector" in js or "inspector-panel" in js


def test_js_drawer_toggle():
    js = _js()
    assert "bottom-drawer" in js
    assert "is-open" in js


def test_js_collapsible_section_wiring():
    js = _js()
    assert "data-collapse-target" in js
    assert "setCollapsedState" in js


def test_js_inspector_hide_show():
    js = _js()
    assert "setInspectorCollapsed" in js
    assert "header-inspector-toggle" in js


def test_js_recent_runs_loading():
    js = _js()
    assert "loadRecentRuns" in js
    assert "/runs/" in js


def test_js_output_surface_updates():
    js = _js()
    assert "setOutputSurface" in js
    assert "output-result-box" in js


def test_js_scenario_btn_handler():
    js = _js()
    assert "scenario-btn" in js


def test_js_scenario_modifier_and_preview_wiring():
    js = _js()
    assert "event.altKey" in js
    assert "event.shiftKey" in js
    assert "renderScenarioPreview" in js
    assert "scenario-run-btn" in js


def test_js_workspace_persistence_keys_exist():
    js = _js()
    assert "dashboard.chat.workspace.sections" in js
    assert "dashboard.chat.workspace.traceMode" in js
    assert "dashboard.chat.workspace.layoutPreset" in js
    assert "dashboard.chat.workspace.composerExpanded" in js
    assert "deepseekAgentOS.layout.cockpit.v1" in js
    assert "deepseekAgentOS.layout.board.v1" in js
    assert "deepseekAgentOS.layout.mode.v1" in js
    assert "deepseekAgentOS.layout.v1" in js


def test_js_layout_state_functions_exist():
    js = _js()
    assert "loadLayoutState" in js
    assert "saveLayoutState" in js
    assert "resetLayoutState" in js
    assert "applyLayoutState" in js
    assert "loadBoardLayoutState" in js
    assert "saveBoardLayoutState" in js
    assert "resetBoardLayoutState" in js
    assert "applyBoardLayoutState" in js
    assert "setLayoutMode" in js
    assert "initBoardInteractions" in js
    assert "initSectionResize" in js
    assert "initPanelResize" in js
    assert "initSectionMoveControls" in js
    assert "initBottomDrawerResize" in js
    assert "initGlobalScrollGuards" in js


def test_js_layout_handles_corrupted_storage_safely():
    js = _js()
    assert "window.localStorage.getItem(STORAGE_KEYS.layoutState)" in js
    assert "removeStoredValue(STORAGE_KEYS.layoutState)" in js


def test_js_section_height_clamp_uses_config_limits():
    js = _js()
    assert "function clampSectionHeight(sectionKey, height)" in js
    assert "return clampNumber(height, config.min, config.max, config.defaultHeight);" in js


def test_js_trace_mode_and_layout_controls_exist():
    js = _js()
    assert "setTraceMode" in js
    assert "formatTraceModeLabel" in js
    assert "setWorkspacePreset" in js
    assert "workspace-reset-btn" in js
    assert "layout-mode-board" in js
    assert "board-reset-btn" in js


def test_js_central_workspace_renderers_exist():
    js = _js()
    assert "renderWorkTrace" in js
    assert "renderResultArtifacts" in js
    assert "chat-message" in js


def test_js_compact_trace_summary_and_details_exist():
    js = _js()
    assert "traceSummary" in js
    assert "renderMessageDetailSections" in js
    assert "Показати кроки" in js
    assert "Показати деталі" in js
    assert "Показати інструменти" in js
    assert "Показати артефакти" in js


def test_js_model_selector_population():
    js = _js()
    assert "model-selector" in js
    assert "/models" in js


def test_js_reasoning_toggle():
    js = _js()
    assert "reasoning-toggle" in js or "reasoning-body" in js


# ── Security ───────────────────────────────────────────────────────────────────

def test_no_raw_reasoning_content_in_html():
    html = _html()
    assert "internal_reasoning_content" not in html
    assert "<think>" not in html
    assert "reasoning_content" not in html


def test_no_raw_reasoning_content_in_js():
    js = _js()
    assert "internal_reasoning_content" not in js
    assert "<think>" not in js


def test_no_api_key_pattern_in_html():
    import re
    # no sk- pattern leaking in static HTML
    html = _html()
    assert not re.search(r'\bsk-[A-Za-z0-9]{8,}', html)


def test_no_env_leakage_in_html():
    assert ".env" not in _html()


# ── Regression: existing panel IDs still present ───────────────────────────────

def test_regression_playbooks_panel():
    html = _html()
    assert 'id="playbooks-panel"' in html
    assert 'id="playbooks-list"' in html


def test_regression_tools_panel():
    html = _html()
    assert 'id="tools-panel"' in html
    assert 'id="tools-list"' in html


def test_regression_approvals_panel():
    html = _html()
    assert 'id="approvals-panel"' in html
    assert 'id="approvals-list"' in html
    assert 'id="approval-create-btn"' in html


def test_regression_reports_panel():
    html = _html()
    assert 'id="reports-panel"' in html
    assert 'id="reports-scan-btn"' in html
    assert 'id="reports-list"' in html


def test_regression_decisions_panel():
    html = _html()
    assert 'id="decisions-panel"' in html
    assert 'id="decision-add-btn"' in html
    assert 'id="decisions-list"' in html


def test_regression_memory_patches_panel():
    html = _html()
    assert 'id="memory-patches-panel"' in html
    assert 'id="patch-create-btn"' in html
    assert 'id="patches-list"' in html


def test_regression_evidence_bundles_panel():
    html = _html()
    assert 'id="evidence-bundles-panel"' in html
    assert 'id="bundles-scan-btn"' in html
    assert 'id="bundles-list"' in html


# ── Collapsible sections and styling hooks ───────────────────────────────────

def test_major_sections_are_collapsible():
    html = _html()
    assert 'data-collapse-target="sessions-card-body"' in html
    assert 'data-collapse-target="tasks-card-body"' in html
    assert 'data-collapse-target="chat-thread-panel"' in html
    assert 'data-collapse-target="reasoning-body"' in html
    assert 'data-collapse-target="output-panel-body"' in html
    assert 'data-collapse-target="context-card-body"' in html
    assert 'data-collapse-target="ssot-rules-body"' in html
    assert 'data-collapse-target="tools-card-body"' in html
    assert 'data-collapse-target="current-run-body"' in html
    assert 'data-collapse-target="agent-graph-body"' in html
    assert 'data-collapse-target="bundles-card-body"' in html


def test_css_cockpit_control_classes_exist():
    css = _css()
    assert ".header-control" in css
    assert ".workspace-tabs-shell" in css
    assert ".section-toggle" in css
    assert ".section-actions-menu" in css
    assert ".section-actions-menu__panel" in css
    assert ".section-actions-menu__item" in css
    assert ".section-menu__btn--menu" in css
    assert ".inspector-shell-head" in css
    assert ".bottom-drawer" in css
    assert ".cmd-palette-item" in css


def test_css_central_workspace_contract_classes_exist():
    css = _css()
    assert ".central-workspace" in css
    assert ".workspace-section" in css
    assert ".workspace-section__header" in css
    assert ".workspace-section__body" in css
    assert ".workspace-section--collapsed" in css


def test_css_central_workspace_is_primary_scroll_container():
    rule = _css_rule(".central-workspace")
    assert "overflow-y: auto;" in rule
    assert "overflow-x: hidden;" in rule
    assert "scrollbar-gutter: stable;" in rule


def test_css_central_workspace_stack_does_not_clip_document_flow():
    stack_rule = _css_rule(".central-workspace__stack")
    assert "flex: 0 0 auto;" in stack_rule
    assert "overflow: visible;" in stack_rule


def test_css_workspace_sections_are_resize_managed_regions():
    css = _css()
    assert ".workspace-section__resize" in css
    assert ".workspace-section--resizing" in css
    assert ".resize-handle" in css
    assert ".resize-handle--vertical" in css
    assert ".workspace-section__body" in css
    assert "scrollbar-gutter: stable;" in css


def test_css_workspace_panels_do_not_force_nested_scroll():
    chat_rule = _css_rule(".chat-thread--workspace")
    trace_rule = _css_rule(".reasoning-tree-shell")
    assert "max-height: none;" in chat_rule
    assert "overflow: visible;" in chat_rule
    assert "overflow: visible;" in trace_rule


def test_css_global_dashboard_scroll_and_panel_resizers_exist():
    css = _css()
    assert "--left-nav-width" in css
    assert "--session-panel-width" in css
    assert "--right-inspector-width" in css
    assert "--bottom-drawer-height" in css
    assert "--board-canvas-width" in css
    assert "--board-canvas-height" in css
    assert ".panel-resizer" in css
    assert ".bottom-drawer__resize" in css
    assert ".layout-reset-button" in css


def test_css_scenario_trace_and_composer_hooks_exist():
    css = _css()
    assert ".scenario-button--running" in css
    assert ".scenario-button--success" in css
    assert ".scenario-button--failed" in css
    assert ".reasoning-tree" in css
    assert ".chat-message" in css
    assert ".chat-message__trace-summary" in css
    assert ".chat-message__detail" in css
    assert ".composer-panel" in css
    assert ".composer-resize-handle" in css
    assert "position: sticky" in css


def test_css_board_mode_hooks_exist():
    css = _css()
    assert ".workspace-mode-bar" in css
    assert ".workspace-mode-switch" in css
    assert "body.layout-mode--board .board-canvas" in css
    assert ".board-panel-resizers" in css
    assert ".board-resize-handle--se" in css
    assert ".board-panel--focused" in css


def test_css_no_default_white_button_language():
    css = _css()
    assert "background: #fff" not in css
    assert "background: white" not in css

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
