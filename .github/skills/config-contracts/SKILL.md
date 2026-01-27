---
name: config-contracts
description: Use when modifying or interpreting config or schema contracts. Anchors to config/aurora/*.yaml, config/_schemas/, and validation tools; enforces strict no-silent-defaults behavior.
---

# Config and Contracts Skill

## Purpose
Ensure configuration and schema changes are explicit, validated, and deterministic.

## Scope
- YAML configs in config/aurora/
- Schema definitions in config/_schemas/ and schemas/
- Validation logic in tools/ (validate/verify/debug config)

## When to use
- Any config change request
- Any schema or validation change
- Any behavior controlled by YAML

## When NOT to use
- Runtime logic unrelated to configuration

## Required inputs
- Target config file(s)
- Target schema or validation scope
- Environment scope (backtest, replay, simulation)

If any required input is missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...

## Deterministic procedure
1) Locate target config in config/aurora/*.yaml (for example, system.yaml, trading.yaml, observability.yaml, strategies.yaml).
2) Locate authoritative schema in config/_schemas/ or schemas/.
3) Identify validation paths in tools/ (for example, tools/validate_configs.py, tools/verify_config.py, tools/debug_config_loading.py).
4) Verify all required fields are explicit; no silent defaults in runtime logic.
5) If adding fields, define defaults only in config or schema with explicit rationale.
6) Define a validation plan and expected failure modes.
7) If any referenced artifact is missing, output MUST start with:
   BLOCKED: missing <exact paths>

## Output
Use output_template.md.

## Safety constraints
- Do not add implicit defaults in business logic.
- Do not relax schema constraints without explicit rationale.
- Do not bypass validation errors.
- Do not assume production write access.

## Failure handling
If required inputs or artifacts are missing, output MUST start with:
BLOCKED: missing <item1>, <item2>, ...
