# P40B Tech Debt Delta

## RETIRED
- URL-string-only testnet confidence at the audited pre-submit safety boundary is retired; descriptor absence now fails closed.
- Ambiguous `supports_order_submit` naming is replaced by `order_submit_enabled`.

## MITIGATED
- Missing audit attribution is mitigated by recording `agent_number` and `rationale` in rejection ledgers.
- Test side effects are mitigated by isolating audit ledgers into `tmp_path` for future focused test runs.

## DEFERRED_WITH_REASON
- Live runtime descriptor discovery is deferred because P40B scope is adapter capability hardening, not exchange execution wiring.
- External testnet order proof is deferred to the P40 order proof task.

## CONVERTED_TO_RUNTIME_CHECK
- Missing descriptor, mainnet/unknown descriptor, no-order mode, and submit-disabled descriptor are explicit runtime pre-submit checks.
