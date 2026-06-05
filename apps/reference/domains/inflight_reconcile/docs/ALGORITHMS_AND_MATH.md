# Алгоритми та математика In-Flight Reconcile

## 1. Алгоритм детекції таймаутів
На кожній ітерації циклу `run_forever` виконується фільтрація:
$$ExpiredEntries = \{e \in Entries \mid (Now - e.created\_ts) \ge TTL_{config}\}$$

Додатково враховується інтервал між спробами звірки, щоб не спамити REST API:
$$(Now - e.last\_reconcile\_ts) \ge Interval_{reconcile}$$

## 2. Логіка ідемпотентного скасування
При досягненні `Max TTL`, реконсилер застосовує алгоритм "Best-effort Cleanup":
1. Викликати `cancel_order`.
2. Якщо отримано помилку `Order Not Found (-2011)`, вважати це успіхом (ордер уже відсутній).
3. Якщо отримано мережеву помилку, залишити стан `ERROR` та повторити спробу на наступному циклі.

## 3. Мапінг статусів
Функція `_map_exchange_status` нормалізує відповіді біржі:
- `NEW`, `PARTIALLY_FILLED` $	o$ `PENDING` (продовжуємо чекати).
- `FILLED`, `CANCELED`, `EXPIRED`, `REJECTED` $	o$ `TERMINAL` (видаляємо з черги).
