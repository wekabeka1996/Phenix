# NRR062 Override Close Coverage Audit

## Freeze Boundary Counts
| metric | value |
| --- | --- |
| canonical_closed | 1 |
| closed_non_canonical_evidence | 0 |
| filled_position_still_open | 1 |
| submitted_not_filled | 0 |
| inconclusive | 24 |

## Latest Known Counts
| metric | value |
| --- | --- |
| canonical_closed | 1 |
| closed_non_canonical_evidence | 1 |
| filled_position_still_open | 0 |
| submitted_not_filled | 0 |
| inconclusive | 24 |

## Conclusion
- Package J freeze low close count was not driven by a large pool of open positions. The retained freeze boundary shows one filled position still open, one canonical close, and twenty-four diagnostics-only rows with no downstream submit/fill evidence.
- The only confirmed short-horizon carryover is the ETH row, which remained open at the J freeze and closed about 2h17m later with a raw SL close outside the retained J window.
- No retained J row shows a same-window non-canonical close gap. The later ETH close is a post-freeze continuation, not proof of a within-window canonical miss.
