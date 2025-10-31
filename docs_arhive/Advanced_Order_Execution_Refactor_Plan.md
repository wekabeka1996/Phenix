#                              :                                                                        

**            :** 2.0
**        :** 2025-10-26
**          :** Gemini AI Agent
**            :**                           

## 1.                                         

**        :**                                                          `BinanceExecutionAdapter`            '                                                                                     :
1.  **                                                       :**                                                                        -                                ,                       `TASK.md`,                                    .
2.  **                                              :**                                                            -                                                                                  `async/await`                               `httpx`.
3.  **                                                                :**                                                             ,                                             `newOrderRespType='RESULT'`                                                              .

**                          :**                                                                                                                  ,                                                                    ,                                                                                                            ,                                         LLA.

## 2.                                           

-   **               (`BinanceExecutionAdapter`):**                                                                  `requests`,                                            API-              .
-   **FSM (`OpenFlowFSM`, `CloseFlowFSM`):**              `handle`                           (`def`).                                                                                       .
-   **                                            :**                                            `LIMIT`      `MARKET`           .
-   **                        :**                                                                                                                                  (        ., `timeInForce`).

## 3.                                                                  

1.  **                                     :** `BinanceExecutionAdapter`                                                                                `async def`                               ,                                                      .                      `requests`                                `httpx`.
2.  **                     FSM:**              `handle`    `OpenFlowFSM`, `ManageFlowFSM`      `CloseFlowFSM`,                                                               ,                                          `async def`.
3.  **                                                :**                                          (   `apps/reference/main.py`),                                                                          `fsm.handle()`,                                                                                 FSM (                              `await`).
4.  **                            `trading.yaml`:**                                          `execution`                                                                    ,                                                                                     .
5.  **                                                                          :**                                                          `_build_order_params`,                                                                                     Binance API                                                               `TradeIntent`.

## 4.                                                   

###          1:                                                                        

1.  **             `httpx`:**             `requirements.txt`                        :
    ```
    httpx
    ```
2.  **                   `trading.yaml`:**                `config/aurora/trading.yaml`,                                                      `execution`.

    ```yaml
    # In config/aurora/trading.yaml
    execution:
      #                                                             .
      #                                    : MARKET, LIMIT, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
      open_order_type: "MARKET"

      #                                                               
      order_params:
        LIMIT:
          timeInForce: "GTC" # Good-Till-Cancel
        STOP_MARKET:
          workingType: "MARK_PRICE"
        TAKE_PROFIT_MARKET:
          workingType: "MARK_PRICE"
        TRAILING_STOP_MARKET:
          callbackRate: "0.5" # 0.5%
    ```

###          2:                        `BinanceExecutionAdapter`

**        :** `apps/reference/domains/execution_position/binance_execution_adapter.py`

1.  **                              `requests`      `httpx`**.

2.  **                                                        `async def`:**

    ```python
    #                        
    async def place_order(self, msg: Message) -> dict:
        # ...
        params = self._build_order_params(pld)
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.base_url}/fapi/v1/order", params=params, headers=self.headers)
            # ...
    
    async def cancel_order(self, msg: Message) -> dict:
        # ...
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{self.base_url}/fapi/v1/order", params=params, headers=self.headers)
            # ...

    #                                   _set_leverage, _set_margin_type, _get_listen_key      .  .
    ```
    **                                       :** `async with httpx.AsyncClient()`                                                                                                                       . `await client.post`                                                                                .

3.  **                       `_build_order_params`:**

    ```python
    def _build_order_params(self, pld: dict) -> dict:
        order_type = self.config.get('trading', {}).get('execution', {}).get('open_order_type', 'MARKET').upper()
        
        params = {
            "symbol": self._adapt_symbol(pld['symbol']),
            "side": self._adapt_side(pld['side']),
            "type": order_type,
            "newOrderRespType": "RESULT"
        }

        # ... (                                                            TASK.md) ...
        #                       LIMIT
        if order_type == 'LIMIT':
            params['quantity'] = pld['qty']
            params['price'] = pld['price']
            params['timeInForce'] = self.config.get('trading', {}).get('execution', {}).get('order_params', {}).get('LIMIT', {}).get('timeInForce', 'GTC')

        #                       STOP_MARKET    closePosition
        elif order_type == 'STOP_MARKET' and pld.get('close_position'):
            params['stopPrice'] = pld['stop_price']
            params['closePosition'] = 'true'
        
        # ...                                               ...

        return params
    ```

###          3:                    FSM                                

**          :** `apps/reference/domains/execution_position/fsm_open.py`, `fsm_close.py`

            ,                                         ,                       `async def`                                   `await`.

```python
#    apps/reference/domains/execution_position/fsm_open.py
class OpenFlowFSM:
    # ...
    async def _execute_open_order(self, msg: Message) -> Optional[Message]:
        # ...
        feedback = await self.adapter.place_order(open_cmd)
        # ...
```

###          4:                                

**        :** `tests/domains/test_binance_execution_adapter.py`

1.  **             `pytest-asyncio`:**                         ,                                     .
2.  **                         :**                                     ,                                                            ,      `@pytest.mark.asyncio`                                   `await`.

    ```python
    import pytest

    @pytest.mark.asyncio
    async def test_place_order_live_mode_success(self, adapter_live):
        msg = Message(...)
        with patch.object(adapter_live, '_place_binance_order', new_callable=mock.AsyncMock) as mock_place:
            mock_place.return_value = {"orderId": "12345", "status": "FILLED"}
            await adapter_live.place_order(msg)
            mock_place.assert_awaited_once_with(...)
    ```
    **                :**                                                                                                                 `mock.AsyncMock`.

3.  **                                                      **        `_build_order_params`,                                                                    ,                                                     .

## 5.                              

1.                                                    `tests/domains/test_binance_execution_adapter.py`                                  .
2.                                                                  `MARKET`                                             Binance (                                                                                             ).
3.             `open_order_type`    `trading.yaml`      `LIMIT`                                                               `LIMIT`             .
4.                                                        (linting)                          .

## 6.             

-   **                                         :**                     `async`                                                                                             .
    -   **                      :**                                                             ,                                                      .                            ,                                                                                `execution_position`.
-   **                                         :**                                                                             .
    -   **                      :**                                                                            (`pytest-asyncio`, `mock.AsyncMock`)                                                                  .

                                                                                                                .
