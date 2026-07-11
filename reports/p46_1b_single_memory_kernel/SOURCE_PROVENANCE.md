# Source Provenance

## FACTS

| Source | SHA | Use |
|---|---|---|
| Canonical integration base | `2d3dac308392cc907c329df338602f442a812097` | branch start; parent `5bc64f9b` |
| P42 release tip | `5bc64f9bae54099f22cf93d1bcbf19f7e40c7b4d` | existing models/config/persistence context |
| P41X kernel | `74fb107971443bc19720900a9ba07649d6d7f5e0` | append-only evidence, checkpoints, source-reference design |
| P41Y hardening | `f5cac0107c16fe43c2ec28fbafa8117f1e665096` | strict replay, partial-write and deterministic recall design input |
| P43A equivalent kernel | `3f2e853b` | duplicate lineage; not separately ported |
| P39D lifecycle | `b0c93c64` | legacy migration input only |

The implementation is a focused manual port, not a whole-commit cherry-pick. P42N code was neither imported nor referenced.

## INFERENCES

- Manual reduction is necessary to keep memory separate from execution authority.

## ASSUMPTIONS

- Preserved source SHAs remain remotely durable as recorded by P46-1A.

## UNKNOWNS

- No semantic equivalence claim is made for P41Y features outside the required P46-1B contract.

