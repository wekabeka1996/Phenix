#  — ² – ‚      ¾  ´ ¾   » – ´ ¶ µ ½ ½     ¾ ± ¾ ‚ ¸    ¸   ‚ µ ¼ ¸  ·    » µ ‡ µ ¼ (Leverage)

** ”   ‚    ´ ¾   » – ´ ¶ µ ½ ½ :** 22  ¶ ¾ ² ‚ ½  2025  
**RID:** AURORA_LEVERAGE_RESEARCH_V1  
** ¡ ‚   ‚ ƒ  :** âš ï¸  š   ˜ ¢ ˜ §  †  Ÿ   ž “  › ˜  ˜  ’ ˜ ¯ ’ › •  ž

---

## ðŸŽ¯  œ µ ‚    ´ ¾   » – ´ ¶ µ ½ ½ 

 ’ ¸ · ½   ‡ ¸ ‚ ¸,  ‡ ¸    ¸   ‚ µ ¼   Aurora    ¾ · ƒ ¼ – ”  ‚    º ¾   µ º ‚ ½ ¾        † Ž ”  ·    » µ ‡ µ ¼ (leverage)      ¸  ‚ ¾   ³ – ² » –  ½   Binance Futures,  ‚     º  †   » ¾ ³ – º      µ   » – · ¾ ²   ½  .

---

## ðŸ“Š    µ · ƒ » Œ ‚   ‚ ¸  ´ ¾   » – ´ ¶ µ ½ ½ 

### âœ…  © ¾  —   ™ ” •  ž  ²    ¸   ‚ µ ¼ –:

#### 1. ** š ¾ ¼ µ ½ ‚     –      ¾    » µ ‡ µ  ²  º ¾ ½ „ – ³ ƒ     † – —**
** ¤   ¹ »:** `config/aurora/system.yaml`
```yaml
inventory_limits:
  max_abs_position: 500  #  œ  š ¡ ˜ œ  › ¬  ž    – ´ x50 pl µ ‡ µ
  max_daily_notional: 10000000  # $10M  ´ µ ½ ½ ¸ ¹  » – ¼ – ‚  ´ »  x50
```

** ¤   ¹ »:** `config/aurora/trading.yaml`
```yaml
instruments:
  BTCUSDT:
    max_notional_usd: 10000000  # $10M per position  ´ »  x50
  ETHUSDT:
    max_notional_usd: 10000000  # $10M per position  ´ »  x50
```

** ’ ¸   ½ ¾ ² ¾ º:**  š ¾ ¼ µ ½ ‚     –  ² º   · ƒ Ž ‚ Œ  ½      » µ ‡ µ x50,    » µ  † µ ** » ¸ ˆ µ  º ¾ ¼ µ ½ ‚     –**,  ½ µ    ¾ ± ¾ ‡ –          ¼ µ ‚   ¸.

---

#### 2. ** § ¸ ‚   ½ ½  leverage  · Account API**
** ¤   ¹ »:** `apps/reference/domains/account_balance/account_connector.py` (    ´ ¾ º 248)
```python
'leverage': int(position.get('leverage', 1)),
'marginType': position.get('marginType', 'cross')
```

** © ¾  ² – ´ ± ƒ ²   ” ‚ Œ   :**
-  ¡ ¸   ‚ µ ¼   ** § ˜ ¢  „**    ¾ ‚ ¾ ‡ ½ µ    » µ ‡ µ  ·    ¾ · ¸ † – ¹  ‡ µ   µ · Binance API
-  ž ‚   ¸ ¼ ƒ ” `marginType` (cross/isolated)
-  — ± µ   – ³   ”  † –  ´   ½ –  ƒ payload    ¾ ´ – — `EVT:ACCOUNT_UPDATE_RECEIVED`

** ’ ¸   ½ ¾ ² ¾ º:**  ¡ ¸   ‚ µ ¼   ** · ½   ”**,   º µ    » µ ‡ µ  ²   ‚   ½ ¾ ² » µ ½ ¾  ½    ± –   ¶ –,    » µ **  •  ’ ˜ š ž   ˜ ¡ ¢ ž ’ £ „**  † Ž  – ½ „ ¾   ¼   † – Ž.

