#            Decision Making (                               )

##                                      

**                                       :** `decision_making`  
**                          :**                                                                         

##                                  

           `decision_making`                                                 Aurora.                                                                                  (            ,                       ,                 ,                      )                                                                                                                 .

###                                 
-                                                                  (OBI, TFI,             ,           )
-                                                                                
-                                                                      equity                    
-                                                                               

##                                

###                                    

#### DecisionMaking
                                      ,                                                                   .

**                          :**
-                                                                                       
-                                                                                              
-                                                                                                      

**                                          :**
- `start()` -                                  
- `stop()` -                                    

###                                          

####                              
```
on_features() + on_risk() + on_portfolio() + on_regime()
                                                 symbol_states
                                                                                 
                                                            
```

####                                             
```
_make_decision_for_symbol()
                                                                             Risk Management
                                                                          
                                                                       
                                                                
                                 EVT:TRADE_INTENT_PROPOSED
```

## FSM           

###                                

#### EVT:TRADE_INTENT_PROPOSED
**              :**                                                                                                    
**                      :** Execution Management, Audit Trail  

**Payload                   :**
```json
{
  "instrument": "BTCUSDT",
  "side": "buy",
  "order": {
    "qty": "0.001",
    "price": "50000.00",
    "price_ref": "50000.00",
    "reduce_only": false
  },
  "p": "0.75",
  "payoff_ratio_r": "2.0",
  "tca_budget": {
    "max_slippage_bps": "10",
    "max_latency_ms": 500,
    "maker_preference": "neutral"
  },
  "risk_budget": {
    "trade_cvar95_max_bps": "100",
    "session_cvar95_max_bps": "200"
  },
  "size": {
    "notional_cap_usd": "50.00",
    "kelly_fraction": "0.1"
  },
  "valid_for_ms": 5000,
  "why": ["signal_score=0.35, pos_size_usd=50.0"],
  "dto_version": "1.0.0",
  "schema_ref": "...",
  "idempotent_key": "uuid-string"
}
```

**        :**                                                                                                                      .

###                              

#### EVT:FEATURES_CALCULATED
**              :** Feature Engineering  
**                        :**                                                                                     
**              :**                            

#### EVT:RISK_ASSESSMENT_COMPLETED
**              :** Risk Management  
**                        :**                                                                              
**              :**                            

#### EVT:PORTFOLIO_STATE_UPDATED
**              :** Position Tracking  
**                        :**                                                  equity  
**              :**                            

#### EVT:REGIME_DETECTED
**              :** Regime Detector  
**                        :**                                                                             
**              :**                            

##                                                    

###                        '        

#### Feature Engineering
- **        :** EVT:FEATURES_CALCULATED
- **                        :** OBI, TFI, delta_price                                               
- **              :**                            

#### Risk Management
- **        :** EVT:RISK_ASSESSMENT_COMPLETED
- **                        :**                    is_trading_allowed
- **              :**                            

#### Position Tracking
- **        :** EVT:PORTFOLIO_STATE_UPDATED
- **                        :**                    equity        sizing
- **              :**                            

#### Regime Detector
- **        :** EVT:REGIME_DETECTED
- **                        :**                                -                                 
- **              :**                            

#### Execution Management
- **          :** EVT:TRADE_INTENT_PROPOSED
- **                        :**                                                     
- **              :**               

###                                          
                                                                                                                                        .

##                                                 

###                                    
```
signal_score = OBI    w_obi + TFI    w_tfi + delta_price    w_delta_price
```

**            :**
- `signal_score > threshold`     BUY
- `signal_score < -threshold`     SELL
- `|signal_score|     threshold`     HOLD

###                            
```
position_size_usd = min(liquidity_cap, equity    risk_fraction)
quantity = position_size_usd / price
rounded_quantity = floor(quantity / step_size)    step_size
```

###               
1. **Risk Filter:**                    `is_trading_allowed`
2. **Regime Filter:**                                -                                   
3. **Equity Filter:**                                                        equity
4. **Size Filter:**                                                   

##                         

###                                  
```yaml
decision:
  signal_weights:
    obi: 0.6
    tfi: 0.35
    delta_price: 0.05
  signal_threshold: 0.05
  position_sizing:
    min_position_size_usd: 10
    liquidity_based_cap_usd: 10000

tca_prefs:
  max_slippage_pct: 0.5
  preferred_venue: "binance"
  execution_priority: "speed"

risk_budgets:
  max_portfolio_risk_pct: 5.0
  max_single_position_risk_pct: 1.0
  max_daily_loss_pct: 2.0
```

###                          
- **live:**                                                               
- **testnet:**                                                                 

##                                                 

###                   
- **                                                 :**                 /                                                           
- **                        :**                        equity,                                      
- **Debug:**                                                                           

###               
-                                      /                                 
-                                                   
-                                             
-                                                   

##                              

###                                          
1. **                         :**                                                                      
2. **                                   :**                                                               
3. **                        :**                                                     

### Graceful degradation
                                                                                                             .

##                     

###                                    
-                                                       features      intent
-                                          edge cases
-                                                            

###                            
-                                                                                
-                                 sizing
-                                                                

##                     

###                                      
- **ML-based signals:**                                                         
- **Multi-timeframe analysis:**                                                      
- **Portfolio optimization:**                                                     
- **Dynamic thresholds:**                                                 