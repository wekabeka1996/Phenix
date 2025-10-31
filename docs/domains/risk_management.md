#  î æ º µ Ω Risk Management ( £       ≤ ª ñ Ω Ω è  † ∏ ∑ ∏ ∫   º ∏)

##  ó   ≥   ª å Ω    ñ Ω Ñ æ   º   Ü ñ è

** Ü ¥ µ Ω Ç ∏ Ñ ñ ∫   Ç æ    ¥ æ º µ Ω É:** `risk_management`  
** † æ ª å  ≤    ∏   Ç µ º ñ:**  û Ü ñ Ω ∫    Ç    ∫ æ Ω Ç   æ ª å  Ç æ   ≥ æ ≤ ∏ Ö    ∏ ∑ ∏ ∫ ñ ≤

##  ê   Ö ñ Ç µ ∫ Ç É   Ω      æ ª å

 î æ º µ Ω `risk_management`  ≤ ∏ ∫ æ Ω É î  Ñ É Ω ∫ Ü ñ é "gatekeeper"    ∏   Ç µ º ∏ Aurora,  æ Ü ñ Ω é é á ∏    ∏ ∑ ∏ ∫ ∏  Ω      ñ ≤ Ω ñ    æ   Ç Ñ µ ª è  Ç    æ ∫   µ º ∏ Ö  ñ Ω   Ç   É º µ Ω Ç ñ ≤.  í ñ Ω    Ω   ª ñ ∑ É î    ∏ Ω ∫ æ ≤ ñ  É º æ ≤ ∏,  ≤ æ ª   Ç ∏ ª å Ω ñ   Ç å  Ç      Ç   Ω    æ   Ç Ñ µ ª è  ¥ ª è      ∏ π Ω è Ç Ç è    ñ à µ Ω Ω è      æ  ¥ æ ∑ ≤ ñ ª  Ç æ   ≥ ñ ≤ ª ñ.

###  í ñ ¥   æ ≤ ñ ¥   ª å Ω ñ   Ç å
-  † æ ∑     Ö É Ω æ ∫  ∫ æ º   æ ∑ ∏ Ç Ω æ ≥ æ risk score  ∑  Ç µ Ö Ω ñ á Ω ∏ Ö  ñ Ω ¥ ∏ ∫   Ç æ   ñ ≤
-  ú æ Ω ñ Ç æ   ∏ Ω ≥ drawdown  ª ñ º ñ Ç ñ ≤    æ   Ç Ñ µ ª è
-  ö æ Ω Ç   æ ª å  ¥ æ ∑ ≤ æ ª É  Ω    Ç æ   ≥ ñ ≤ ª é (circuit breaker)
-  û Ü ñ Ω ∫    ≤ æ ª   Ç ∏ ª å Ω æ   Ç ñ  Ç      ∏ Ω ∫ æ ≤ ∏ Ö    ∏ ∑ ∏ ∫ ñ ≤

##  ° Ç   É ∫ Ç É      ¥ æ º µ Ω É

###  û   Ω æ ≤ Ω ñ  ∫ æ º   æ Ω µ Ω Ç ∏

#### RiskManagement
 ì æ ª æ ≤ Ω ∏ π  ∫ ª      ¥ æ º µ Ω É,  â æ    µ   ª ñ ∑ É î  æ Ü ñ Ω ∫ É    ∏ ∑ ∏ ∫ ñ ≤.

** Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è:**
-  ü ñ ¥   ∏   ∫    Ω      æ ¥ ñ ó features  Ç   portfolio updates
-  Ü Ω ñ Ü ñ   ª ñ ∑   Ü ñ è tracking  ¥ ª è peak equity  Ç   drawdown
-  ó   ≤   Ω Ç   ∂ µ Ω Ω è  ∫ æ Ω Ñ ñ ≥ É     Ü ñ ó    ∏ ∑ ∏ ∫ ñ ≤

** ú µ Ç æ ¥ ∏  ∂ ∏ Ç Ç î ≤ æ ≥ æ  Ü ∏ ∫ ª É:**
- `on_features_calculated()` -  æ ±   æ ± ∫    Ç µ Ö Ω ñ á Ω ∏ Ö  ñ Ω ¥ ∏ ∫   Ç æ   ñ ≤
- `on_portfolio_state_updated()` -  æ Ω æ ≤ ª µ Ω Ω è  º µ Ç   ∏ ∫    æ   Ç Ñ µ ª è

###  í Ω É Ç   ñ à Ω è      Ö ñ Ç µ ∫ Ç É    

####  î ≤ æ Ö   ñ ≤ Ω µ ≤    æ Ü ñ Ω ∫      ∏ ∑ ∏ ∫ ñ ≤
```
_calculate_risk_parameters()
    ‚îú‚î ‚î  Portfolio-level check (circuit breaker)
    ‚îÇ   ‚îî‚î ‚î  Drawdown limit validation
    ‚îî‚î ‚î  Instrument-level check (risk score)
        ‚îú‚î ‚î  Feature normalization
        ‚îú‚î ‚î  Risk score calculation
        ‚îî‚î ‚î  Trading permission decision
```

