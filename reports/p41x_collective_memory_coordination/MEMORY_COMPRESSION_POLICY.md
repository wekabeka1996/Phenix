# Memory Compression Policy

- Raw evidence is never overwritten or deleted.
- Events are grouped deterministically by configured sequence segment size.
- Each segment lists every source ID; the manifest lists all source references in chronological sequence.
- Critical order, risk, FSM, exchange, lifecycle, SOS, and instruction events are embedded in full.
- Noncritical payload categories omitted from a summary are listed explicitly.
- Checkpoint state contains full feature-trust history and instruction versions.
- Private checkpoints remain in per-agent directories and are referenced by a carryover bundle without leaking private content.
- `tiktoken` is used when installed; this environment lacked it, so benchmark counts are marked `estimate` using the configured chars/token ratio.
- Active prompt context is separately bounded; old segments can be represented by explicit checkpoint manifest refs while the complete checkpoint remains on disk.

Compression ratio measures context size reduction only. It is not evidence of semantic quality.
