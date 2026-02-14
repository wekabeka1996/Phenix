# optimization — Aurora Hierarchical Optimization Module
#
# Three-stage optimization pipeline:
#   Stage 0: Regime Calibration (stability_score)
#   Stage 1: Alpha Search (median_sharpe − penalties)
#   Stage 2: Robustness Check (Walk-Forward, Bootstrap, Stress)
#   + Cold Holdout gate (go/no-go before production)