#### Drawdown tracking
```
on_portfolio_state_updated()
    ‚îú‚î ‚î  Peak equity tracking
    ‚îú‚î ‚î  Current drawdown calculation
    ‚îî‚î ‚î  Circuit breaker activation
```

## FSM    æ ¥ ñ ó

###  ì µ Ω µ   æ ≤   Ω ñ    æ ¥ ñ ó

#### EVT:RISK_ASSESSMENT_COMPLETED
** ß     Ç æ Ç  :**  ü   ∏  æ Ç   ∏ º   Ω Ω ñ EVT:FEATURES_CALCULATED  
** ù         ≤ ª µ Ω Ω è:** Decision Making  

**Payload    Ç   É ∫ Ç É    :**
```json
{
  "symbol": "BTCUSDT",
  "ts": 1640995200000,
  "risk_parameters": {
    "is_trading_allowed": true
  }
}
```

** û   ∏  :**  ü µ   µ ¥   î    ñ à µ Ω Ω è      æ  ¥ æ ∑ ≤ ñ ª  Ç æ   ≥ ñ ≤ ª ñ  Ω    æ   Ω æ ≤ ñ  æ Ü ñ Ω ∫ ∏    ∏ ∑ ∏ ∫ ñ ≤.

###  °   æ ∂ ∏ ≤   Ω ñ    æ ¥ ñ ó

#### EVT:FEATURES_CALCULATED
** î ∂ µ   µ ª æ:** Feature Engineering  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  û Ç   ∏ º   Ω Ω è  Ç µ Ö Ω ñ á Ω ∏ Ö  ñ Ω ¥ ∏ ∫   Ç æ   ñ ≤  ¥ ª è    æ ∑     Ö É Ω ∫ É risk score  
** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É

#### EVT:PORTFOLIO_STATE_UPDATED
** î ∂ µ   µ ª æ:** Position Tracking  
** í ∏ ∫ æ   ∏   Ç   Ω Ω è:**  ú æ Ω ñ Ç æ   ∏ Ω ≥ equity  ¥ ª è drawdown control  
** ß     Ç æ Ç  :**  ü ñ   ª è  ∫ æ ∂ Ω æ ≥ æ  Ç   µ π ¥ É

##  í ∑   î º æ ¥ ñ è  ∑  ñ Ω à ∏ º ∏  ¥ æ º µ Ω   º ∏

###  ° ∏ Ω Ö   æ Ω Ω ñ  ∑ ≤' è ∑ ∫ ∏

#### Feature Engineering
- ** í Ö ñ ¥:** EVT:FEATURES_CALCULATED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:** OBI, TFI, delta_price  ¥ ª è risk score
- ** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É

#### Position Tracking
- ** í Ö ñ ¥:** EVT:PORTFOLIO_STATE_UPDATED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:** Equity tracking  ¥ ª è drawdown limits
- ** ß     Ç æ Ç  :**  ü ñ   ª è  Ç   µ π ¥ ñ ≤

#### Decision Making
- ** í ∏ Ö ñ ¥:** EVT:RISK_ASSESSMENT_COMPLETED
- ** í ∏ ∫ æ   ∏   Ç   Ω Ω è:** is_trading_allowed  ¥ ª è  Ñ ñ ª å Ç     Ü ñ ó    ∏ ≥ Ω   ª ñ ≤
- ** ß     Ç æ Ç  :**  † µ   ª å Ω æ ≥ æ  á     É

###  ê   ∏ Ω Ö   æ Ω Ω ñ  ∑   ª µ ∂ Ω æ   Ç ñ
 ö   ∏ Ç ∏ á Ω ∏ π guardrail  ¥ ª è  ≤   ñ î ó  Ç æ   ≥ æ ≤ æ ó  ª æ ≥ ñ ∫ ∏.

##  † æ ∑     Ö É Ω æ ∫ Risk Score

###  ö æ º   æ ∑ ∏ Ç Ω ∏ π risk score
```
risk_score = delta_price_pct √ó w_delta +
             |obi| √ó w_obi +
             |tfi| √ó w_tfi +
             (1 - absorption) √ó w_absorption_inverse
```

** ù æ   º   ª ñ ∑   Ü ñ è:**
- `delta_price_pct`:    ±   æ ª é Ç Ω    ∑ º ñ Ω   ‚Üí  ≤ ñ ¥ Ω æ   Ω   (%)
- `obi`, `tfi`:  ≤ ∂ µ  ≤  ¥ ñ       ∑ æ Ω ñ [-1, 1]
- `absorption`:  ñ Ω ≤ µ     ñ è ( ≤ ∏ â   absorption =  Ω ∏ ∂ á ∏ π    ∏ ∑ ∏ ∫)

### Trading permission
```
is_trading_allowed = risk_score ‚â§ max_risk_score_threshold
```

### Circuit Breaker (Portfolio-level)
```
if current_drawdown > max_daily_drawdown_limit:
    is_trading_allowed = False  #  î ª è  ≤   ñ Ö    ∏ º ≤ æ ª ñ ≤
```

##  ö æ Ω Ñ ñ ≥ É     Ü ñ è

