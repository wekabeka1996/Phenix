---
name: risk-guards
description: Use for risk gates, kill switches, exposure controls, CVaR/DD/latency limits. Anchors to config/aurora/*.yaml and tools/gate_effect_report.py, tools/smoke_tidy_gate.py, tools/verify_sizing.py.
---

# Risk Guards Skill

## Purpose
Perform severity-classified analysis of risk controls with fail-closed expectations.

## Scope
- Risk gates, kill switches, exposure limits
- Config-driven thresholds
- Guard diagnostics in tools/

## When to use
- Any change affecting risk controls
- Any audit or analysis of guards

## When NOT to use
- Non-risk features with no guard impact

## Required inputs
- Target strategy or subsystem
- Risk controls in scope
- Environment scope

If any required input is missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...

## Deterministic procedure
1) Locate relevant thresholds in config/aurora/*.yaml (for example, trading.yaml, system.yaml, regime.yaml).
2) Identify enforcement and diagnostics in tools/gate_effect_report.py, tools/smoke_tidy_gate.py, tools/verify_sizing.py.
3) Classify risk severity (S0-S3).
4) Verify fail-closed behavior for each control.
5) Define required tests and rollback criteria.
6) If any referenced artifact is missing, output MUST start with:
   BLOCKED: missing <exact paths>

Severity scale:
- S0: Critical safety breach or capital risk
- S1: High risk of loss or systemic failure
- S2: Moderate impact, bounded risk
- S3: Low impact or cosmetic

## Output
Use output_template.md.

## Safety constraints
- Do not loosen thresholds without explicit rationale and rollback.
- Do not disable guards for convenience.
- Do not assume production write access.

## Failure handling
If required inputs or artifacts are missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...