---

### âŒ  © ¾   •  —   ™ ” •  ž:

#### 1. ** ’   ‚   ½ ¾ ² » µ ½ ½  leverage  ‡ µ   µ · API**
âŒ   µ ¼   ”  ² ¸ º » ¸ º – ²  ´ ¾ `/fapi/v1/leverage` endpoint  
âŒ   µ ¼   ”  „ ƒ ½ º † – ¹ `set_leverage()`    ± ¾ `change_leverage()`  
âŒ   µ ¼   ”  » ¾ ³ – º ¸  ²   ‚   ½ ¾ ² » µ ½ ½  leverage      ¸  – ½ – † –   » – ·   † – —    ´     ‚ µ    

**Binance API  ´ »   ²   ‚   ½ ¾ ² » µ ½ ½  leverage:**
```python
#   •    •  › † — ž ’   ž  ²    ¸   ‚ µ ¼ –:
POST /fapi/v1/leverage
{
  "symbol": "BTCUSDT",
  "leverage": 50
}
```

---

#### 2. ** ’     … ƒ ²   ½ ½  leverage      ¸    ¾ ·     … ƒ ½ º ƒ    ¾ · ¸ † – ¹**
** ¤   ¹ »:** `apps/reference/domains/decision_making/decision_making.py`

**   ¾ ·     … ƒ ½ ¾ º qty:**
```python
#     ´ ¾ º 220-221
cvar_trade_usd = equity * Decimal(risk_budgets['trade_cvar95_max_bps']) / Decimal('10000')
cvar_session_usd = equity * Decimal(risk_budgets['session_cvar95_max_bps']) / Decimal('10000')

#     ´ ¾ º 266
kelly_based_size = equity * kelly_fraction * kelly_conservative_factor

#     ´ ¾ º 258
notional_cap = min(kelly_based_cap, cvar_based_cap, liquidity_based_cap, default_notional_cap)

#     ´ ¾ º 330 ( º ¾ ½ ² µ   ‚   † –   ² qty)
qty_raw = position_size / price
```

** Ÿ   ¾ ± » µ ¼  :**    ¾ ·     … ƒ ½ ¾ º  ² ¸ º ¾   ¸   ‚ ¾ ² ƒ ” **equity** ( ´ ¾   ‚ ƒ   ½ ¸ ¹  º     – ‚   »),    » µ:
- âŒ   µ  ²     … ¾ ² ƒ ”,  ‰ ¾  ·    » µ ‡ µ ¼ x50 ** ¼     ¶  ** = position_size / 50
- âŒ   µ  ²     … ¾ ² ƒ ”    ¸ · ¸ º  » – º ² – ´   † – —      ¸  ² ¸   ¾ º ¾ ¼ ƒ    » µ ‡ –
- âŒ   µ    µ   µ ² –    ”,  ‡ ¸  ´ ¾   ‚   ‚ ½ Œ ¾  ¼     ¶ –  ´ »   ² – ´ º   ¸ ‚ ‚     ¾ · ¸ † – —

---

#### 3. ** —   … ¸   ‚  ² – ´  ½   ´ ¼ –   ½ ¾ ³ ¾ leverage**
âŒ   µ ¼   ”    µ   µ ² –   º ¸  ¼   º   ¸ ¼   » Œ ½ ¾ ³ ¾ leverage  
âŒ   µ ¼   ”    ¾ ·     … ƒ ½ º ƒ  † – ½ ¸  » – º ² – ´   † – —  
âŒ   µ ¼   ”  ·   … ¸   ‚ ƒ  ² – ´ margin call

---

