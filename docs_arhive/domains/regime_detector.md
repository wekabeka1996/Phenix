#            Regime Detector (                                            )

##                                      

**                                       :** `regime_detector`  
**                          :**                                                                                          

##                                  

           `regime_detector`                                                                        ,                                                           (          ,                           , ranging).                                                                                                                                                       regime-aware                              .

###                                 
-                                                      (TREND_UP, TREND_DOWN)
-                                         (HIGH_VOLATILITY, LOW_VOLATILITY)
-                  ranging          (MEAN_REVERSION)
-                      confidence scores                                   

##                                

###                                    

#### RegimeDetector
                                      ,                                                  .

**                          :**
-                                                                                    
-                                                                  
-                    multiple detection models

**                                          :**
- `handle_event()` -                EVT:FEATURES_CALCULATED

###                                          

#### Hierarchical Detection Logic
```
handle_event() -> detect regime
              PRIORITY 1: Volatility regime (HIGH/LOW_VOLATILITY)
              PRIORITY 2: Mean reversion (MEAN_REVERSION)
              PRIORITY 3: Trend detection (TREND_UP/TREND_DOWN)
```

#### Confidence Calculation
```
_calculate_confidence() -> confidence score
              Spread ratio: (sma_short - sma_long) / sma_long
              Heuristic scaling: spread_ratio    20.0
              Bounding: [0.5, 0.95]
```

## FSM           

###                                

#### EVT:REGIME_DETECTED
**              :**                           EVT:FEATURES_CALCULATED  
**                      :** Decision Making  

**Payload                   :**
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "regime": "TREND_UP",
  "confidence": "0.77",
  "source_model": "sma_trend_v1"
}
```

**        :**                                                                               confidence.

###                              

#### EVT:FEATURES_CALCULATED
**              :** Feature Engineering  
**                        :**                                                                                                    
**              :**                            

##                                                    

###                        '        

#### Feature Engineering
- **        :** EVT:FEATURES_CALCULATED
- **                        :** SMA, ATR, price        detection algorithms
- **              :**                            

#### Decision Making
- **          :** EVT:REGIME_DETECTED
- **                        :**                                -                                   
- **              :**                            

###                                          
                                         Decision Making domain.

##                                                     

### Trend Detection (SMA-based)
```
TREND_UP: sma_short > sma_long AND price > sma_short
TREND_DOWN: sma_short < sma_long AND price < sma_short
```

### Volatility Regime
```
HIGH_VOLATILITY: atr_14 / atr_14_sma_100 > threshold_multiplier
LOW_VOLATILITY: atr_14 / atr_14_sma_100 < low_vol_multiplier
```

### Mean Reversion
```
MEAN_REVERSION: all values within 0.5% of each other
              sma_spread < 0.005
              price_deviation_short < 0.005
              price_deviation_long < 0.005
```

##                         

###                                  
```yaml
models:
  sma_trend:
    # Basic trend detection parameters
  volatility:
    enabled: true
    threshold_multiplier: 2.0
    low_vol_multiplier: 0.5
  mean_reversion:
    threshold: 0.005  # 0.5%
```

###                          
- **live:**                                                        
- **testnet:**                                                          

##                                                 

###               
- Regime distribution              
- Confidence score statistics
- Model accuracy tracking
- Detection latency

###                   
- **                        :**                                  confidence
- **Debug:**                                                                       
- **                        :** Missing features        detection

##                              

###                                          
1. **Missing features:** Fallback                                   
2. **Invalid data:** Conservative assumption (UNCERTAIN)
3. **Model failures:** Graceful degradation

### Graceful degradation
                                                                                                      .

##                     

###                                    
-                             detection algorithms
-                    confidence calculations
-                                                                      

###                            
-                                   detection condition
-                    confidence formulas
-                      edge cases

##                                                

### Multi-Model Architecture
                                               detection:
- **SMA Trend:**                    trend following
- **Volatility:** Risk-based filtering
- **Mean Reversion:** Range-bound markets

### Hierarchical Priority
```
Volatility > Mean Reversion > Trend
```
                                                                                 .

### Confidence Scoring
                                             confidence score       :
- Decision weighting
- Risk adjustment
- Performance tracking

##                     

###                              
- **Machine Learning:** ML-based regime classification
- **Multi-timeframe:** Cross-timeframe regime analysis
- **Inter-market:** Cross-asset regime detection
- **Sentiment analysis:** News-based regime detection