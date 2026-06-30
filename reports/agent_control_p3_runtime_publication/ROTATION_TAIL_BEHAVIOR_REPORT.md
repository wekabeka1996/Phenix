# Rotation and tail behavior report

The relay read the active ~245 MB main-owned mirror from EOF with a 2 MiB / 1,000-line cap. `leading_partial_line_discarded` was observed, and the latest BTCUSDT/ETHUSDT 300-second records were selected without a full scan.

During the observation, the mirror's mtime advanced and relay watch atomically replaced all three compact publication files. No `.tmp` residue remained. Readers returned only complete schema-valid old or new files.

Source log rotation did not occur: `not_observed`. No destructive rotation was forced. Atomic publication replacement was observed; JSONL file rollover remains outside P3.
