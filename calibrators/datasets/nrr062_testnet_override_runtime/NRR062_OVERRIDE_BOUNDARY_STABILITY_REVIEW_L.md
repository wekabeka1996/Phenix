# NRR062_OVERRIDE_BOUNDARY_STABILITY_REVIEW_L

- verdict: BOUNDARY_STABLE_NO_OVERRIDE_LEAKAGE_WITH_SIDECAR_CONFIG_DRIFT_CAVEAT
- package_l_override_count: 7
- package_l_status_counts: {'REJECTED_UPSTREAM': 7}
- sidecar_mode_drift_detected: True

| surface | value |
| --- | --- |
| package_l_downstream_no_effect_confirmed | 7 |
| package_l_submit_fill_close_detected | False |
| domains_yaml_same_as_j | False |
| aurora_yaml_same_as_j | True |

The Package L environment is not sidecar-authority-equivalent to the Package J snapshot. The diagnostics-only no-effect classification remains valid because neither the 24 J rows nor the 7 new L rows reached submit/fill/close evidence, but downstream authority-sensitive comparability is contaminated for promotion-grade interpretation.
