# Інженерний План: Рефакторинг Си� теми Виконання Ордерів

**Вер� ія:** 2.0
**Дата:** 2025-10-26
**Автор:** Gemini AI Agent
**Стату� :** Запропоновано

## 1. Мета та Обґрунтування

**Мета:** Прове� ти глибокий рефакторинг `BinanceExecutionAdapter` та пов'язаних компонентів для до� ягнення трьох цілей:
1.  **Повна Підтримка Типів Ордерів:** Забезпечити можливі� ть � творення будь-якого типу ордера, опи� аного в `TASK.md`, через конфігурацію.
2.  **Перехід на А� инхронні� ть:** У� унути блокуючі операції вводу-виводу шляхом переходу на а� инхронну модель `async/await` з викори� танням `httpx`.
3.  **Відповідні� ть Найкращим Практикам:** Реалізувати рекомендації аудиту, включаючи викори� тання `newOrderRespType='RESULT'` та валідацію точно� ті параметрів.

**Обґрунтування:** Цей рефакторинг є критичним кроком для підвищення надійно� ті, гнучко� ті та продуктивно� ті � и� теми, а також для закладення фундаменту для майбутніх розширень, таких як інтеграція з LLA.

## 2. Аналіз Поточного Стану

-   **Адаптер (`BinanceExecutionAdapter`):** Викори� товує � инхронну бібліотеку `requests`, що блокує потік під ча�  API-запитів.
-   **FSM (`OpenFlowFSM`, `CloseFlowFSM`):** Методи `handle` є � инхронними (`def`). Вони безпо� ередньо викликають методи адаптера.
-   **Логіка Створення Ордера:** Жор� тко закодована для `LIMIT` та `MARKET` типів.
-   **Конфігурація:** Від� утня можливі� ть гнучко керувати типами ордерів та їх параметрами (напр., `timeInForce`).

## 3. Запропонована Архітектура та Зміни

1.  **А� инхронний Адаптер:** `BinanceExecutionAdapter` буде повні� тю перепи� аний з викори� танням `async def` для в� іх методів, що виконують мережеві запити. Бібліотека `requests` буде замінена на `httpx`.
2.  **А� инхронні FSM:** Методи `handle` в `OpenFlowFSM`, `ManageFlowFSM` та `CloseFlowFSM`, які ініціюють виклики до адаптера, будуть перетворені на `async def`.
3.  **А� инхронний Головний Цикл:** Головний цикл додатку (в `apps/reference/main.py`), який обробляє повідомлення та викликає `fsm.handle()`, буде адаптований для роботи з а� инхронними FSM (з викори� танням `await`).
4.  **Конфігурація в `trading.yaml`:** Буде розширено � екцію `execution` для визначення не тільки типу ордера, але й � пецифічних параметрів для кожного типу.
5.  **Універ� альний Побудувальник Параметрів:** В адаптері буде � творено метод `_build_order_params`, який буде динамічно генерувати параметри для Binance API на о� нові конфігурації та даних з `TradeIntent`.

## 4. Покроковий План Реалізації

### Крок 1: Оновлення Залежно� тей та Конфігурації

1.  **Додати `httpx`:** У файл `requirements.txt` додати рядок:
    ```
    httpx
    ```
2.  **Розширити `trading.yaml`:** Оновити `config/aurora/trading.yaml`, додавши деталізовану � екцію `execution`.

    ```yaml
    # In config/aurora/trading.yaml
    execution:
      # Тип ордера для відкриття позиції.
      # Допу� тимі значення: MARKET, LIMIT, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
      open_order_type: "MARKET"

      # Параметри для кожного типу ордера
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

### Крок 2: Рефакторинг `BinanceExecutionAdapter`

**Файл:** `apps/reference/domains/execution_position/binance_execution_adapter.py`

1.  **Замінити імпорт `requests` на `httpx`**.

2.  **Перетворити ключові методи на `async def`:**

    ```python
    # Новий вигляд
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

    # Також перетворити _set_leverage, _set_margin_type, _get_listen_key і т.д.
    ```
    **Логіка а� инхронно� ті:** `async with httpx.AsyncClient()` � творює а� инхронний контек� тний менеджер для управління � е� ією. `await client.post` неблокуюче очікує на відповідь від � ервера.

3.  **Реалізувати `_build_order_params`:**

    ```python
    def _build_order_params(self, pld: dict) -> dict:
        order_type = self.config.get('trading', {}).get('execution', {}).get('open_order_type', 'MARKET').upper()
        
        params = {
            "symbol": self._adapt_symbol(pld['symbol']),
            "side": self._adapt_side(pld['side']),
            "type": order_type,
            "newOrderRespType": "RESULT"
        }

        # ... (логіка для кожного типу ордера з TASK.md) ...
        # Приклад для LIMIT
        if order_type == 'LIMIT':
            params['quantity'] = pld['qty']
            params['price'] = pld['price']
            params['timeInForce'] = self.config.get('trading', {}).get('execution', {}).get('order_params', {}).get('LIMIT', {}).get('timeInForce', 'GTC')

        # Приклад для STOP_MARKET з closePosition
        elif order_type == 'STOP_MARKET' and pld.get('close_position'):
            params['stopPrice'] = pld['stop_price']
            params['closePosition'] = 'true'
        
        # ... і так далі для в� іх типів ...

        return params
    ```

### Крок 3: Адаптація FSM до А� инхронно� ті

**Файли:** `apps/reference/domains/execution_position/fsm_open.py`, `fsm_close.py`

Методи, що викликають адаптер, мають � тати `async def` і викори� товувати `await`.

```python
# В apps/reference/domains/execution_position/fsm_open.py
class OpenFlowFSM:
    # ...
    async def _execute_open_order(self, msg: Message) -> Optional[Message]:
        # ...
        feedback = await self.adapter.place_order(open_cmd)
        # ...
```

### Крок 4: Оновлення Те� тів

**Файл:** `tests/domains/test_binance_execution_adapter.py`

1.  **Додати `pytest-asyncio`:** Переконати� я, що він в� тановлений.
2.  **Оновити те� ти:** Позначити в� і те� ти, що викликають а� инхронні методи, як `@pytest.mark.asyncio` і викори� товувати `await`.

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
    **Примітка:** Для мокування а� инхронних методів потрібно викори� товувати `mock.AsyncMock`.

3.  **Додати параметризований те� т** для `_build_order_params`, як було опи� ано в попередньому плані, щоб покрити в� і типи ордерів.

## 5. Критерії У� піху

1.  В� і і� нуючі та нові те� ти в `tests/domains/test_binance_execution_adapter.py` проходять у� пішно.
2.  Си� тема здатна у� пішно відправити `MARKET` ордер на те� тову мережу Binance (перевіряєть� я вручну або через інтеграційний те� т).
3.  Зміна `open_order_type` в `trading.yaml` на `LIMIT` призводить до у� пішної відправки `LIMIT` ордера.
4.  Код пройшов � татичний аналіз (linting) без зауважень.

## 6. Ризики

-   **Ка� кадний рефакторинг:** Перехід на `async` може вимагати змін у непередбачених ча� тинах коду.
    -   **Мінімізація:** Дотримувати� я покрокового плану, ретельно те� туючи кожен етап. Аналіз показує, що зміни в о� новному локалізовані в домені `execution_position`.
-   **Складні� ть те� тування:** Мокування а� инхронного коду є � кладнішим.
    -   **Мінімізація:** Викори� товувати � тандартні ін� трументи (`pytest-asyncio`, `mock.AsyncMock`) та � лідувати в� тановленим патернам.

Я готовий розпочати реалізацію цього плану за вашою командою.
