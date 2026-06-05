# Алгоритми та математика Position Tracking

## 1. Середня ціна входу (Weighted Average Price)
При накопиченні позиції в одному напрямку:
$$Price_{new\_avg} = \frac{Qty_{current} \cdot Price_{avg} + Qty_{trade} \cdot Price_{trade}}{Qty_{current} + Qty_{trade}}$$

При перевороті позиції (Flip):
Якщо нова угода повністю перекриває стару, ціна входу стає ціною останньої угоди для залишку.

## 2. Розрахунок реалізованого P&L
PnL розраховується лише при зменшенні або закритті позиції:
$$PnL_{delta} = Sign_{position} \cdot Qty_{closed} \cdot (Price_{exit} - Price_{entry}) - Fees$$
Де $Sign_{position} = +1$ для LONG та $-1$ для SHORT.

## 3. Розрахунок маржі (Margin Used)
Домен розраховує маржу, використовуючи цільове плече ($L$) з конфігурації:
$$Margin_{usd} = \frac{|Qty| \cdot Price_{entry}}{L}$$

## 4. Детекція порожніх позицій (Dust Handling)
Для запобігання накопиченню мікро-залишків ("пилу"), позиція вважається закритою, якщо:
$$|Qty| < Threshold_{flat}$$
(За замовчуванням $10^{-8}$).