#### 4. ** Ÿ       ¼ µ ‚   leverage  ƒ  º ¾ ½ „ – ³ ƒ     † – —**
âŒ   µ ¼   ”   ² ½ ¾ ³ ¾          ¼ µ ‚     `leverage: 50`  ƒ `trading.yaml`  
âŒ  ¡ ¸   ‚ µ ¼    ½ µ  · ½   ”,   º µ    » µ ‡ µ  ² ¸ º ¾   ¸   ‚ ¾ ² ƒ ²   ‚ ¸  
âŒ  Ÿ ¾ º »   ´   ” ‚ Œ     ½    ‚ µ,  ‰ ¾    » µ ‡ µ  ² ¶ µ  ²   ‚   ½ ¾ ² » µ ½ ¾  ½    ± –   ¶ –  ²   ƒ ‡ ½ ƒ

---

## ðŸ”´  š   ˜ ¢ ˜ §  †  Ÿ   ž ‘ › • œ ˜:

### 1. ** ¡ ¸   ‚ µ ¼     •  ²   ‚   ½ ¾ ² » Ž ”    » µ ‡ µ**
-  Ÿ » µ ‡ µ  ¼   ”  ± ƒ ‚ ¸  ²   ‚   ½ ¾ ² » µ ½ ¾ ** ’   £ §  £**  ‡ µ   µ · Binance UI    ± ¾ API
-  ¯ º ‰ ¾    » µ ‡ µ  ½ µ  ²   ‚   ½ ¾ ² » µ ½ ¾ â†’        † Ž ”  ½    ´ µ „ ¾ » ‚ ½ ¾ ¼ ƒ ( ·   · ² ¸ ‡   ¹ x20    ± ¾ x1)
- **   ˜ — ˜ š:**   µ ² – ´   ¾ ² – ´ ½ –   ‚ Œ  ¼ – ¶  ¾ ‡ – º ƒ ²   ½ ¸ ¼ (x50)  ‚      µ   » Œ ½ ¸ ¼    » µ ‡ µ ¼

---

### 2. **   ¾ ·     … ƒ ½ ¾ º qty   •  ²     … ¾ ² ƒ ” leverage**
** Ÿ   ¸ º »   ´      ¾ ± » µ ¼ ¸:**
```
Equity: $1000
CVaR limit: $150 (15%  ² – ´ equity)
BTC price: $100,000

 ‘ • — leverage:
- Position size: $150
- Qty: 0.0015 BTC
-  Ÿ ¾ ‚   – ± ½    ¼     ¶  : $150 (100%)

 — leverage x50:
- Position size: $150
- Qty: 0.0015 BTC  
-  Ÿ ¾ ‚   – ± ½    ¼     ¶  : $3 (2%)  â†  ¡ ¸   ‚ µ ¼    † µ   •  ²     … ¾ ² ƒ ”!
```

**      » – ´ ¾ º:**  ¡ ¸   ‚ µ ¼    ¾ ± ¼ µ ¶ ƒ ”    ¾ · ¸ † – —  ·   ½   ´ ‚ ¾  º ¾ ½   µ   ²   ‚ ¸ ² ½ ¾,  ½ µ  ² ¸ º ¾   ¸   ‚ ¾ ² ƒ Ž ‡ ¸    µ   µ ²   ³ ¸ leverage.

---

### 3. **  µ ¼   ”  ·   … ¸   ‚ ƒ  ² – ´  » – º ² – ´   † – —**
 Ÿ   ¸ leverage x50:
-  ¦ – ½    » – º ² – ´   † – —  ´ ƒ ¶ µ  ± » ¸ · Œ º    ´ ¾ entry price (~2%    ƒ … ƒ)
-  ¡ ¸   ‚ µ ¼     •    ¾ ·     … ¾ ² ƒ ”  † – ½ ƒ  » – º ² – ´   † – —
-   µ ¼   ”    µ   µ ² –   º ¸  ² – ´   ‚   ½ –  ´ ¾  » – º ² – ´   † – —

---

### 4. **max_notional_usd = $10M  ½ µ  ¼   ”    µ ½   ƒ**
```yaml
max_notional_usd: 10000000  # $10M per position  ´ »  x50
```

 ¯ º ‰ ¾ equity = $1000:
