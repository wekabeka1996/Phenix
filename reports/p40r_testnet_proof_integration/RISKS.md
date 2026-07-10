# Risks and Mitigations

We audited the P40R integrated surface.

## Audited Risks
1.  **Old Test Harness Validation Failure**:
    - Risk: Merging P40C's test harness before aligning it to P40B's hardened `AdapterCapability` schema leads to Pydantic validation crashes.
    - Mitigation: Aligned the test setup code in `test_agent_order_lifecycle_harness.py` to instantiate `AdapterCapabilityDescriptor` using correct fields.
2.  **No-Order observation mode bypass**:
    - Risk: If `no_order_observation_mode` is incorrectly bypassed in live runtime, live orders could occur.
    - Mitigation: Checked by double-guard URL checks in `verify_handoff_safety`. Base URL domain checking explicitly fails closed if live domains are present.
