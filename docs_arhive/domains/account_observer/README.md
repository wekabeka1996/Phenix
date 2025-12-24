# Account Observer Domain (                                                  )

##           

           `account_observer`                                                             Aurora,                                                                                                            Binance Futures.                                 read-only API                                                                                                                                                                .

##                                  

###                                 
- **                                   :**                                                                                               Binance API
- **                        :**                                                                                                                     
- **                                       :**                                     API                                          FSM           
- **                    :**                                                                                                                               

###                                             
                                                   :
- **Position Tracking** -                                                                                            
- **Risk Management** -                                                                                     
- **Audit Trail** -                                                                             

##                                

```
account_observer/
          README.md              #                 -                        
          documentation.md       #                                           FSM                                   
          architecture.md        #                                                                     
          dictionaries.yaml      #                                                          
          functions.md           #                                                        
          examples/              #                                                        
                config.yaml        #                                          
                usage.py           #                                        
                tests/             #                                
          schema.json           # JSON Schema                                     
```

##                                    

### AccountObserver
                                      ,                                                                      Binance API.

**                                   :**
-                                     API                                                 (live/testnet/hybrid)
-                                                                                         
-                                              ID                                               
-                                         FSM                                                    

## FSM           

###                                
- `EVT:TRADE_EXECUTED` -                                                                                                

###                              
                                                                                               .

##                                       

###                        '        
- **Position Tracking**     `EVT:TRADE_EXECUTED`
- **Risk Management**     `EVT:TRADE_EXECUTED`
- **Audit Trail**     `EVT:TRADE_EXECUTED`

###                                          
                                          ,                                                                                   ,                                           .

##                         

###                                  
```yaml
#                                                         
trading_mode: "testnet"

# API                         
binance_api:
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"

#                                       account_observer
account_observer:
  poll_interval: 5        #                                               
  symbols:                #                                             
    - BTCUSDT
    - ETHUSDT
    - BNBUSDT
  trade_limit: 50         #                                                  
```
  trade_limit: 50        #                                                            
```

##                     

###               
- `account_observer.trades_processed` -                                                       
- `account_observer.new_trades_detected` -                                             
- `account_observer.api_errors` -                                   API
- `account_observer.poll_interval_actual` -                                                         

###                   
- INFO:                                             ,                        
- DEBUG:                                                                
- ERROR:                                 API                        

##                                           

###                           
```python
from apps.reference.domains.account_observer import AccountObserver

observer = AccountObserver(fsm, config)
observer.start()
```

###                                          
```python
#                                           ,                                                       
# EVT:TRADE_EXECUTED                                                                           
```

##                     

###                                    
```bash
pytest tests/domains/account_observer/ -v
```

###                            
```bash
pytest tests/unit/domains/account_observer/ -v
```

##               

### Read-only             
-                                       read-only API             
-                                                                              
-                                                                                 

###           
-                                                                            
-                                                              
-                                                           

##                 

###                                             
1.                `dictionaries.yaml`                                                  
2.                                `AccountObserver`
3.                `schema.json`                             
4.                            
5.                                        

###                       
-                                                                              
-                                                               
-                                                                

##                            

- [                                         ](documentation.md) - FSM                                   
- [                                   ](architecture.md) -                                                  
- [                           ](dictionaries.yaml) -                              
- [                                     ](functions.md) - API                  </content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_observer\README.md