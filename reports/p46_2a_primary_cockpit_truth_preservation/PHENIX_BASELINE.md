# Phenix Baseline

## FACTS

| Field | Evidence |
|---|---|
| Canonical worktree | `C:\Users\wekab\Music\Phenix-p46-1b-canonical` |
| Canonical branch | `p46-1b-canonical-integration-primary-20260711` |
| Observed canonical HEAD/remote | `5fb8b928923d6a2a14fca84d283548b92777ac45` / same |
| Ahead/behind | `0/0` |
| Report baseline | `2caae9d3f11987f8fe089003eeb0ad7e7e04abe9` |
| Required ancestors | all present |
| Tracked status | clean |
| Untracked status | `scripts/p46_1g_r_canonical_venue_proof.py` only |
| Forensic script SHA256 | `6b5a05ec066cfd1cef3f68ba731ae8c131250fff4b82b65267f05541d5499771` |

The report branch is intentionally rooted at `2caae9d3`; no Phenix production source was modified. Later canonical commits `3848890e` and `5fb8b928` are report/closure descendants and were inventoried without being used as the report branch base.

## INFERENCES

The execution baseline is not ambiguous: `2caae9d3` and all required implementation ancestors are in the synchronized canonical lineage.

## ASSUMPTIONS

The known untracked script remains forensic evidence and is not an authoritative runtime component.

## UNKNOWNS

None affecting P46-2A repository preservation.
