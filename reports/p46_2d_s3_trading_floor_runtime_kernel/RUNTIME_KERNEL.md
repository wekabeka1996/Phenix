# Runtime Kernel

## FACTS

No `TradingFloorRuntimeKernel` was implemented. The task permits construction only after one ownership model is supported by evidence.

The safe future composition order remains:

```text
validated manifest -> exclusive memory ownership -> session bootstrap
-> versioned snapshots/projections -> query service -> IPC registration -> ready
```

## INFERENCES

Building the aggregate before exclusive memory acquisition would create a misleading readiness surface.

## ASSUMPTIONS

Existing business services should remain injected references rather than be reimplemented in the kernel.

## UNKNOWNS

The approved exclusive-writer mechanism and mutation transport.
