#            Account Observer (                                     )

##                                      

**                                       :** `account_observer`  
**                          :**                                                                                                  

##                                  

           `account_observer`                                                                                                                              .                                          API                                                                                                                                                                                         FSM               .

###                                 
-                                                           read-only API
-                        ID                                                              
-                                                                                                       
-                                                                                                                             

##                                

###                                    

#### AccountObserver
                                      ,                                                          .

**                          :**
-                          Binance Client                   `trading_mode`
-            API                                                             
-                                                                                     
-                                                                 

**                                          :**
- `start()` -                                                   
- `stop()` -                                      

###                                          

####                              
```
_poll_loop() -> _poll_trades()
                                                                                            
                                                                 (get_my_trades)
                                                            
                                      EVT:TRADE_EXECUTED
```

####                                            
-                                             trade_id    Set
-                                                          
-                                                                      

## FSM           

###                                

#### EVT:TRADE_EXECUTED
**              :**                                                     (                            5                                  )  
**                      :** Position Tracking, Risk Management, Audit Trail  

**Payload                   :**
```json
{
  "symbol": "BTCUSDT",
  "side": "buy",
  "price": "50000.00",
  "quantity": "0.001",
  "ts": 1640995200000,
  "fees": "0.0001",
  "venue": "binance"
}
```

**        :**                                                                                                           .

###                              
                                                             -                                .

##                                                    

###                        '        

#### Position Tracking
- **        :** EVT:TRADE_EXECUTED
- **                        :**                                                                                               
- **              :**                (                                )

#### Risk Management
- **        :** EVT:TRADE_EXECUTED
- **                        :**                                                                                     
- **              :**                (                                )

#### Audit Trail
- **        :** EVT:TRADE_EXECUTED
- **                        :**                                                 
- **              :**                (                              )

###                                          
                                          ,                                                                                                            .

##                         

###                                  
```yaml
trading_mode: "hybrid_live_data_testnet_exec"

binance_api:
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"

account_observer:
  poll_interval: 5          #                                                          
  symbols:                  #                                                            
    - BTCUSDT
    - ETHUSDT
    - BNBUSDT
  trade_limit: 50          #                                                                             
```

###                          
- **live:**                                                   
- **testnet:**                                                     
- **hybrid:**                                                                                   

##                                                 

###                   
- **                                                 :**                                             ,                        
- **Debug                         :**                                                                
- **              :**                     API,                                

###               
-                                                       
-                                                            
-                                                        

##                              

###                                          
1. **API               :**                                                                        
2. **                                 :**                                                                     
3. **                             :**                                                                           

### Graceful degradation
                                                                                                                                       .

##                     

###                                    
-                                                                                                  
-                                                             
-                                                                 

###                            
-                                                    Binance
-                                   payload
-                                                           

##               

### Read-only             
-                                       read-only API             
-                                                                              
-                                                                  

###           
                                                                                 debugging.