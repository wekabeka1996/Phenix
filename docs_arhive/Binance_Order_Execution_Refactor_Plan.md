# План Рефакторингу Си� теми Виконання Ордерів Binance

**Вер� ія:** 1.0
**Дата:** 2025-10-26
**Автор:** Gemini AI Agent

## 1. Мета та Обґрунтування

**Мета:** Модернізувати `BinanceExecutionAdapter` для підтримки в� іх типів ордерів, зазначених у документації Binance Futures API, зробити його повні� тю конфігурованим та приве� ти у відповідні� ть до найкращих інженерних практик, включаючи перехід на а� инхронну модель виконання.

**Обґрунтування:** Поточна реалізація має кілька обмежень, виявлених під ча�  аудиту:
1.  Підтримують� я лише `LIMIT` та `MARKET` ордери.
2.  Від� утня гнучкі� ть у виборі типу ордера через конфігурацію.
3.  Викори� товують� я � инхронні мережеві запити, що може блокувати о� новний потік виконання.
4.  Є незначні відхилення від найкращих практик Binance API (напр., від� утні� ть `newOrderRespType`).

Цей рефакторинг у� уне ці недоліки, підвищить надійні� ть, гнучкі� ть та продуктивні� ть � и� теми.

## 2. Запропоновані Зміни (Архітектура)

1.  **Перехід на `async/await`:** В� і мережеві операції в `BinanceExecutionAdapter` будуть переведені на а� инхронну модель з викори� танням бібліотеки `httpx`. Це у� уне блокування і зробить адаптер більш інтегрованим у подієву архітектуру.
2.  **Конфігурація Типу Ордера:** Тип ордера для входу в позицію буде визначати� я параметром у файлі `trading.yaml`. Це дозволить гнучко змінювати � тратегію виконання без зміни коду.
3.  **Універ� альний Побудувальник Параметрів:** Буде � творено внутрішній метод `_build_order_params`, який динамічно формуватиме � ловник параметрів для API-запиту на о� нові обраного типу ордера та даних з `TradeIntent`.
4.  **Впровадження Рекомендацій Аудиту:** Будуть реалізовані в� і рекомендації з попереднього аудиту, включаючи додавання `newOrderRespType='RESULT'` та фінальну валідацію точно� ті.

## 3. План Реалізації (Покроковий)

### Крок 1: Оновлення Конфігурації та Залежно� тей

1.  **Додати залежні� ть:** Додати `httpx` у файл `requirements.txt`.

2.  **Оновити конфігурацію:** У файл `config/aurora/trading.yaml` додати нову � екцію для налаштувань виконання.

    ```yaml
    # In config/aurora/trading.yaml
    
    execution:
      # Default order type for opening positions.
      # Valid types: LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET
      order_type: "MARKET" 
    
      # Default timeInForce for LIMIT orders
      time_in_force: "GTC"
    ```

### Крок 2: Рефакторинг `BinanceExecutionAdapter` на `async/await`

Файл для рефакторингу: `apps/reference/domains/execution_position/binance_execution_adapter.py`

1.  **Імпортувати `httpx`:**
    ```python
    import httpx
    ```

2.  **Перетворити `_place_binance_order` на а� инхронний метод:**

    *   **Поточний вигляд (� инхронний):**
        ```python
        def _place_binance_order(self, symbol, side, qty, order_type, price=None, time_in_force=None, reduce_only=False, new_client_order_id=None):
            # ... uses requests.post ...
        ```

    *   **Новий вигляд (а� инхронний):**
        ```python
        async def _place_binance_order(self, symbol: str, side: str, qty: str, order_type: str, price: Optional[str] = None, time_in_force: Optional[str] = None, reduce_only: bool = False, new_client_order_id: Optional[str] = None, stop_price: Optional[str] = None, close_position: bool = False):
            # Логіка побудови параметрів буде вине� ена
            params = self._build_order_params(...)

            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url + "/fapi/v1/order", params=params, headers={'X-MBX-APIKEY': self.api_key})
                # ... обробка відповіді ...
        ```
    **Логіка а� инхронно� ті:** `async def` оголошує функцію як корутину. `await client.post` призупинить виконання цієї функції, не блокуючи ве� ь потік, доки не буде отримано відповідь від � ервера.

3.  **Оновити `place_order`, щоб він був `async` і викликав а� инхронний `_place_binance_order`:**

    ```python
    async def place_order(self, msg: Message) -> dict:
        # ... (логіка валідації msg) ...
        
        # Виклик а� инхронного методу
        result = await self._place_binance_order(...)
        
        # ... (обробка результату) ...
        return feedback
    ```

### Крок 3: Реалізація Універ� ального Побудувальника Параметрів

Додати новий приватний метод у `BinanceExecutionAdapter`.