-  — leverage x50 â†’  ¼   º   ¸ ¼   » Œ ½      ¾ · ¸ † –  = $50,000
-  › – ¼ – ‚ $10M  ½ µ ´ ¾    ¶ ½ ¸ ¹  –  ½ µ  ·   … ¸ ‰   ”  ² – ´    ¸ · ¸ º – ²

---

## ðŸ’¡    µ º ¾ ¼ µ ½ ´   † – —:

### ** š ¾   ¾ ‚ º ¾   ‚   ¾ º ¾ ² – (URGENT):**

1. ** ” ¾ ´   ‚ ¸          ¼ µ ‚   leverage  ƒ  º ¾ ½ „ – ³ ƒ     † – Ž:**
```yaml
instruments:
  BTCUSDT:
    leverage: 50  # â†  ” ž ”  ¢ ˜
    margin_type: "cross"  # â†  ” ž ”  ¢ ˜
```

2. **   µ   » – · ƒ ²   ‚ ¸  ²   ‚   ½ ¾ ² » µ ½ ½  leverage      ¸  – ½ – † –   » – ·   † – —:**
```python
#  £ BinanceExecutionAdapter.__init__()
def _set_leverage(self, symbol: str, leverage: int):
    """Set leverage for symbol via Binance API."""
    params = {
        "symbol": symbol,
        "leverage": leverage,
        "timestamp": int(time.time() * 1000)
    }
    # Sign and POST to /fapi/v1/leverage
```

3. ** ” ¾ ´   ‚ ¸  » ¾ ³ ƒ ²   ½ ½     ¾ ‚ ¾ ‡ ½ ¾ ³ ¾ leverage:**
```python
self.logger.info(f"[BinanceAdapter] Using leverage={leverage}x for {symbol}")
```

---

### ** ¡ µ   µ ´ ½ Œ ¾   ‚   ¾ º ¾ ² – (HIGH PRIORITY):**

4. ** œ ¾ ´ ¸ „ – º ƒ ²   ‚ ¸    ¾ ·     … ƒ ½ ¾ º qty  ·  ƒ     … ƒ ²   ½ ½  ¼ leverage:**
```python
#  £ decision_making.py
required_margin = position_size / leverage
if required_margin > available_margin:
    # Reduce position size
    position_size = available_margin * leverage * safety_factor
```

5. ** ” ¾ ´   ‚ ¸    ¾ ·     … ƒ ½ ¾ º  † – ½ ¸  » – º ² – ´   † – —:**
```python
liquidation_price = entry_price * (1 - (1 / leverage) * margin_ratio)
min_distance_to_liquidation_pct = 5.0  # 5% safety buffer

if abs(current_price - liquidation_price) / current_price < min_distance_to_liquidation_pct / 100:
    self.logger.error("Position too close to liquidation!")
    return None  # Reject trade
```

6. ** ” ¾ ´   ‚ ¸  ·   … ¸   ‚  ² – ´  ½   ´ ¼ –   ½ ¾ ³ ¾ leverage:**
```yaml
risk:
  max_leverage: 50
  min_liquidation_distance_pct: 5.0  # Minimum 5% from liquidation
  margin_buffer_pct: 10.0  # Keep 10% margin buffer
```

---

### ** ” ¾ ² ³ ¾   ‚   ¾ º ¾ ² – (MEDIUM PRIORITY):**

7. **   µ   » – · ƒ ²   ‚ ¸ margin tracker:**
-  œ ¾ ½ – ‚ ¾   ¸ ½ ³  ² ¸ º ¾   ¸   ‚   ½ ¾ —  ¼     ¶ –
-   » µ   ‚ ¸      ¸  ½   ± » ¸ ¶ µ ½ ½ –  ´ ¾ margin call
-   ² ‚ ¾ ¼   ‚ ¸ ‡ ½ µ  · ¼ µ ½ ˆ µ ½ ½     ¾ · ¸ † – ¹      ¸  º   ¸ ‚ ¸ ‡ ½ – ¹  ¼     ¶ –

