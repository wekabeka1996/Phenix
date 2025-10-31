#  î æ º µ Ω Regime Detector ( í ∏ è ≤ ª µ Ω Ω è  † µ ∂ ∏ º ñ ≤  † ∏ Ω ∫ É)

##  ó   ≥   ª å Ω    ñ Ω Ñ æ   º   Ü ñ è

** Ü ¥ µ Ω Ç ∏ Ñ ñ ∫   Ç æ    ¥ æ º µ Ω É:** `regime_detector`  
** † æ ª å  ≤    ∏   Ç µ º ñ:**  ê Ω   ª ñ ∑    ∏ Ω ∫ æ ≤ ∏ Ö    µ ∂ ∏ º ñ ≤  ¥ ª è    ¥     Ç ∏ ≤ Ω æ ó  Ç æ   ≥ ñ ≤ ª ñ

##  ê   Ö ñ Ç µ ∫ Ç É   Ω      æ ª å

 î æ º µ Ω `regime_detector`  ≤ ∏ ∫ æ Ω É î  Ñ É Ω ∫ Ü ñ é    ∏ Ω ∫ æ ≤ æ ≥ æ    Ω   ª ñ ∑   Ç æ    ,  ≤ ∏ ∑ Ω   á   é á ∏    æ Ç æ á Ω ∏ π    Ç   Ω    ∏ Ω ∫ É ( Ç   µ Ω ¥,  ≤ æ ª   Ç ∏ ª å Ω ñ   Ç å, ranging).  í ñ Ω    Ω   ª ñ ∑ É î  Ç µ Ö Ω ñ á Ω ñ  ñ Ω ¥ ∏ ∫   Ç æ   ∏  ¥ ª è  ∫ ª     ∏ Ñ ñ ∫   Ü ñ ó    ∏ Ω ∫ æ ≤ ∏ Ö  É º æ ≤  Ç    ∑   ± µ ∑   µ á µ Ω Ω è regime-aware  Ç æ   ≥ æ ≤ ∏ Ö    ñ à µ Ω å.

###  í ñ ¥   æ ≤ ñ ¥   ª å Ω ñ   Ç å
-  í ∏ è ≤ ª µ Ω Ω è  Ç   µ Ω ¥ æ ≤ ∏ Ö    µ ∂ ∏ º ñ ≤ (TREND_UP, TREND_DOWN)
-  û Ü ñ Ω ∫    ≤ æ ª   Ç ∏ ª å Ω æ   Ç ñ (HIGH_VOLATILITY, LOW_VOLATILITY)
-  î µ Ç µ ∫ Ü ñ è ranging  É º æ ≤ (MEAN_REVERSION)
-  † æ ∑     Ö É Ω æ ∫ confidence scores  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ    µ ∂ ∏ º É

##  ° Ç   É ∫ Ç É      ¥ æ º µ Ω É

###  û   Ω æ ≤ Ω ñ  ∫ æ º   æ Ω µ Ω Ç ∏

#### RegimeDetector
 ì æ ª æ ≤ Ω ∏ π  ∫ ª      ¥ æ º µ Ω É,  â æ    µ   ª ñ ∑ É î    Ω   ª ñ ∑    µ ∂ ∏ º ñ ≤.

** Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è:**
-  ó   ≤   Ω Ç   ∂ µ Ω Ω è  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó  º æ ¥ µ ª µ π  ≤ ∏ è ≤ ª µ Ω Ω è
-  ù   ª   à Ç É ≤   Ω Ω è    æ   æ ≥ ñ ≤  Ç            º µ Ç   ñ ≤
-  ü ñ ¥ Ç   ∏ º ∫   multiple detection models

** ú µ Ç æ ¥ ∏  ∂ ∏ Ç Ç î ≤ æ ≥ æ  Ü ∏ ∫ ª É:**
- `handle_event()` -  æ ±   æ ± ∫   EVT:FEATURES_CALCULATED

###  í Ω É Ç   ñ à Ω è      Ö ñ Ç µ ∫ Ç É    

