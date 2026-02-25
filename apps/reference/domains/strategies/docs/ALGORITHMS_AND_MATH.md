# Алгоритми та математика Strategies

## 1. Алгоритм збору призначених ID
Рантайм виконує ітерацію по вкладеному словнику `assignments`:
1. $AssignedSet = \emptyset$
2. For each $Symbol, StrategyList$ in $Assignments$:
   - For each $ID$ in $StrategyList$:
     - $AssignedSet.add(ID)$
3. $AssignedSet$ використовується для мінімізації кількості створюваних об'єктів (створюється лише по одному хендлеру на кожен тип стратегії, який керує всіма своїми символами).

## 2. Валідація відсутності плагінів
Для кожного $ID \in AssignedSet$:
- Якщо $Registry.get(ID) 	ext{ is } None$:
  - Додати $ID$ до списку $Missing$.
Якщо $Missing 
eq \emptyset 	o$ Помилка запуску.
