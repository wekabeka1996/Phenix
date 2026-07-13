# Risks And Residuals

## FACTS
- Main-process authority and standalone API remain separated without a canonical process-safe authority/context projection.
- Dry-run result cache is process-local; Cockpit is the durable immutable evidence owner.

## UNKNOWNS
- Production process lifecycle, load, and cross-domain snapshot atomicity are unproven.
