# AURORA DECISION GEOMETRY VALIDATION

- Symbols: BTCUSDT, ETHUSDT, SOLUSDT
- Date window: 2026-03-13 .. 2026-03-13
- Source: recorder bars + RegimeDetector + live shield cascade + current threshold surfaces
- NRR-027 metric: offline directional-sanity proxy, not live post-signal order-log replay

## BTCUSDT

| candidate | eligible | neutral_ratio | side_ratio | allowed_side | nrr027_proxy | nrr027_rate | buy | sell |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_quadratic | 132 | 100.00% | 0.00% | 0 | 0 | 0.00% | 0 | 0 |
| soft_power_p1_5 | 132 | 100.00% | 0.00% | 0 | 0 | 0.00% | 0 | 0 |
| decoupled_linear_floor075 | 132 | 100.00% | 0.00% | 0 | 0 | 0.00% | 0 | 0 |

## ETHUSDT

| candidate | eligible | neutral_ratio | side_ratio | allowed_side | nrr027_proxy | nrr027_rate | buy | sell |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_quadratic | 132 | 100.00% | 0.00% | 0 | 0 | 0.00% | 0 | 0 |
| soft_power_p1_5 | 132 | 68.94% | 31.06% | 0 | 0 | 0.00% | 0 | 41 |
| decoupled_linear_floor075 | 132 | 59.09% | 40.91% | 0 | 0 | 0.00% | 0 | 54 |

## SOLUSDT

| candidate | eligible | neutral_ratio | side_ratio | allowed_side | nrr027_proxy | nrr027_rate | buy | sell |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_quadratic | 136 | 99.26% | 0.74% | 0 | 0 | 0.00% | 0 | 1 |
| soft_power_p1_5 | 136 | 66.18% | 33.82% | 0 | 0 | 0.00% | 0 | 46 |
| decoupled_linear_floor075 | 136 | 56.62% | 43.38% | 0 | 0 | 0.00% | 0 | 59 |

## FACTS

- Baseline and candidate metrics were computed on the same recorder/regime/shield path.
- Candidate 1 uses soft_power p=1.5 as a representative in-band soft-power check.
- Candidate 2 uses linear admission, quadratic sizing, admission shield floor 0.75.
