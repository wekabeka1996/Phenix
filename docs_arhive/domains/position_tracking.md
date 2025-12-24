#            Position Tracking (                                     )

##                                      

**                                       :** `position_tracking`  
**                          :**                                                                  P&L

##                                  

           `position_tracking`                                                                                                             Aurora.                                                                      ,                                                ,                          realized/unrealized P&L                                                           equity.

###                                 
-                                                                                        
-                      realized      unrealized P&L
-                                      equity                 
- WAL                             disaster recovery
-                                                          

##                                

###                                    

#### PositionTracking
                                      ,                                                    .

**                          :**
-                                                                                     
-                                                                                   P&L
-                          WAL                     

**                                          :**
- `start()` -                                  
- `on_trade_executed()` -                                                 
- `on_account_update()` -                                               

###                                          

####                                        
```
_positions: Dict[str, Dict[str, Any]]
              symbol -> position data
              avg_price:                                   
              quantity:                                  
              realized_pnl:                        P&L
              venue:                              
```

#### WAL                     
```
on_trade_executed() -> WAL write first
                                       WAL                            
                                                     WAL failure
                                                  disaster recovery
```

## FSM           

###                                

#### EVT:PORTFOLIO_STATE_UPDATED
**              :**                           EVT:TRADE_EXECUTED  
**                      :** Decision Making, Risk Management, Audit Trail  

**Payload                   :**
```json
{
  "ts": 1640995200000,
  "equity": "1000.50",
  "realized_pnl": "25.30",
  "unrealized_pnl": "-5.20",
  "positions": [
    {
      "symbol": "BTCUSDT",
      "quantity": "0.001",
      "avg_price": "50000.00",
      "current_price": "50250.00",
      "unrealized_pnl": "2.50",
      "realized_pnl": "0.00"
    }
  ]
}
```

**        :**                                                                                             .

###                              

#### EVT:TRADE_EXECUTED
**              :** Account Observer  
**                        :**                                                                                                              
**              :**                                                

#### EVT:ACCOUNT_UPDATE_RECEIVED
**              :** Account Balance  
**                        :**                                                                    
**              :**                             (30       )

#### EVT:BALANCE_UPDATE_RECEIVED
**              :** Account Balance  
**                        :**                                                                   
**              :**                             (30       )

##                                                    

###                        '        

#### Account Observer
- **        :** EVT:TRADE_EXECUTED
- **                        :**                                                                           
- **              :**               

#### Account Balance
- **        :** EVT:ACCOUNT_UPDATE_RECEIVED, EVT:BALANCE_UPDATE_RECEIVED
- **                        :**                                                              
- **              :**                            

#### Decision Making
- **          :** EVT:PORTFOLIO_STATE_UPDATED
- **                        :**                 equity        sizing             
- **              :**                                       

#### Risk Management
- **          :** EVT:PORTFOLIO_STATE_UPDATED
- **                        :**                                                     
- **              :**                                       

###                                          
                                                 ,                                                             .

##                      P&L

### Realized P&L
```
realized_pnl += (exit_price - entry_price)    quantity - fees
```
**            :**                                                                                    .

### Unrealized P&L
```
unrealized_pnl =   (current_price - avg_entry_price)    quantity
```
**            :**                                                                      .

### Equity
```
equity = wallet_balance + unrealized_pnl
```
**              :**                             +                              P&L.

## WAL      Disaster Recovery

### WAL-first             
```python
# Write to WAL BEFORE processing
wal_hash = wal.append(event_dict)
if wal_hash is None:
    # CRITICAL: Halt processing
    return
```

**        :**                  durability            state mutation.

### State Persistence
-                                                            WAL
-                                                                             
-                                                                        

##                         

###                                  
```yaml
system:
  trading:
    instruments:
      BTCUSDT:
        step_size: "0.001"
      ETHUSDT:
        step_size: "0.01"
```

###                          
- **live:**                                                     
- **testnet:**                                                       

##                                                 

###               
-                                                     
- Total realized/unrealized P&L
- Equity changes over time
- WAL write success rate

###                   
- **                        :**                                    ,                      P&L
- **                        :**                                                                
- **                :** WAL write failures

##                              

###                                          
1. **WAL failure:**                                               
2. **Invalid data:**                                                                           
3. **State inconsistency:**                                                                                        

### Data Validation
-                                                                     
-                    quantity      side
-                                                     

##                     

###                                    
-                                           P&L
-                    WAL                     
-                                                       

###                            
-                                                                  
-                    P&L                       
-                      error handling

##                                                

### Single Source of Truth
Position Tracking                                                     :
-                                               
-                      P&L           
- Equity                       

### WAL-first Design
                                            WAL                            ,                          :
- Atomicity                 
- Durability                
- Consistency                              