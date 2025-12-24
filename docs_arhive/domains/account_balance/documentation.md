#            Account Balance (                           )

##                                      

**                                       :** `account_balance`  
**            :** FSMP-P1-T04  
**                          :**                                                                             

##                                  

           `account_balance`                                                                         Aurora,                                                                                                                   .                                                                 API                                                          ,                                                                                         FSM           .

###                                 
-                                                                     Binance Futures API
-                                                       
-                                     API                                                         FSM
-                                                                                                                           

##                                

###                                    

#### AccountConnector
                                      ,                                                   Binance API.

**                          :**
-                          BinanceAdapter                   `trading_mode`
-            API              (live/testnet)                                                
-                                                                  (                                30             )

**                                          :**
- `start()` -                                                     
- `stop()` -                                                               '            

###                                          

####                                      
```
_monitor_loop() -> _fetch_and_emit_account_data()
                                                (/fapi/v2/balance)
                                                (/fapi/v2/positionRisk)
                                      FSM
                                                                          
```

####                          
1. **                           :**                                                                             
2. **              :**                                                        (positionAmt != 0)
3. **                        :**                           Decimal                                           

## FSM           

###                                

#### EVT:BALANCE_UPDATE_RECEIVED
**              :**            30              (                                      )  
**                      :** Decision Making, Risk Management, Position Tracking  

**Payload                   :**
```json
{
  "assets": [
    {
      "asset": "USDT",
      "balance": "1000.50",
      "crossUnPnl": "25.30",
      "crossWalletBalance": "975.20",
      "updateTime": 1640995200000
    }
  ],
  "updateTime": 1640995200000
}
```

**        :**                                                                                                                      .

#### EVT:ACCOUNT_UPDATE_RECEIVED
**              :**            30              (                                      )  
**                      :** Position Tracking, Risk Management, Decision Making  

**Payload                   :**
```json
{
  "totalWalletBalance": "1000.50",
  "totalUnrealizedProfit": "25.30",
  "totalCrossWalletBalance": "975.20",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "positionAmt": "0.001",
      "entryPrice": "50000.00",
      "unRealizedProfit": "5.25",
      "leverage": 10,
      "marginType": "cross",
      "markPrice": "50250.00",
      "liquidationPrice": "45000.00"
    }
  ],
  "updateTime": 1640995200000
}
```

**        :**                                                                                                                                  .

###                              
                                                             -                                .

##                                                    

###                        '        

#### Position Tracking
- **        :** EVT:ACCOUNT_UPDATE_RECEIVED
- **                        :**                                                                      
- **              :**                             (30       )

#### Risk Management
- **        :** EVT:BALANCE_UPDATE_RECEIVED, EVT:ACCOUNT_UPDATE_RECEIVED
- **                        :**                                                     ,                                  
- **              :**                             (30       )

#### Decision Making
- **        :** EVT:BALANCE_UPDATE_RECEIVED
- **                        :**                                                                                    
- **              :**                             (30       )

###                                          
                                                                                   ,                                                                                 .

##                         

###                                  
```yaml
trading_mode: "hybrid_live_data_testnet_exec"  #                                API             

binance_api:
  live:
    api_key: "${BINANCE_LIVE_API_KEY}"
    api_secret: "${BINANCE_LIVE_API_SECRET}"
    rest_url: "https://fapi.binance.com"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
    rest_url: "https://testnet.binancefuture.com"

account_observer:
  poll_interval: 30  #                                                          
```

###                          
- **live:**                                         API              Binance
- **testnet:**                                           API             
- **hybrid_live_data_testnet_exec:**                                                                       

##                                                 

###                   
- **                                                 :**                                             ,                                  /              
- **                        :**                        USDT                  ,                     API
- **              :**                  '                  API,                                             

###               
-                                                                
-                                                                
-                                      API                                                  

##                              

###                                          
1. **API               :**                                                                   backoff
2. **                           :**                                                                             
3. **                                 :**                                                                                        

### Graceful degradation
                                                                 API                                                                                                       ,                                .

##                     

###                                    
-                                                                      API               FSM           
-                                                                (live/testnet/hybrid)
-                                                    API

###                            
-                                                                  
-                                                       
-                                              FSM

##               

###                                           
- API                                                                                              
-                                                             
-                          HTTPS                 API                 

###           
                                                                                        debugging.