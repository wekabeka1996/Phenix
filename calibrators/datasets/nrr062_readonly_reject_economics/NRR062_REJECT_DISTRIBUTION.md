# NRR062_REJECT_DISTRIBUTION

| Metric | Value | Notes |
| --- | --- | --- |
| Reject Rows | 153 | canonical NRR062 cohort |
| Structured Rows | 153 | rows with parsed low_vol metadata |
| Parse Quality Counts | {"STRUCTURED_METADATA_COMPLETE": 153} | distribution input quality |

## symbol
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| symbol:ETHUSDT | 76 | 49.673203 |  |
| symbol:BTCUSDT | 47 | 30.718954 |  |
| symbol:XRPUSDT | 30 | 19.607843 |  |

## side
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| side:SELL | 114 | 74.509804 |  |
| side:BUY | 39 | 25.490196 |  |

## position_side
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| position_side:SHORT | 114 | 74.509804 |  |
| position_side:LONG | 39 | 25.490196 |  |

## strategy_id
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| strategy_id:aurora | 153 | 100 |  |

## regime
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| regime:LOW_VOLATILITY | 153 | 100 |  |

## selected_source
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| selected_source:signal_score | 153 | 100 |  |

## selected_scale
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| selected_scale:raw_signed_score | 153 | 100 |  |

## threshold_family
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| threshold_family:raw_signed_score | 153 | 100 |  |

## session
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| session:AMER_UTC_16_23 | 70 | 45.751634 |  |
| session:ASIA_UTC_00_07 | 52 | 33.986928 |  |
| session:EMEA_UTC_08_15 | 31 | 20.261438 |  |

## required_gross_tp_bps_floor_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| required_gross_tp_bps_floor_bucket:20-30bps | 153 | 100 |  |

## gross_tp_bps_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| gross_tp_bps_bucket:75-100bps | 153 | 100 |  |

## direction_confidence_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| direction_confidence_bucket:<0.01 | 130 | 84.96732 |  |
| direction_confidence_bucket:0.01-0.05 | 23 | 15.03268 |  |

## regime_confidence_bucket
| Segment | Rejects | Share | Notes |
| --- | --- | --- | --- |
| regime_confidence_bucket:>=0.39 | 103 | 67.320261 |  |
| regime_confidence_bucket:0.25-0.35 | 31 | 20.261438 |  |
| regime_confidence_bucket:0.15-0.25 | 12 | 7.843137 |  |
| regime_confidence_bucket:0.35-0.39 | 7 | 4.575163 |  |