###  û   Ω æ ≤ Ω ñ          º µ Ç   ∏
```yaml
risk:
  max_daily_drawdown_limit: 0.05  # 5%
  score_weights:
    delta_price: 0.05
    obi: 0.35
    tfi: 0.35
    absorption_inverse: 0.25
  trading_allowed_thresholds:
    max_risk_score: 0.8
```

###  † µ ∂ ∏ º ∏    æ ± æ Ç ∏
- **live:**  û Ü ñ Ω ∫      ∏ ∑ ∏ ∫ ñ ≤  Ω    ± æ π æ ≤ ∏ Ö  ¥   Ω ∏ Ö
- **testnet:**  û Ü ñ Ω ∫      ∏ ∑ ∏ ∫ ñ ≤  Ω    Ç µ   Ç æ ≤ ∏ Ö  ¥   Ω ∏ Ö

## Circuit Breaker Logic

### Portfolio-level Protection
1. **Drawdown Monitoring:**  í ñ ¥   Ç µ ∂ µ Ω Ω è peak equity
2. **Threshold Breach:**  ê ≤ Ç æ º   Ç ∏ á Ω µ  ± ª æ ∫ É ≤   Ω Ω è  Ç æ   ≥ ñ ≤ ª ñ
3. **Critical Logging:**  ü æ ≤ ñ ¥ æ º ª µ Ω Ω è      æ    æ   É à µ Ω Ω è  ª ñ º ñ Ç ñ ≤

### Recovery
-  ê ≤ Ç æ º   Ç ∏ á Ω µ  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è      ∏  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω ñ equity
-  † É á Ω µ    µ   µ ∑     É   ∫  º æ ∂ ª ∏ ≤ ∏ π      ∏    æ Ç   µ ± ñ

##  ú æ Ω ñ Ç æ   ∏ Ω ≥  Ç    ¥ ñ   ≥ Ω æ   Ç ∏ ∫  

###  ú µ Ç   ∏ ∫ ∏
- Risk score distribution    æ    ∏ º ≤ æ ª   Ö
- Drawdown tracking over time
- Circuit breaker activation frequency
- Trading permission success rate

###  õ æ ≥ É ≤   Ω Ω è
- ** Ü Ω Ñ æ   º   Ü ñ π Ω ñ:** Risk assessments, score calculations
- ** ü æ   µ   µ ¥ ∂ µ Ω Ω è:** High risk scores, approaching limits
- ** ö   ∏ Ç ∏ á Ω ñ:** Circuit breaker activations, drawdown breaches

##  û ±   æ ± ∫      æ º ∏ ª æ ∫

###  ° Ç     Ç µ ≥ ñ ó  ≤ ñ ¥ Ω æ ≤ ª µ Ω Ω è
1. **Invalid features:** Conservative assumption (high risk)
2. **Missing portfolio data:** Fallback  ¥ æ instrument-only checks
3. **Config errors:** Default thresholds

### Graceful degradation
 ü   ∏      æ ± ª µ º   Ö      æ ¥ æ ≤ ∂ É î    æ ± æ Ç É  ∑ conservative settings.

##  ¢ µ   Ç É ≤   Ω Ω è

###  Ü Ω Ç µ ≥     Ü ñ π Ω ñ  Ç µ   Ç ∏
-  í   ª ñ ¥   Ü ñ è circuit breaker  ª æ ≥ ñ ∫ ∏
-  ü µ   µ ≤ ñ   ∫   risk score calculations
-  ¢ µ   Ç É ≤   Ω Ω è    ñ ∑ Ω ∏ Ö    ∏ Ω ∫ æ ≤ ∏ Ö  É º æ ≤

###  ú æ ¥ É ª å Ω ñ  Ç µ   Ç ∏
-  ü µ   µ ≤ ñ   ∫   normalization  Ñ É Ω ∫ Ü ñ π
-  í   ª ñ ¥   Ü ñ è threshold logic
-  ¢ µ   Ç É ≤   Ω Ω è drawdown calculations

##  ê   Ö ñ Ç µ ∫ Ç É   Ω ñ  æ   æ ± ª ∏ ≤ æ   Ç ñ

### Two-tier Risk Assessment
**Portfolio Level:** Circuit breaker  ¥ ª è  ∫   Ç     Ç   æ Ñ ñ á Ω ∏ Ö  ≤ Ç     Ç  
**Instrument Level:** Risk score  ¥ ª è  æ   Ç ∏ º   ª å Ω æ ≥ æ sizing

### Conservative Defaults
 ü   ∏  ≤ ñ ¥   É Ç Ω æ   Ç ñ  ¥   Ω ∏ Ö      ∏ π º   î conservative    æ ∑ ∏ Ü ñ é (high risk),  ∑   ± µ ∑   µ á É é á ∏  ± µ ∑   µ ∫ É.

### Real-time Adaptation
Risk parameters    µ   µ     Ö æ ≤ É é Ç å   è      ∏  ∫ æ ∂ Ω æ º É  Ω æ ≤ æ º É features event,  ∑   ± µ ∑   µ á É é á ∏    ∫ Ç É   ª å Ω É  æ Ü ñ Ω ∫ É.