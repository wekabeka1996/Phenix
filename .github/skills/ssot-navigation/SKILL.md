---
name: ssot-navigation
description: Use when a task requires SSOT alignment, architecture navigation, or contract-driven changes. Enforces Copilot_Master_Roadmap.md as SSOT and real repo anchors for configs, tools, logs, and reports.
---

# SSOT Navigation Skill

## Purpose
Guarantee SSOT-first navigation and prevent edits that are disconnected from the actual Aurora/Phenix repository structure.

## Scope
- SSOT alignment via Copilot_Master_Roadmap.md
- Navigation across real repo domains and artifacts
- Contract or configuration impacts

## When to use
- Any request that mentions SSOT, contracts, or architecture
- Any change that needs authoritative references
- Any analysis that depends on config, tools, logs, or reports

## When NOT to use
- Pure UI/editor preference tasks
- Single-file edits with no architectural impact

## Required inputs
- Target feature or subsystem
- Intended change or question
- Environment scope (backtest, replay, simulation)

If any required input is missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...

## Deterministic procedure
1) Open Copilot_Master_Roadmap.md and identify the task’s SSOT context and related artifacts.
2) Locate relevant domain folder(s) among: alysha_core/, apps/, backtest_engine/, config/, data/, docs/, logs/, reports/, schemas/, scripts/, tests/, tools/, vfoundation/.
3) If the task touches configuration, open config/aurora/*.yaml and config/_schemas/ plus related validators in tools/ (for example, tools/validate_configs.py, tools/verify_config.py).
4) If the task touches execution or orders, locate diagnostics under tools/ (for example, tools/check_orders.py, tools/debug_orders.py, tools/metrics_summary.py) and correlate with logs/*.jsonl or logs/backtests/*.
5) If the task touches observability or audits, use reports/*.md, FORENSIC_REPORT.md, FORENSIC_ANALYSIS_LOSING_RUN.md, and tools/log_audit.py.
6) If any referenced artifact is missing on disk, output MUST start with:
   BLOCKED: missing <exact paths>
7) Summarize allowed change boundaries and the minimal change set.

## Output
Use output_template.md.

## Safety constraints
- Do not invent paths or domains.
- Do not proceed without SSOT alignment.
- Do not assume live trading or production write access.
- AI is advisory only; never make trading decisions.

## Failure handling
If SSOT context or referenced artifacts are missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...
