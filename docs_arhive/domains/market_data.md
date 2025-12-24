#            Market Data (                       )

##                                      

**                                       :** `market_data`  
**            :** FSMP-P1-T03  
**                          :**                                                                                                      

##                                  

           `market_data`                                                                                Aurora.                                                                                                  REST API Binance,                                   Kline                                                                                                 .

###                                 
-                    1-                   Kline               Binance Futures
-                                                                                                                    
-                                              (live/testnet)                                           
-                                                                                               

##                                

###                                    

#### MarketDataConnector
                                      ,                                                                                         .

**                          :**
-                          BinanceAdapter                                                  
-            API                                                             domain_configuration
-                                                                                                    

**                                          :**
- `start()` -                                                   
- `stop()` -                                        '            

###                                          

####                                       
```
_poll_loop() -> _fetch_and_emit_data()
                                                                                            
                                                  1m Kline           
                                          MARKET_TICK_RECEIVED           
                                                                          
```

####                Kline           
1. **              :**                           Kline                                       
2. **                        :**                             Decimal                        
3. **                             :**                    bid/ask    close price                            

## FSM           

###                                

#### EVT:MARKET_TICK_RECEIVED
**              :**            5                                (                               )  
**                      :** Feature Engineering, Decision Making, Risk Management  

**Payload                   :**
```json
{
  "ts": 1640995200000,
  "symbol": "BTCUSDT",
  "price": "50000.00",
  "bid": "50000.00",
  "ask": "50000.00",
  "mid": "50000.00",
  "bid_size": "1",
  "ask_size": "1",
  "buy_volume": "100.5",
  "sell_volume": "95.3",
  "data_type": "kline_1m",
  "data_source": "live"
}
```

**        :**                                                                                                                             .

###                              
                                                             -                                .

##                                                    

###                        '        

#### Feature Engineering
- **        :** EVT:MARKET_TICK_RECEIVED
- **                        :**                                                                (OBI, TFI, delta_price)
- **              :**                             (5                         )

> **Note:** Risk Management та Decision Making НЕ споживають EVT:MARKET_TICK_RECEIVED напряму.
> Вони працюють з EVT:FEATURES_CALCULATED, який генерує Feature Engineering.

###                                          
                                                                                                                      .

##                         

###                                  
```yaml
trading_mode: "hybrid_live_data_testnet_exec"

domain_configuration:
  market_data:
    trading_mode: "live"  #              live                                                      

binance_api:
  live:
    api_key: "${BINANCE_LIVE_API_KEY}"
    api_secret: "${BINANCE_LIVE_API_SECRET}"
    rest_url: "https://fapi.binance.com"

system:
  trading:
    symbols_to_track:
      - BTCUSDT
      - ETHUSDT
    market_data:
      poll_interval_sec: 5
```

###                          
- **live:**                                                              
- **testnet:**                                                                
- **hybrid:**                  live                      , testnet                          

##                                                 

###                   
- **                                                 :**             /                                 ,                                     
- **                        :**                                                        
- **              :**                     API,                              

###               
-                                                                
-                                                                                
-                                                                     

##                              

###                                          
1. **API               :**                                                                        
2. **                           :**                                                             Kline
3. **                                 :**                                                                     

### Graceful degradation
                                                                                                                         .

##                     

###                                    
-                                                                      Kline              
-                                                                (live/testnet)
-                                                                           

###                            
-                                     Kline               
-                                                       
-                                                              

##               

### Read-only             
-                          API                                                            
-                                                                           
-                                                                 

###                                  
                                 `data_source`                                                                     .