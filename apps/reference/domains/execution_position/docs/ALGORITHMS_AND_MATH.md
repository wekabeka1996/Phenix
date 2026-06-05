# Алгоритми та математика Execution Position

## 1. Нормалізація кількості (Qty Normalizer)
Кожен ордер проходить сувору перевірку перед відправкою.

**Логіка ROUND_DOWN:**
$$Q_{normalized} = 	ext{floor}\left(\frac{Q_{raw}}{StepSize}ight) \cdot StepSize$$
*Важливо: Якщо $Q_{normalized} < MinQty$ або $Q_{normalized} \cdot Price < MinNotional$, ордер відхиляється.*

## 2. Цілісність ціни (Anti-2021)
Для стоп-ордерів (SL) система перевіряє, чи не призведе виставлення ордера до його негайного виконання (Error -2021).

**Для LONG позиції (Stop Loss):**
Мусить бути: $Price_{stop} < Price_{mark} - Offset_{safety}$
Якщо умова порушена, ціна стопу автоматично коригується (widening) або ордер відхиляється.

## 3. Двигун Soft Clip (Ризикова обрізка)
Обчислює максимально допустимий обсяг ($Q_{max}$) на основі лімітів.

**Спрощена формула:**
$$Q_{max} = \min(L_{margin}, L_{concentration}, L_{side})$$
Якщо $Q_{requested} > Q_{max}$, то $Q_{final} = Q_{max}$.

## 4. Трейлінг-стоп (Trailing Logic)
Динамічне оновлення стоп-лосу при русі ціни у вигідному напрямку.

**Розрахунок для LONG:**
$$NewSL = \max(CurrentSL, HighestPrice - TrailingOffset)$$
*Крок оновлення ($TrailingOffset$) зазвичай прив'язаний до волатильності (ATR).*
