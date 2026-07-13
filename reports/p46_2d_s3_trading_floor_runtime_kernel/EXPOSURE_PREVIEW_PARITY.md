# Exposure Preview Parity

## FACTS

`ExposureGuard.can_open()` is a reusable non-reserving evaluation seam; mutation remains in separate reservation operations. S1 dry-run contracts require zero reservations.

No production parity proof was attempted because authoritative account/market snapshot identities and canonical context are prerequisites. Reusing the formula with anonymous fixtures would violate the task.

## INFERENCES

The calculation seam is not the current blocker.

## ASSUMPTIONS

Future dry-run and live evaluation must share the same guard instance/config version.

## UNKNOWNS

Parity under real published snapshot identities remains unproven.