#### Hierarchical Detection Logic
```
handle_event() -> detect regime
    ‚îú‚î ‚î  PRIORITY 1: Volatility regime (HIGH/LOW_VOLATILITY)
    ‚îú‚î ‚î  PRIORITY 2: Mean reversion (MEAN_REVERSION)
    ‚îî‚î ‚î  PRIORITY 3: Trend detection (TREND_UP/TREND_DOWN)
```

#### Confidence Calculation
```
_calculate_confidence() -> confidence score
    ‚îú‚î ‚î  Spread ratio: (sma_short - sma_long) / sma_long
    ‚îú‚î ‚î  Heuristic scaling: spread_ratio √ó 20.0
    ‚îî‚î ‚î  Bounding: [0.5, 0.95]
```

## FSM    æ ¥ ñ ó

###  ì µ Ω µ   æ ≤   Ω ñ    æ ¥ ñ ó

#### EVT:REGIME_DETECTED
** ß     Ç æ Ç  :**  ü   ∏  æ Ç   ∏ º   Ω Ω ñ EVT:FEATURES_CALCULATED  
** ù         ≤ ª µ Ω Ω è:** Decision Making  

**Payload    Ç   É ∫ Ç É    :**
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "regime": "TREND_UP",
  "confidence": "0.77",
  "source_model": "sma_trend_v1"
}
```

** û   ∏  :**  ü µ   µ ¥   î  ≤ ∏ è ≤ ª µ Ω ∏ π    ∏ Ω ∫ æ ≤ ∏ π    µ ∂ ∏ º  ∑    ñ ≤ Ω µ º confidence.

###  °   æ ∂ ∏ ≤   Ω ñ    æ ¥ ñ ó

#### EVT:FEATURES_CALCULATED
** î ∂ µ   µ ª æ:** Feature Engineering  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  û Ç   ∏ º   Ω Ω è  Ç µ Ö Ω ñ á Ω ∏ Ö  ñ Ω ¥ ∏ ∫   Ç æ   ñ ≤  ¥ ª è    Ω   ª ñ ∑ É    µ ∂ ∏ º ñ ≤  
** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É

##  í ∑   î º æ ¥ ñ è  ∑  ñ Ω à ∏ º ∏  ¥ æ º µ Ω   º ∏

###  ° ∏ Ω Ö   æ Ω Ω ñ  ∑ ≤' è ∑ ∫ ∏

#### Feature Engineering
- ** í Ö ñ ¥:** EVT:FEATURES_CALCULATED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:** SMA, ATR, price  ¥ ª è detection algorithms
- ** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É

#### Decision Making
- ** í ∏ Ö ñ ¥:** EVT:REGIME_DETECTED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  § ñ ª å Ç     Ü ñ è  ∫ æ Ω Ç  - Ç   µ Ω ¥ æ ≤ ∏ Ö    ∏ ≥ Ω   ª ñ ≤
- ** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É

###  ê   ∏ Ω Ö   æ Ω Ω ñ  ∑   ª µ ∂ Ω æ   Ç ñ
 î æ ¥   Ç ∫ æ ≤ ∏ π  Ñ ñ ª å Ç    ¥ ª è Decision Making domain.

##  ê ª ≥ æ   ∏ Ç º ∏  ≤ ∏ è ≤ ª µ Ω Ω è    µ ∂ ∏ º ñ ≤

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
    ‚îú‚î ‚î  sma_spread < 0.005
    ‚îú‚î ‚î  price_deviation_short < 0.005
    ‚îî‚î ‚î  price_deviation_long < 0.005
```

##  ö æ Ω Ñ ñ ≥ É     Ü ñ è

###  û   Ω æ ≤ Ω ñ          º µ Ç   ∏
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

###  † µ ∂ ∏ º ∏    æ ± æ Ç ∏
- **live:**  ê Ω   ª ñ ∑  ± æ π æ ≤ ∏ Ö    ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö
- **testnet:**  ê Ω   ª ñ ∑  Ç µ   Ç æ ≤ ∏ Ö    ∏ Ω ∫ æ ≤ ∏ Ö  ¥   Ω ∏ Ö

