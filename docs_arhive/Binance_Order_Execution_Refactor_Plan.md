#                                                                                    Binance

**            :** 1.0
**        :** 2025-10-26
**          :** Gemini AI Agent

## 1.                                         

**        :**                            `BinanceExecutionAdapter`                                                             ,                                                  Binance Futures API,                                                                                                                                                                                      ,                                                                                            .

**                          :**                                                                         ,                                              :
1.                                      `LIMIT`      `MARKET`             .
2.                                                                                                               .
3.                                                                                   ,                                                                                .
4.                                                                                    Binance API (        .,                        `newOrderRespType`).

                                                              ,                                        ,                                                                    .

## 2.                                       (                      )

1.  **                    `async/await`:**                                             `BinanceExecutionAdapter`                                                                                                                             `httpx`.                                                                                                                                                   .
2.  **                                              :**                                                                                                                            `trading.yaml`.                                                                                                                         .
3.  **                                                                          :**                                                           `_build_order_params`,                                                                                               API-                                                                                         `TradeIntent`.
4.  **                                                              :**                                                                                                             ,                                       `newOrderRespType='RESULT'`                                                          .

## 3.                               (                    )

###          1:                                                                        

1.  **                                 :**              `httpx`             `requirements.txt`.

2.  **                                       :**             `config/aurora/trading.yaml`                                                                                    .

    ```yaml
    # In config/aurora/trading.yaml
    
    execution:
      # Default order type for opening positions.
      # Valid types: LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET
      order_type: "MARKET" 
    
      # Default timeInForce for LIMIT orders
      time_in_force: "GTC"
    ```

###          2:                        `BinanceExecutionAdapter`      `async/await`

                                        : `apps/reference/domains/execution_position/binance_execution_adapter.py`

1.  **                       `httpx`:**
    ```python
    import httpx
    ```

2.  **                       `_place_binance_order`                                       :**

    *   **                              (                    ):**
        ```python
        def _place_binance_order(self, symbol, side, qty, order_type, price=None, time_in_force=None, reduce_only=False, new_client_order_id=None):
            # ... uses requests.post ...
        ```

    *   **                        (                      ):**
        ```python
        async def _place_binance_order(self, symbol: str, side: str, qty: str, order_type: str, price: Optional[str] = None, time_in_force: Optional[str] = None, reduce_only: bool = False, new_client_order_id: Optional[str] = None, stop_price: Optional[str] = None, close_position: bool = False):
            #                                                                             
            params = self._build_order_params(...)

            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url + "/fapi/v1/order", params=params, headers={'X-MBX-APIKEY': self.api_key})
                # ...                                   ...
        ```
    **                                       :** `async def`                                                      . `await client.post`                                                                  ,                                          ,                                                                                 .

3.  **               `place_order`,                      `async`                                            `_place_binance_order`:**

    ```python
    async def place_order(self, msg: Message) -> dict:
        # ... (                                msg) ...
        
        #                                                   
        result = await self._place_binance_order(...)
        
        # ... (                                   ) ...
        return feedback
    ```

###          3:                                                                                                    

                                                         `BinanceExecutionAdapter`.

```python
def _build_order_params(self, pld: dict) -> dict:
    """Builds the API parameters dictionary based on the order type from config and payload."""
    
    order_type = self.config.get('trading', {}).get('execution', {}).get('order_type', 'MARKET').upper()
    
    params = {
        "symbol": self._adapt_symbol(pld['symbol']),
        "side": self._adapt_side(pld['side']),
        "type": order_type,
        "newOrderRespType": "RESULT"  #                                                               
    }

    #                                                      (                                     )
    # (                      ,      `self.exchange_info`                                                 )
    qty = self._validate_quantity(pld['symbol'], pld['qty'])
    
    if order_type == 'MARKET':
        params['quantity'] = qty
    
    elif order_type == 'LIMIT':
        params['quantity'] = qty
        params['price'] = self._validate_price(pld['symbol'], pld['price'])
        params['timeInForce'] = self.config.get('trading', {}).get('execution', {}).get('time_in_force', 'GTC')

    elif order_type == 'STOP_MARKET':
        params['stopPrice'] = pld['stop_price'] #                                        TradeIntent
        params['workingType'] = pld.get('working_type', 'CONTRACT_PRICE')
        if pld.get('close_position'):
            params['closePosition'] = 'true'
        else:
            params['quantity'] = qty

    # ...                                                                      :
    # STOP, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
    # ...

    if pld.get('reduce_only') and not pld.get('close_position'):
        params['reduceOnly'] = 'true'

    if pld.get('idempotent_key'):
        params['newClientOrderId'] = pld['idempotent_key']

    return params
```

###          4:                    `DecisionMaking`

        : `apps/reference/domains/decision_making/decision_making.py`

                                                     `TradeIntent`,                                                           (                  , `stop_price`).

```python
#                 _propose_trade_intent
trade_intent = {
    # ...                         ...
    "order": {
        "qty": str(qty),
        "price": str(price),
        "price_ref": str(price),
        "reduce_only": False,
        "stop_price": "0" #                                             
    },
    # ...                         ...
}
```

## 4.                              

                                  : `tests/domains/test_binance_execution_adapter.py`

1.  **                                        :**                  ,                           `place_order`,                                                                     .
    ```python
    import pytest
    
    @pytest.mark.asyncio
    async def test_place_order_shadow_mode_success(self, adapter_shadow):
        # ... (                       ) ...
        result = await adapter_shadow.place_order(dec_msg)
        # ... (                  ) ...
    ```

2.  **                                                                                                    :**                                                           `_build_order_params`                                            .

    ```python
    @pytest.mark.parametrize("order_type, pld_extras, expected_params", [
        ("MARKET", {}, ["symbol", "side", "type", "quantity"]),
        ("LIMIT", {"price": "50000"}, ["symbol", "side", "type", "quantity", "price", "timeInForce"]),
        ("STOP_MARKET", {"stop_price": "49000", "close_position": True}, ["symbol", "side", "type", "stopPrice", "closePosition"]),
        # ...                                                                              ...
    ])
    @pytest.mark.asyncio
    async def test_order_param_builder(self, order_type, pld_extras, expected_params, adapter_live):
        # 1.                                             
        adapter_live.config['trading']['execution']['order_type'] = order_type
        
        # 2.                  pld
        pld = {"symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", **pld_extras}
        
        # 3.                    _build_order_params
        params = adapter_live._build_order_params(pld)
        
        # 4.                     ,                                                                   
        for key in expected_params:
            assert key in params
            
        # 5.                                                          (        ., closePosition    quantity)
        if "closePosition" in params:
            assert "quantity" not in params
    ```

## 5.                                                         

1.  `BinanceExecutionAdapter`                                                                                           .
2.                                                           -                            ,                            Binance Futures,                                                         (`order_type`)               `trading.yaml`.
3.                                                                           `newOrderRespType='RESULT'`,                                           .
4.                                                                -                                                 ,                                                                                                       .

## 6.                                              

-   **          :**                                        `async/await`.                          `place_order`      `async`                                                            ,                                    (                  ,    `main.py`).
    -   **                      :**                                                                                   .                , `place_order`                             `on_trade_intent_proposed`,                                                                                                                                                                                       .

-   **          :**                                                                                                            (        ., `TRAILING_STOP_MARKET`).
    -   **                      :**                                                          `TASK.md`.                                ,                                                                                                                                          .

-   **          :**                                                  `httpx`                                 '                  .
    -   **                      :**                                `httpx.AsyncClient`    `async with`           ,                                                                            '            .                                                                                                     .
