AGENT_IDENTITY:
  agent_number: 3
  agent_name: primary-attachment-ui-builder
  machine: primary
  task_id: P34C_ATTACHMENT_UI_PANEL_WIRING
  branch: p34c-attachment-ui-primary-20260709
  worktree: C:\Users\wekab\Music\Phenix-p34c-attachment-ui
  started_at: 2026-07-09T10:30:00+03:00
  finished_at: 2026-07-09T10:46:38+03:00

# UI Contract

Panel:
- Location: Cockpit inspector memory area.
- Markup root: #attachments-panel.
- List root: #attachment-list.
- Status surface: #attachment-status.

Inputs:
- #attachment-kind supports operator_note, pasted_text, news_summary, image_ref, chart_snapshot, market_screenshot, file_ref.
- #attachment-summary is required.
- #attachment-raw-ref accepts a reference/path string only.
- #attachment-source-refs accepts comma-separated source refs.
- #attachment-include-prompt controls include_in_prompt.

Actions:
- #attachment-add-btn sends POST /chat/sessions/{session_id}/attachments.
- #attachment-reload-btn sends GET /chat/sessions/{session_id}/attachments.
- No active session shows a visible status and warning.

Rendering:
- Cards show kind, prompt/stored badge, bounded summary, bounded ref, and up to three source refs.
- No raw image/file upload input exists in this package.