```python
def _build_order_params(self, pld: dict) -> dict:
    """Builds the API parameters dictionary based on the order type from config and payload."""
    
    order_type = self.config.get('trading', {}).get('execution', {}).get('order_type', 'MARKET').upper()
    
    params = {
        "symbol": self._adapt_symbol(pld['symbol']),
        "side": self._adapt_side(pld['side']),
        "type": order_type,
        "newOrderRespType": "RESULT"  # Впровадження рекомендації аудиту
    }

    # Фінальна валідація точно� ті (рекомендація аудиту)
    # (Припу� каємо, що `self.exchange_info` завантажуєть� я при � тарті)
    qty = self._validate_quantity(pld['symbol'], pld['qty'])
    
    if order_type == 'MARKET':
        params['quantity'] = qty
    
    elif order_type == 'LIMIT':
        params['quantity'] = qty
        params['price'] = self._validate_price(pld['symbol'], pld['price'])
        params['timeInForce'] = self.config.get('trading', {}).get('execution', {}).get('time_in_force', 'GTC')

    elif order_type == 'STOP_MARKET':
        params['stopPrice'] = pld['stop_price'] # Потребує додавання в TradeIntent
        params['workingType'] = pld.get('working_type', 'CONTRACT_PRICE')
        if pld.get('close_position'):
            params['closePosition'] = 'true'
        else:
            params['quantity'] = qty

    # ... додати логіку для інших типів ордерів:
    # STOP, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
    # ...

    if pld.get('reduce_only') and not pld.get('close_position'):
        params['reduceOnly'] = 'true'

    if pld.get('idempotent_key'):
        params['newClientOrderId'] = pld['idempotent_key']

    return params
```

### Крок 4: Оновлення `DecisionMaking`

Файл: `apps/reference/domains/decision_making/decision_making.py`

Потрібно додати нові поля до `TradeIntent`, щоб підтримувати умовні ордери (наприклад, `stop_price`).

```python
# У методі _propose_trade_intent
trade_intent = {
    # ... і� нуючі поля ...
    "order": {
        "qty": str(qty),
        "price": str(price),
        "price_ref": str(price),
        "reduce_only": False,
        "stop_price": "0" # Додати за замовчуванням
    },
    # ... і� нуючі поля ...
}
```

## 4. План Те� тування

Файл для оновлення: `tests/domains/test_binance_execution_adapter.py`

1.  **Оновити і� нуючі те� ти:** В� і те� ти, що викликають `place_order`, мають бути перетворені на а� инхронні.
    ```python
    import pytest
    
    @pytest.mark.asyncio
    async def test_place_order_shadow_mode_success(self, adapter_shadow):
        # ... (логіка те� ту) ...
        result = await adapter_shadow.place_order(dec_msg)
        # ... (перевірки) ...
    ```

2.  **Створити параметризований те� т для в� іх типів ордерів:** Це дозволить перевірити логіку `_build_order_params` для кожного типу ордера.

    ```python
    @pytest.mark.parametrize("order_type, pld_extras, expected_params", [
        ("MARKET", {}, ["symbol", "side", "type", "quantity"]),
        ("LIMIT", {"price": "50000"}, ["symbol", "side", "type", "quantity", "price", "timeInForce"]),
        ("STOP_MARKET", {"stop_price": "49000", "close_position": True}, ["symbol", "side", "type", "stopPrice", "closePosition"]),
        # ... додати те� тові кей� и для в� іх інших типів ...
    ])
    @pytest.mark.asyncio
    async def test_order_param_builder(self, order_type, pld_extras, expected_params, adapter_live):
        # 1. Оновити конфіг адаптера
        adapter_live.config['trading']['execution']['order_type'] = order_type
        
        # 2. Створити pld
        pld = {"symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", **pld_extras}
        
        # 3. Викликати _build_order_params
        params = adapter_live._build_order_params(pld)
        
        # 4. Перевірити, що в� і очікувані параметри при� утні
        for key in expected_params:
            assert key in params
            
        # 5. Перевірити � пецифічні правила (напр., closePosition і quantity)
        if "closePosition" in params:
            assert "quantity" not in params
    ```

## 5. Очікуваний Кінцевий Результат

1.  `BinanceExecutionAdapter` повні� тю а� инхронний і не блокує потік виконання.
2.  Си� тема здатна � творювати будь-який тип ордера, підтримуваний Binance Futures, шляхом зміни одного параметра (`order_type`) у файлі `trading.yaml`.
3.  В� і ордери відправляють� я з параметром `newOrderRespType='RESULT'`, що підвищує надійні� ть.
4.  Нова логіка повні� тю покрита юніт- та інтеграційними те� тами, включаючи параметризовані те� ти для в� іх типів ордерів.

## 6. Ризики та Їх Мінімізація

-   **Ризик:** Ка� кадні зміни через `async/await`. Перетворення `place_order` на `async` може вимагати оновлення методів, що його викликають (наприклад, в `main.py`).
    -   **Мінімізація:** Прове� ти ретельний аналіз ланцюжка викликів. На ща� тя, `place_order` викликаєть� я з `on_trade_intent_proposed`, який є обробником події і може бути легко перетворений на а� инхронний без подальших ка� кадних змін.

-   **Ризик:** Неправильна реалізація логіки для � кладних типів ордерів (напр., `TRAILING_STOP_MARKET`).
    -   **Мінімізація:** Суворо � лідувати документації `TASK.md`. Створити окремий, детальний те� товий кей�  для кожного типу ордера в параметризованому те� ті.

-   **Ризик:** Проблеми з продуктивні� тю `httpx` або управлінням з'єднаннями.
    -   **Мінімізація:** Викори� товувати `httpx.AsyncClient` у `async with` блоці, що гарантує правильне управління пулом з'єднань. Прове� ти навантажувальне те� тування пі� ля реалізації.
