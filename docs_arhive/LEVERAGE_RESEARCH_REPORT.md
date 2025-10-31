#                                                                                    (Leverage)

**                               :** 22              2025  
**RID:** AURORA_LEVERAGE_RESEARCH_V1  
**            :**                                                            

---

##                                     

                  ,                     Aurora                                                                   (leverage)                              Binance Futures,                                                   .

---

##                                                 

###                                            :

#### 1. **                                                                **
**        :** `config/aurora/system.yaml`
```yaml
inventory_limits:
  max_abs_position: 500  #                               x50 pl      
  max_daily_notional: 10000000  # $10M                                x50
```

**        :** `config/aurora/trading.yaml`
```yaml
instruments:
  BTCUSDT:
    max_notional_usd: 10000000  # $10M per position        x50
  ETHUSDT:
    max_notional_usd: 10000000  # $10M per position        x50
```

**                :**                                                     x50,             **                           **,                                     .

---

#### 2. **               leverage    Account API**
**        :** `apps/reference/domains/account_balance/account_connector.py` (           248)
```python
'leverage': int(position.get('leverage', 1)),
'marginType': position.get('marginType', 'cross')
```

**                             :**
-                **          **                                                        Binance API
-                `marginType` (cross/isolated)
-                                   payload            `EVT:ACCOUNT_UPDATE_RECEIVED`

**                :**                **        **,                                                         ,        **                             **                          .

---

###                               :

#### 1. **                         leverage            API**
                                     `/fapi/v1/leverage` endpoint  
                              `set_leverage()`        `change_leverage()`  
                                                     leverage                                                   

**Binance API                                 leverage:**
```python
#                                              :
POST /fapi/v1/leverage
{
  "symbol": "BTCUSDT",
  "leverage": 50
}
```

---

#### 2. **                     leverage                                           **
**        :** `apps/reference/domains/decision_making/decision_making.py`

**                     qty:**
```python
#            220-221
cvar_trade_usd = equity * Decimal(risk_budgets['trade_cvar95_max_bps']) / Decimal('10000')
cvar_session_usd = equity * Decimal(risk_budgets['session_cvar95_max_bps']) / Decimal('10000')

#            266
kelly_based_size = equity * kelly_fraction * kelly_conservative_factor

#            258
notional_cap = min(kelly_based_cap, cvar_based_cap, liquidity_based_cap, default_notional_cap)

#            330 (                          qty)
qty_raw = position_size / price
```

**                :**                                               **equity** (                                 ),       :
-                          ,                      x50 **          ** = position_size / 50
-                                                                                             
-                            ,                                                                            

---

#### 3. **                                         leverage**
                                                             leverage  
                                                                   
                                     margin call

---

#### 4. **                 leverage                            **
                                               `leverage: 50`    `trading.yaml`  
                                ,                                                   
                                      ,                                                                           

---

##                                       :

### 1. **                                                   **
-                                                   **            **            Binance UI        API
-                                                                                            (                 x20        x1)
- **          :**                                                            (x50)                                   

---

### 2. **                     qty                       leverage**
**                               :**
```
Equity: $1000
CVaR limit: $150 (15%        equity)
BTC price: $100,000

       leverage:
- Position size: $150
- Qty: 0.0015 BTC
-                            : $150 (100%)

   leverage x50:
- Position size: $150
- Qty: 0.0015 BTC  
-                            : $3 (2%)                                               !
```

**                :**                                                                                       ,                                                    leverage.

---

### 3. **                                                     **
       leverage x50:
-                                                            entry price (~2%         )
-                                                                       
-                                                                         

---

### 4. **max_notional_usd = $10M                       **
```yaml
max_notional_usd: 10000000  # $10M per position        x50
```

         equity = $1000:
-    leverage x50                                           = $50,000
-            $10M                                                                  

---

##                              :

### **                               (URGENT):**

1. **                              leverage                            :**
```yaml
instruments:
  BTCUSDT:
    leverage: 50  #                 
    margin_type: "cross"  #                 
```

2. **                                                leverage                                  :**
```python
#    BinanceExecutionAdapter.__init__()
def _set_leverage(self, symbol: str, leverage: int):
    """Set leverage for symbol via Binance API."""
    params = {
        "symbol": symbol,
        "leverage": leverage,
        "timestamp": int(time.time() * 1000)
    }
    # Sign and POST to /fapi/v1/leverage
```

3. **                                                   leverage:**
```python
self.logger.info(f"[BinanceAdapter] Using leverage={leverage}x for {symbol}")
```

---

### **                                 (HIGH PRIORITY):**

4. **                                              qty                           leverage:**
```python
#    decision_making.py
required_margin = position_size / leverage
if required_margin > available_margin:
    # Reduce position size
    position_size = available_margin * leverage * safety_factor
```

5. **                                                               :**
```python
liquidation_price = entry_price * (1 - (1 / leverage) * margin_ratio)
min_distance_to_liquidation_pct = 5.0  # 5% safety buffer

if abs(current_price - liquidation_price) / current_price < min_distance_to_liquidation_pct / 100:
    self.logger.error("Position too close to liquidation!")
    return None  # Reject trade
```

6. **                                                      leverage:**
```yaml
risk:
  max_leverage: 50
  min_liquidation_distance_pct: 5.0  # Minimum 5% from liquidation
  margin_buffer_pct: 10.0  # Keep 10% margin buffer
```

---

### **                           (MEDIUM PRIORITY):**

7. **                       margin tracker:**
-                                                         
-                                               margin call
-                                                                                              

8. **                        isolated margin:**
-                              cascade liquidation
-                margin pool                                   

9. **Stress testing    leverage:**
-                                                                  
-                      max drawdown                           leverage
-                                                flash crash'    

---

##                      :

### **                         :**
               **                leverage**,             **          **                       .                                     **                     ** leverage,                               :
-                                                              (                                                         leverage)
-                                                                  
-                                                   

### **                      :**
     **                         **                                                               .  
     **                           **        testnet (                                                                        mainnet).

### **                           :**
1.                                          `leverage`                                
2.                        API                                              leverage    
3.                          qty calculation                           margin    
4.                                                                    

---

**                                 :** GitHub Copilot  
**                      :** [    '                       ]  
**            :** Draft v1.0  
