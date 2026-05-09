# Calibrators

This directory is the canonical home for offline calibration entrypoints and their inventories.

What belongs here:
- offline calibrators that search, compare, score, or recommend threshold/parameter overlays
- calibration-stage orchestration that bundles or ranks candidate overlays
- calibration-only helper packages that are not part of the runtime hot path

What does not belong here:
- production runtime modules under apps/reference
- passive reports without calibration logic
- generic replay, extraction, or forensic tools that only feed calibration inputs

Rules:
- Calibrators may recommend config changes, but they must not silently mutate live YAML unless that behavior is explicitly designed, reviewed, and separately validated.
- Production runtime modules must not import from calibrators.
- Accepted calibration outputs require an explicit report plus validation evidence.
- YAML and Pydantic remain the SSOT for business semantics.
