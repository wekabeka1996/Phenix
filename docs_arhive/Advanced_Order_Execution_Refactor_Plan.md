# Інженерний План: Рефакторинг Системи Виконання Ордерів

**Версія:** 2.0
**Дата:** 2025-10-26
**Автор:** Gemini AI Agent
**Статус:** Запропоновано

## 1. Мета та Обґрунтування

**Мета:** Провести глибокий рефакторинг `BinanceExecutionAdapter` та пов'язаних компонентів для досягнення трьох цілей:
1.  **Повна Підтримка Типів Ордерів:** Забезпечити можливість створення будь-якого типу ордера, описаного в `TASK.md`, через конфігурацію.
2.  **Перехід на Асинхронність:** Усунути блокуючі операції вводу-виводу шляхом переходу на асинхронну модель `async/await` з використанням `httpx`.
3.  **Відповідність Найкращим Практикам:** Реалізувати рекомендації аудиту, включаючи використання `newOrderRespType='RESULT'` та валідацію точності параметрів.

**Обґрунтування:** Цей рефакторинг є критичним кроком для підвищення надійності, гнучкості та продуктивності системи, а також для закладення фундаменту для майбутніх розширень, таких як інтеграція з LLA.

## 2. Аналіз Поточного Стану

-   **Адаптер (`BinanceExecutionAdapter`):** Використовує синхронну бібліотеку `requests`, що блокує потік під час API-запитів.
-   **FSM (`OpenFlowFSM`, `CloseFlowFSM`):** Методи `handle` є синхронними (`def`). Вони безпосередньо викликають методи адаптера.
-   **Логіка Створення Ордера:** Жорстко закодована для `LIMIT` та `MARKET` типів.
-   **Конфігурація:** Відсутня можливість гнучко керувати типами ордерів та їх параметрами (напр., `timeInForce`).

## 3. Запропонована Архітектура та Зміни

1.  **Асинхронний Адаптер:** `BinanceExecutionAdapter` буде повністю переписаний з використанням `async def` для всіх методів, що виконують мережеві запити. Бібліотека `requests` буде замінена на `httpx`.
2.  **Асинхронні FSM:** Методи `handle` в `OpenFlowFSM`, `ManageFlowFSM` та `CloseFlowFSM`, які ініціюють виклики до адаптера, будуть перетворені на `async def`.
3.  **Асинхронний Головний Цикл:** Головний цикл додатку (в `apps/reference/main.py`), який обробляє повідомлення та викликає `fsm.handle()`, буде адаптований для роботи з асинхронними FSM (з використанням `await`).
4.  **Конфігурація в `trading.yaml`:** Буде розширено секцію `execution` для визначення не тільки типу ордера, але й специфічних параметрів для кожного типу.
5.  **Універсальний Побудувальник Параметрів:** В адаптері буде створено метод `_build_order_params`, який буде динамічно генерувати параметри для Binance API на основі конфігурації та даних з `TradeIntent`.

## 4. Покроковий План Реалізації

### Крок 1: Оновлення Залежностей та Конфігурації

1.  **Додати `httpx`:** У файл `requirements.txt` додати рядок:
    ```
    httpx
    ```
2.  **Розширити `trading.yaml`:** Оновити `config/aurora/trading.yaml`, додавши деталізовану секцію `execution`.

    ```yaml
    # In config/aurora/trading.yaml
    execution:
      # Тип ордера для відкриття позиції.
      # Допустимі значення: MARKET, LIMIT, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET
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
    **Логіка асинхронності:** `async with httpx.AsyncClient()` створює асинхронний контекстний менеджер для управління сесією. `await client.post` неблокуюче очікує на відповідь від сервера.

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
        
        # ... і так далі для всіх типів ...

        return params
    ```

### Крок 3: Адаптація FSM до Асинхронності

**Файли:** `apps/reference/domains/execution_position/fsm_open.py`, `fsm_close.py`

Методи, що викликають адаптер, мають стати `async def` і використовувати `await`.

```python
# В apps/reference/domains/execution_position/fsm_open.py
class OpenFlowFSM:
    # ...
    async def _execute_open_order(self, msg: Message) -> Optional[Message]:
        # ...
        feedback = await self.adapter.place_order(open_cmd)
        # ...
```

### Крок 4: Оновлення Тестів

**Файл:** `tests/domains/test_binance_execution_adapter.py`

1.  **Додати `pytest-asyncio`:** Переконатися, що він встановлений.
2.  **Оновити тести:** Позначити всі тести, що викликають асинхронні методи, як `@pytest.mark.asyncio` і використовувати `await`.

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
    **Примітка:** Для мокування асинхронних методів потрібно використовувати `mock.AsyncMock`.

3.  **Додати параметризований тест** для `_build_order_params`, як було описано в попередньому плані, щоб покрити всі типи ордерів.

## 5. Критерії Успіху

1.  Всі існуючі та нові тести в `tests/domains/test_binance_execution_adapter.py` проходять успішно.
2.  Система здатна успішно відправити `MARKET` ордер на тестову мережу Binance (перевіряється вручну або через інтеграційний тест).
3.  Зміна `open_order_type` в `trading.yaml` на `LIMIT` призводить до успішної відправки `LIMIT` ордера.
4.  Код пройшов статичний аналіз (linting) без зауважень.

## 6. Ризики

-   **Каскадний рефакторинг:** Перехід на `async` може вимагати змін у непередбачених частинах коду.
    -   **Мінімізація:** Дотримуватися покрокового плану, ретельно тестуючи кожен етап. Аналіз показує, що зміни в основному локалізовані в домені `execution_position`.
-   **Складність тестування:** Мокування асинхронного коду є складнішим.
    -   **Мінімізація:** Використовувати стандартні інструменти (`pytest-asyncio`, `mock.AsyncMock`) та слідувати встановленим патернам.

Я готовий розпочати реалізацію цього плану за вашою командою.
