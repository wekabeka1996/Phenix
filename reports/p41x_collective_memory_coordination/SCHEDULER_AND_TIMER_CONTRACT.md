# Scheduler And Timer Contract

The scheduler is caller-driven; it does not start a hidden daemon. Every cadence comes from `collective_memory_config.yaml` and is Pydantic-validated.

| Task | Cadence |
|---|---:|
| market refresh | 30 s |
| agent heartbeat | 30 s |
| collective sync | 60 s |
| tactical analysis | 300 s |
| decision review | 900 s |
| portfolio reconciliation | 60 s |
| reflection | 1800 s |
| memory checkpoint | 1800 s |
| instruction refresh | 300 s |

Event wakeups are configured for instruction changes, order/position lifecycle changes, peer publications, risk warnings, regime changes, and exchange errors. Tactical analysis cannot be configured below 5 minutes and decision review cannot be configured below 15 minutes.