##  ú æ Ω ñ Ç æ   ∏ Ω ≥  Ç    ¥ ñ   ≥ Ω æ   Ç ∏ ∫  

###  ú µ Ç   ∏ ∫ ∏
- Regime distribution    æ  á     É
- Confidence score statistics
- Model accuracy tracking
- Detection latency

###  õ æ ≥ É ≤   Ω Ω è
- ** Ü Ω Ñ æ   º   Ü ñ π Ω ñ:**  í ∏ è ≤ ª µ Ω ñ    µ ∂ ∏ º ∏  ∑ confidence
- **Debug:**  î µ Ç   ª ñ    æ ∑     Ö É Ω ∫ ñ ≤  ¥ ª è  ∫ æ ∂ Ω æ ≥ æ    µ ∂ ∏ º É
- ** ü æ   µ   µ ¥ ∂ µ Ω Ω è:** Missing features  ¥ ª è detection

##  û ±   æ ± ∫      æ º ∏ ª æ ∫

###  ° Ç     Ç µ ≥ ñ ó  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è
1. **Missing features:** Fallback  ¥ æ  ±   ∑ æ ≤ ∏ Ö  º æ ¥ µ ª µ π
2. **Invalid data:** Conservative assumption (UNCERTAIN)
3. **Model failures:** Graceful degradation

### Graceful degradation
 ü   ∏  ≤ ñ ¥   É Ç Ω æ   Ç ñ  ¥   Ω ∏ Ö    µ   µ Ö æ ¥ ∏ Ç å  ¥ æ  ±   ∑ æ ≤ ∏ Ö    ª ≥ æ   ∏ Ç º ñ ≤.

##  ¢ µ   Ç É ≤   Ω Ω è

###  Ü Ω Ç µ ≥     Ü ñ π Ω ñ  Ç µ   Ç ∏
-  í   ª ñ ¥   Ü ñ è  ≤   ñ Ö detection algorithms
-  ü µ   µ ≤ ñ   ∫   confidence calculations
-  ¢ µ   Ç É ≤   Ω Ω è    ñ ∑ Ω ∏ Ö    ∏ Ω ∫ æ ≤ ∏ Ö    Ü µ Ω     ñ ó ≤

###  ú æ ¥ É ª å Ω ñ  Ç µ   Ç ∏
-  ü µ   µ ≤ ñ   ∫    ∫ æ ∂ Ω æ ≥ æ detection condition
-  í   ª ñ ¥   Ü ñ è confidence formulas
-  ¢ µ   Ç É ≤   Ω Ω è edge cases

##  ê   Ö ñ Ç µ ∫ Ç É   Ω ñ  æ   æ ± ª ∏ ≤ æ   Ç ñ

### Multi-Model Architecture
 ü ñ ¥ Ç   ∏ º ∫      ñ ∑ Ω ∏ Ö  º æ ¥ µ ª µ π detection:
- **SMA Trend:**  ö ª     ∏ á Ω ∏ π trend following
- **Volatility:** Risk-based filtering
- **Mean Reversion:** Range-bound markets

### Hierarchical Priority
```
Volatility > Mean Reversion > Trend
```
 ë ñ ª å à  ∫   ∏ Ç ∏ á Ω ñ    µ ∂ ∏ º ∏  º   é Ç å  ≤ ∏ â ∏ π      ñ æ   ∏ Ç µ Ç.

### Confidence Scoring
 ö æ ∂ Ω µ  ≤ ∏ è ≤ ª µ Ω Ω è  ≤ ∫ ª é á   î confidence score  ¥ ª è:
- Decision weighting
- Risk adjustment
- Performance tracking

##  † æ ∑ à ∏   µ Ω Ω è

###  ú   π ± É Ç Ω ñ  º æ ¥ µ ª ñ
- **Machine Learning:** ML-based regime classification
- **Multi-timeframe:** Cross-timeframe regime analysis
- **Inter-market:** Cross-asset regime detection
- **Sentiment analysis:** News-based regime detection