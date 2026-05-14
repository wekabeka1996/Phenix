# NRR062_REJECT_DISTRIBUTION

| Metric | Value | Notes |
| --- | --- | --- |
| Reject Rows | 227 | canonical NRR062 cohort |
| Structured Rows | 227 | rows with parsed low_vol metadata |
| Parse Quality Counts | {"STRUCTURED_METADATA_COMPLETE": 227} | distribution input quality |

## symbol
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| symbol:ETHUSDT | 108 | 47.577093 |  |
| symbol:BTCUSDT | 76 | 33.480176 |  |
| symbol:XRPUSDT | 43 | 18.942731 |  |

## side
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| side:SELL | 161 | 70.92511 |  |
| side:BUY | 66 | 29.07489 |  |

## position_side
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| position_side:SHORT | 161 | 70.92511 |  |
| position_side:LONG | 66 | 29.07489 |  |

## strategy_id
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| strategy_id:aurora | 227 | 100 |  |

## regime
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| regime:LOW_VOLATILITY | 227 | 100 |  |

## selected_source
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| selected_source:signal_score | 227 | 100 |  |

## selected_scale
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| selected_scale:raw_signed_score | 227 | 100 |  |

## threshold_family
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| threshold_family:raw_signed_score | 227 | 100 |  |

## session
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| session:AMER_UTC_16_23 | 114 | 50.220264 |  |
| session:ASIA_UTC_00_07 | 82 | 36.123348 |  |
| session:EMEA_UTC_08_15 | 31 | 13.656388 |  |

## required_gross_tp_bps_floor_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| required_gross_tp_bps_floor_bucket:20-30bps | 227 | 100 |  |

## gross_tp_bps_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| gross_tp_bps_bucket:75-100bps | 227 | 100 |  |

## direction_confidence_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| direction_confidence_bucket:<0.01 | 196 | 86.343612 |  |
| direction_confidence_bucket:0.01-0.05 | 31 | 13.656388 |  |

## regime_confidence_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| regime_confidence_bucket:>=0.39 | 146 | 64.317181 |  |
| regime_confidence_bucket:0.25-0.35 | 50 | 22.026432 |  |
| regime_confidence_bucket:0.15-0.25 | 18 | 7.929515 |  |
| regime_confidence_bucket:0.35-0.39 | 13 | 5.726872 |  |
