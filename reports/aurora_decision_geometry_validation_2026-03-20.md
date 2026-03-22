# AURORA DECISION GEOMETRY VALIDATION

- Symbols: BTCUSDT, ETHUSDT, SOLUSDT
- Date window: 2026-03-20 .. 2026-03-20
- Source: recorder bars + RegimeDetector + live shield cascade + current threshold surfaces
- NRR-027 metric: offline directional-sanity proxy, not live post-signal order-log replay

## BTCUSDT

| candidate | eligible | neutral_ratio | side_ratio | allowed_side | nrr027_proxy | nrr027_rate | buy | sell |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_quadratic | 0 | 0.00% | 0.00% | 0 | 0 | 0.00% | 0 | 0 |
| soft_power_p1_5 | 0 | 0.00% | 0.00% | 0 | 0 | 0.00% | 0 | 0 |
| decoupled_linear_floor075 | 0 | 0.00% | 0.00% | 0 | 0 | 0.00% | 0 | 0 |

## ETHUSDT

| candidate | eligible | neutral_ratio | side_ratio | allowed_side | nrr027_proxy | nrr027_rate | buy | sell |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_quadratic | 63 | 80.95% | 19.05% | 12 | 3 | 25.00% | 0 | 12 |
| soft_power_p1_5 | 63 | 28.57% | 71.43% | 37 | 6 | 13.33% | 0 | 45 |
| decoupled_linear_floor075 | 63 | 0.00% | 100.00% | 46 | 6 | 9.52% | 0 | 63 |

## SOLUSDT

| candidate | eligible | neutral_ratio | side_ratio | allowed_side | nrr027_proxy | nrr027_rate | buy | sell |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_quadratic | 116 | 52.59% | 47.41% | 49 | 6 | 10.91% | 0 | 55 |
| soft_power_p1_5 | 116 | 25.00% | 75.00% | 77 | 7 | 8.05% | 0 | 87 |
| decoupled_linear_floor075 | 116 | 0.00% | 100.00% | 97 | 9 | 7.76% | 0 | 116 |

## FACTS

- Baseline and candidate metrics were computed on the same recorder/regime/shield path.
- Candidate 1 uses soft_power p=1.5 as a representative in-band soft-power check.
- Candidate 2 uses linear admission, quadratic sizing, admission shield floor 0.75.
