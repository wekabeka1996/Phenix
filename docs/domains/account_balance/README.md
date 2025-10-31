# Account Balance Domain (                                        )

##           

           `account_balance`                                                                         Aurora,                                                                                                                         Binance Futures.                                                                 API                                                          ,                                                                                         FSM           .

##                                  

###                                 
- **                                   :**                                                                                         Binance Futures API
- **                                     :**                                           '                                                                           
- **                                       :**                                     API                                                         FSM               
- **                    :**                                                                                                                                            

###                                             
                                                       ,                                                                    :
- **Risk Management**                                                    
- **Decision Making**                                                            
- **Position Tracking**                                                              
- **Execution Management**                                                                

##                                

```
account_balance/
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

### AccountConnector
                                      ,                                                   Binance API                                         .

**                                   :**
-                                     API                                                 (live/testnet/hybrid)
-                                                                                         
- Graceful degradation                              API
-                                         FSM           

## FSM           

###                                
- `EVT:BALANCE_UPDATE_RECEIVED` -                                                 
- `EVT:ACCOUNT_UPDATE_RECEIVED` -                                                                 

###                              
                                                                                               .

##                                       

###                        '        
- **Position Tracking**     `EVT:ACCOUNT_UPDATE_RECEIVED`
- **Risk Management**     `EVT:BALANCE_UPDATE_RECEIVED`, `EVT:ACCOUNT_UPDATE_RECEIVED`
- **Decision Making**     `EVT:BALANCE_UPDATE_RECEIVED`

###                                          
                                          ,                                                                                        .

##                         

###                                  
```yaml
trading_mode: "hybrid_live_data_testnet_exec"
binance_api:
  live:
    api_key: "${BINANCE_LIVE_API_KEY}"
    api_secret: "${BINANCE_LIVE_API_SECRET}"
  testnet:
    api_key: "${BINANCE_TESTNET_API_KEY}"
    api_secret: "${BINANCE_TESTNET_API_SECRET}"
account_balance:
  poll_interval: 30  #               
  retry_attempts: 3
  backoff_multiplier: 2.0
```

##                     

###               
- `account_balance.updates_success` -                                                     
- `account_balance.api_errors` -                                   API
- `account_balance.last_update_age` -                                    (              )

###                   
- INFO:                                                 /              
- WARN:                     API,                        USDT
- ERROR:                                   '              

##                                           

###                           
```python
from apps.reference.domains.account_balance import AccountConnector

connector = AccountConnector(config)
await connector.start()
```

###                                                 
```python
#            FSM                                            
balance_data = await connector.get_current_balance()
positions_data = await connector.get_current_positions()
```

##                     

###                                    
```bash
pytest tests/domains/account_balance/ -v
```

###                            
```bash
pytest tests/unit/domains/account_balance/ -v
```

##               

- API                                                                                              
- HTTPS                 API                 
-                                                         
-                                                                                

##                 

###                                             
1.                `dictionaries.yaml`                                                  
2.                                `AccountConnector`
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
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_balance\README.md