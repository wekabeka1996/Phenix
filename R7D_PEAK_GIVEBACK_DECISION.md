# R7D Peak-Giveback Decision

The fresh runtime slice after the latest Sidecar restart still does not show the R7C observability payloads.

Specifically:

- latest mode-active row is missing `sidecar_config_snapshot`
- all non-mode Sidecar rows are missing `peak_giveback_snapshot`
- no peak-giveback provenance appears in recommendation, close-request, order-log, shadow-journal, or execution-domain surfaces
- the only evaluated lifecycle still lacks usable economic fields in runtime artifacts

Because of that, runtime cannot prove loaded config, cannot reconstruct peak-giveback states, and cannot distinguish quiet market from missing observability.

PEAK_GIVEBACK_RUNTIME_NOT_PROVEN
