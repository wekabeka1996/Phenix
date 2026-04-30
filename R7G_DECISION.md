# R7G Decision

The verified runtime does not show a Sidecar math defect. It shows an upstream economics boundary gap: PositionTracking emits only minimal position snapshots, the portfolio-state schema does not carry symbol-scoped markPrice or per-position PnL, and the inspected runtime slice does not show a market-tick feed that would populate a symbol cache for export.

UPSTREAM_PORTFOLIO_ECONOMICS_BOUNDARY_GAP