8. ** ” ¾ ´   ‚ ¸    µ ¶ ¸ ¼ isolated margin:**
-  ” »   ·   … ¸   ‚ ƒ  ² – ´ cascade liquidation
-  ž º   µ ¼ ¸ ¹ margin pool  ´ »   º ¾ ¶ ½ ¾ —    ¾ · ¸ † – —

9. **Stress testing  · leverage:**
-  ¡ ¸ ¼ ƒ »  † –   µ º   ‚   µ ¼   » Œ ½ ¸ …    ƒ … – ²  † – ½ ¸
-    ¾ ·     … ƒ ½ ¾ º max drawdown  ·  ƒ     … ƒ ²   ½ ½  ¼ leverage
-  ¢ µ   ‚ ƒ ²   ½ ½   ½    –   ‚ ¾   ¸ ‡ ½ ¸ … flash crash'   …

---

## ðŸŽ“  ’ ¸   ½ ¾ ² ¾ º:

### ** Ÿ ¾ ‚ ¾ ‡ ½ ¸ ¹    ‚   ½:**
 ¡ ¸   ‚ µ ¼   **  •  º µ   ƒ ” leverage**,     » ¸ ˆ µ ** ‡ ¸ ‚   ”**  ¹ ¾ ³ ¾  ·  ± –   ¶ –.    ¾ ·     … ƒ ½ ¾ º    ¾ · ¸ † – ¹ **  •  ²     … ¾ ² ƒ ”** leverage,  ‰ ¾      ¸ · ² ¾ ´ ¸ ‚ Œ  ´ ¾:
-     ´ ¼ –   ½ ¾  º ¾ ½   µ   ²   ‚ ¸ ² ½ ¸ …    ¾ · ¸ † – ¹ ( ½ µ  ² ¸ º ¾   ¸   ‚ ¾ ² ƒ ” ‚ Œ       ¾ ‚ µ ½ † –   » leverage)
-  ’ – ´   ƒ ‚ ½ ¾   ‚ –  ·   … ¸   ‚ ƒ  ² – ´  » – º ² – ´   † – —
-   µ       ² ¸ » Œ ½ ¾ —  ¾ † – ½ º ¸    ¸ · ¸ º ƒ

### ** š   ¸ ‚ ¸ ‡ ½ –   ‚ Œ:**
ðŸ”´ ** ’ ˜ ¡ ž š ˜ ™    ˜ — ˜ š**  ´ »       ¾ ´   º ˆ ½ ƒ  ·    µ   » Œ ½ ¸ ¼ ¸  º ¾ ˆ ‚   ¼ ¸.  
ðŸŸ¡ ** ¡ •   • ”  † ™    ˜ — ˜ š**  ´ »  testnet (   » µ  ‚   µ ±    ² ¸       ² ¸ ‚ ¸    µ   µ ´    µ   µ … ¾ ´ ¾ ¼  ½   mainnet).

### **      ‚ ƒ   ½ –  º   ¾ º ¸:**
1.  ” ¾ ´   ‚ ¸   ² ½ ¸ ¹          ¼ µ ‚   `leverage`  ƒ  º ¾ ½ „ – ³ ƒ     † – Ž âœ…
2.    µ   » – · ƒ ²   ‚ ¸ API  ² ¸ º » ¸ º  ´ »   ²   ‚   ½ ¾ ² » µ ½ ½  leverage âœ…
3.  œ ¾ ´ ¸ „ – º ƒ ²   ‚ ¸ qty calculation  ·  ƒ     … ƒ ²   ½ ½  ¼ margin âœ…
4.  ” ¾ ´   ‚ ¸    ¾ ·     … ƒ ½ ¾ º  † – ½ ¸  » – º ² – ´   † – — âœ…

---

**  ² ‚ ¾    ´ ¾   » – ´ ¶ µ ½ ½ :** GitHub Copilot  
** Ÿ µ   µ ³ »  ½ ƒ ‚ ¾:** [ † ¼'     ¾ ·   ¾ ± ½ ¸ º  ]  
** ¡ ‚   ‚ ƒ  :** Draft v1.0  
