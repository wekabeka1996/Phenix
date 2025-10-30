# План Рефакторингу Системи Виконання Ордерів Binance

**Версія:** 1.0
**Дата:** 2025-10-26
**Автор:** Gemini AI Agent

## 1. Мета та Обґрунтування

**Мета:** Модернізувати `BinanceExecutionAdapter` для підтримки всіх типів ордерів, зазначених у документації Binance Futures API, зробити його повністю конфігурованим та привести у відповідність до найкращих інженерних практик, включаючи перехід на асинхронну модель виконання.

**Обґрунтування:** Поточна реалізація має кілька обмежень, виявлених під час аудиту:
1.  Підтримуються лише `LIMIT` та `MARKET` ордери.
2.  Відсутня гнучкість у виборі типу ордера через конфігурацію.
3.  Використовуються синхронні мережеві запити, що може блокувати основний потік виконання.
4.  Є незначні відхилення від найкращих практик Binance API (напр., відсутність `newOrderRespType`).

Цей рефакторинг усуне ці недоліки, підвищить надійність, гнучкість та продуктивність системи.

## 2. Запропоновані Зміни (Архітектура)

1.  **Перехід на `async/await`:** Всі мережеві операції в `BinanceExecutionAdapter` будуть переведені на асинхронну модель з використанням бібліотеки `httpx`. Це усуне блокування і зробить адаптер більш інтегрованим у подієву архітектуру.
2.  **Конфігурація Типу Ордера:** Тип ордера для входу в позицію буде визначатися параметром у файлі `trading.yaml`. Це дозволить гнучко змінювати стратегію виконання без зміни коду.
3.  **Універсальний Побудувальник Параметрів:** Буде створено внутрішній метод `_build_order_params`, який динамічно формуватиме словник параметрів для API-запиту на основі обраного типу ордера та даних з `TradeIntent`.
4.  **Впровадження Рекомендацій Аудиту:** Будуть реалізовані всі рекомендації з попереднього аудиту, включаючи додавання `newOrderRespType='RESULT'` та фінальну валідацію точності.

## 3. План Реалізації (Покроковий)

### Крок 1: Оновлення Конфігурації та Залежностей

1.  **Додати залежність:** Додати `httpx` у файл `requirements.txt`.

2.  **Оновити конфігурацію:** У файл `config/aurora/trading.yaml` додати нову секцію для налаштувань виконання.

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

2.  **Перетворити `_place_binance_order` на асинхронний метод:**

    *   **Поточний вигляд (синхронний):**
        ```python
        def _place_binance_order(self, symbol, side, qty, order_type, price=None, time_in_force=None, reduce_only=False, new_client_order_id=None):
            # ... uses requests.post ...
        ```

    *   **Новий вигляд (асинхронний):**
        ```python
        async def _place_binance_order(self, symbol: str, side: str, qty: str, order_type: str, price: Optional[str] = None, time_in_force: Optional[str] = None, reduce_only: bool = False, new_client_order_id: Optional[str] = None, stop_price: Optional[str] = None, close_position: bool = False):
            # Логіка побудови параметрів буде винесена
            params = self._build_order_params(...)

            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url + "/fapi/v1/order", params=params, headers={'X-MBX-APIKEY': self.api_key})
                # ... обробка відповіді ...
        ```
    **Логіка асинхронності:** `async def` оголошує функцію як корутину. `await client.post` призупинить виконання цієї функції, не блокуючи весь потік, доки не буде отримано відповідь від сервера.

3.  **Оновити `place_order`, щоб він був `async` і викликав асинхронний `_place_binance_order`:**

    ```python
    async def place_order(self, msg: Message) -> dict:
        # ... (логіка валідації msg) ...
        
        # Виклик асинхронного методу
        result = await self._place_binance_order(...)
        
        # ... (обробка результату) ...
        return feedback
    ```

