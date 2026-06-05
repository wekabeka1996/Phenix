# Алгоритми та математика Regime Detector

## 1. Впевненість тренду (SMA Confidence)
Розраховується на основі розходження (divergence) середніх ліній.
$$Conf = \left| \frac{SMA_{short} - SMA_{long}}{SMA_{long}} ight| \cdot Multiplier$$
Результат обмежується діапазоном $[0.5, 0.95]$.

## 2. Volatility Ratio
Відношення поточного ATR до його історичного середнього (baseline).
$$VolRatio = \frac{ATR_{current}}{SMA(ATR, 100)}$$
- Якщо $VolRatio > Threshold_{high} 	o$ `HIGH_VOLATILITY`.
- Якщо $VolRatio < Threshold_{low} 	o$ `LOW_VOLATILITY`.

## 3. Mean Reversion Thresholds
Режим активується, якщо спред SMA та відхилення ціни від них не перевищують ліміт (зазвичай 0.5%):
$$\max(Spread, Dev_{short}, Dev_{long}) < Threshold_{MR}$$

## 4. Slope Gate (Швидкість шторму)
Вимірює різницю між двома EMA волатильності:
$$Slope = EMA(VolRatio, 3) - EMA(VolRatio, 6)$$
Якщо $Slope \le \epsilon$ під час шторму, це може бути сигналом до деескалації режиму.
