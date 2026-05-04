---
name: observability-forensics
description: Use for incident analysis, JSONL log forensics, metrics, and post-mortems. Anchors to logs/*.jsonl, reports/*.md, and tools/log_audit.py, tools/metrics_summary.py.
---

# Observability and Forensics Skill

## Purpose
Generate audit-grade incident analysis with evidence-backed timelines and root cause.

## Scope
- Logs in logs/*.jsonl and logs/backtests/*
- Reports in reports/*.md and FORENSIC_*.md
- Observability tools in tools/

## When to use
- Any incident investigation
- Any post-mortem or audit

## When NOT to use
- Routine code edits without incident context

## Required inputs
- Incident time window
- Evidence sources (logs/reports)
- Target subsystem

If any required input is missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...

## Deterministic procedure
1) Collect evidence from logs/*.jsonl, logs/backtests/*, reports/*.md, FORENSIC_REPORT.md, FORENSIC_ANALYSIS_LOSING_RUN.md.
2) Use tools/log_audit.py and tools/metrics_summary.py if applicable.
3) Build a time-ordered UTC timeline.
4) Validate hypotheses against evidence.
5) Identify root cause and contributing factors.
6) Classify severity (S0-S3).
7) If any referenced artifact is missing, output MUST start with:
   BLOCKED: missing <exact paths>

## Output
Use output_template.md.

## Safety constraints
- Do not speculate without evidence.
- Do not alter logs or reports.
- Do not assume production data access.

## Failure handling
If required inputs or artifacts are missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...
