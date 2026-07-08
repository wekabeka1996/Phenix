# Policy Repair Report

This document outlines the safety policy repairs implemented in the shared session context contract to prevent unauthorized execution or unsafe configuration mutations.

## Core Safety Enforcements

### 1. No Order, Sizing, or Leverage Payload
- **Constraint**: The `SessionContextV1` contract must not contain fields that grant ordering authority, position sizing, or leverage parameters.
- **Enforcement**: Enforced via Pydantic v2's `model_config = ConfigDict(extra="forbid")` and validated in unit tests to ensure that inserting keys like `order`, `sizing`, or `leverage` raises validation errors.

### 2. GET-Only Read-Only API
- **Constraint**: The bridge interface must remain strictly read-only, prohibiting any POST or write endpoints.
- **Enforcement**: The API route is registered exclusively as `@app.get` in `routes.py`. Unit tests verify that calling POST on this endpoint returns `405 Method Not Allowed`.

### 3. Source References & Provenance Verification
- **Constraint**: Source references and provenance metadata must be validated where appropriate.
- **Enforcement**:
  - Added a Pydantic `@field_validator` enforcing that the `source` field must start with the schema prefix `cockpit-session://`.
  - Added a `@field_validator` on `provenance` requiring both `title` and `status` keys.
  - Aligned the JSON Schema (`session_context_v1.json`) to enforce these constraints.

### 4. Non-Mutation of Configurations
- **Constraint**: Memory patches or FSM components must not mutate YAML or system configurations.
- **Enforcement**:
  - The read model does not expose any write operations or serialization back into files outside of the read-only card.
  - Added explicit policy docstrings/comments to `session_context_contract.py` and `session_context_read_model.py` specifying that memory patches, session context, or FSM components are prohibited from mutating YAML/system configs.