### Крок 3: Реалізація Універсального Побудувальника Параметрів

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

    # Фінальна валідація точності (рекомендація аудиту)
    # (Припускаємо, що `self.exchange_info` завантажується при старті)
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
    # ... існуючі поля ...
    "order": {
        "qty": str(qty),
        "price": str(price),
        "price_ref": str(price),
        "reduce_only": False,
        "stop_price": "0" # Додати за замовчуванням
    },
    # ... існуючі поля ...
}
```

## 4. План Тестування

Файл для оновлення: `tests/domains/test_binance_execution_adapter.py`

1.  **Оновити існуючі тести:** Всі тести, що викликають `place_order`, мають бути перетворені на асинхронні.
    ```python
    import pytest
    
    @pytest.mark.asyncio
    async def test_place_order_shadow_mode_success(self, adapter_shadow):
        # ... (логіка тесту) ...
        result = await adapter_shadow.place_order(dec_msg)
        # ... (перевірки) ...
    ```

2.  **Створити параметризований тест для всіх типів ордерів:** Це дозволить перевірити логіку `_build_order_params` для кожного типу ордера.

    ```python
    @pytest.mark.parametrize("order_type, pld_extras, expected_params", [
        ("MARKET", {}, ["symbol", "side", "type", "quantity"]),
        ("LIMIT", {"price": "50000"}, ["symbol", "side", "type", "quantity", "price", "timeInForce"]),
        ("STOP_MARKET", {"stop_price": "49000", "close_position": True}, ["symbol", "side", "type", "stopPrice", "closePosition"]),
        # ... додати тестові кейси для всіх інших типів ...
    ])
    @pytest.mark.asyncio
    async def test_order_param_builder(self, order_type, pld_extras, expected_params, adapter_live):
        # 1. Оновити конфіг адаптера
        adapter_live.config['trading']['execution']['order_type'] = order_type
        
        # 2. Створити pld
        pld = {"symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", **pld_extras}
        
        # 3. Викликати _build_order_params
        params = adapter_live._build_order_params(pld)
        
        # 4. Перевірити, що всі очікувані параметри присутні
        for key in expected_params:
            assert key in params
            
        # 5. Перевірити специфічні правила (напр., closePosition і quantity)
        if "closePosition" in params:
            assert "quantity" not in params
    ```

## 5. Очікуваний Кінцевий Результат

1.  `BinanceExecutionAdapter` повністю асинхронний і не блокує потік виконання.
2.  Система здатна створювати будь-який тип ордера, підтримуваний Binance Futures, шляхом зміни одного параметра (`order_type`) у файлі `trading.yaml`.
3.  Всі ордери відправляються з параметром `newOrderRespType='RESULT'`, що підвищує надійність.
4.  Нова логіка повністю покрита юніт- та інтеграційними тестами, включаючи параметризовані тести для всіх типів ордерів.

## 6. Ризики та Їх Мінімізація

-   **Ризик:** Каскадні зміни через `async/await`. Перетворення `place_order` на `async` може вимагати оновлення методів, що його викликають (наприклад, в `main.py`).
    -   **Мінімізація:** Провести ретельний аналіз ланцюжка викликів. На щастя, `place_order` викликається з `on_trade_intent_proposed`, який є обробником події і може бути легко перетворений на асинхронний без подальших каскадних змін.

-   **Ризик:** Неправильна реалізація логіки для складних типів ордерів (напр., `TRAILING_STOP_MARKET`).
    -   **Мінімізація:** Суворо слідувати документації `TASK.md`. Створити окремий, детальний тестовий кейс для кожного типу ордера в параметризованому тесті.

-   **Ризик:** Проблеми з продуктивністю `httpx` або управлінням з'єднаннями.
    -   **Мінімізація:** Використовувати `httpx.AsyncClient` у `async with` блоці, що гарантує правильне управління пулом з'єднань. Провести навантажувальне тестування після реалізації.
