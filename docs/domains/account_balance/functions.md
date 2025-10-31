#                                                    Account Balance

##           

           `account_balance`                           `AccountConnector`                                                                                          Binance Futures.                                                                                                                                                                                         .

##                          : AccountConnector

###                                                       

#### `__init__(fsm: FSMCore, config: Dict[str, Any]) -> None`
**        :**                          '                  Binance API            BinanceAdapter.

**                  :**
- `fsm`:                    FSM core                               
- `config`:                                                  API credentials                                  

**                                       :**
1.                                            FSM                              
2.                                                               `account_observer.poll_interval`
3.            API                                                `trading_mode`:
   - `live`:                                         API             
   - `testnet`/`hybrid`:                                           API             
4.                                                                     API                     
5.                                         `BinanceAdapter`

**              :** `ValueError`                         API                         

###                                                   

#### `start() -> None`
**        :**                                                                                      .

**            :**
1.                   ,                             
2.                                         `running = True`
3.                    daemon                                `_monitor_loop`
4.                          
5.                                                     

#### `stop() -> None`
**        :**                                                             '              .

**            :**
1.                          `running = False`
2.                                                        (thread.join())
3.                  HTTP                            
4.                                  

###                                                 

#### `_monitor_loop() -> None`
**        :**                                                 ,                                                   .

**            :**
1.                                 event loop                                               
2.                   `running == True`:
   -              `_fetch_and_emit_account_data()`
   -                      `update_interval`             
3.                  event loop                            

**                             :**                                                   

###                                                  

#### `_fetch_and_emit_account_data() -> None`
**        :**                                                 Binance API                   FSM           .

**                                  :**
1.              `adapter.get_account_balance()`
2.                                                (                list)
3.                                    `_latest_balance_data`
4.                                     USDT               
5.              `_emit_balance_update()`

**                                  :**
1.              `adapter.get_open_positions()`
2.                                                (                list)
3.              `_emit_positions_update()`

**                             :**                                                                                                                 

###              FSM           

#### `_emit_balance_update(balance_data: List[Dict[str, Any]]) -> None`
**        :**                         `EVT:BALANCE_UPDATE_RECEIVED`                               .

**                                     :**
1.                                        `balance > 0`
2.                                                           `Decimal`                        
3.                                 assets                :
   - `asset`:                        
   - `balance`:                                
   - `crossUnPnl`:                              P&L
   - `crossWalletBalance`:              cross margin
   - `updateTime`:                          

**Payload                   :**
```python
{
    'assets': [...],  #                            
    'updateTime': int  #                          updateTime                  
}
```

**                       :**
- Event name: `"EVT:BALANCE_UPDATE_RECEIVED"`
- Why: `"Balance data updated from Binance API."`
-                                                                          > 0

#### `_emit_positions_update(positions_data: List[Dict[str, Any]]) -> None`
**        :**                         `EVT:ACCOUNT_UPDATE_RECEIVED`                                                                    .

**                                         :**
1.                                        `positionAmt != 0`
2.                           Decimal                        
3.                                                                                  :
   - `symbol`:                        
   - `positionAmt`:                            
   - `entryPrice`:                    
   - `unRealizedProfit`:                                              
   - `leverage`:           
   - `marginType`:                  
   - `markPrice`:                            
   - `liquidationPrice`:                              

**                                                    :**
1.                          `_latest_balance_data`        USDT             
2.                    `totalWalletBalance`             `balance`
3.                    `totalUnrealizedProfit`             `crossUnPnl`
4.                    `totalCrossWalletBalance`                                     

**Payload                   :**
```python
{
    'totalWalletBalance': str,
    'totalUnrealizedProfit': str,
    'totalCrossWalletBalance': str,
    'positions': [...],  #                                               
    'updateTime': int    #                  timestamp    ms
}
```

**                       :**
- Event name: `"EVT:ACCOUNT_UPDATE_RECEIVED"`
- Why: `"Open positions data updated from Binance API."`
-                                                                              wallet balance

##                                               

###                                              
- `fsm`:                         FSM core
- `config`:                                              
- `update_interval`:                                                           (                                30)

###                            
- `thread`:                                             
- `running`:                                                         
- `adapter`:                    BinanceAdapter

###                          
- `_latest_balance_data`:                                           API `/fapi/v2/balance`

##                                                                     

### vfoundation.adapters.binance_adapter.BinanceAdapter
**            :**
- `get_account_balance()`:                                                 
- `get_open_positions()`:                                                     
- `close_session()`:                  HTTP           

### vfoundation.core.FSMCore
**            :**
- `emit(event_name, payload, why)`:              FSM           

##                              

###                   
1. **API               :**                       `exc_info=True`                             traceback
2. **                           :**                                                                                        
3. **                                 :** Graceful degradation                                                    

###                   
- **INFO:**                                ,                              
- **WARNING:**                        USDT,                                 
- **ERROR:**                                                 traceback

##                             

###                       
- **                    :**                                               > 0                        amount != 0
- **                  :**                                                                                        
- **                          :**                      API               
- **Background execution:**                                                                          

###                                        
- **CPU:**                                               (                                  API               )
- **Memory:**                                                                                        
- **Network:** 2 API                           30             
- **Storage:**                                                              

##                     

###                            
- **                          :**                                                                                     
- **API         :**                                         Binance API
- **                          :**                                                                   
- **            :**                                       payload           

###                                    
- **FSM                     :**                                                                     
- **API                     :**                                            credentials (testnet)
- **Error handling:**                                                           API failures

##               

###                                           
- API                                                                                 
-                                                             
-                          HTTPS            BinanceAdapter

###           
-        API                                          sensitive data
-                                                                          
- Timestamp                                              

##                                                      

###                                  
1. **WebSocket                   :**                   REST      real-time updates
2. **Multi-asset                   :**                                                         
3. **Historical data:**                                                   
4. **Alerting:**                                                                           

###                                                  
-                                                         /              
-   astom                                            
-                                                         
-                                                                         </content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\domains\account_balance\functions.md