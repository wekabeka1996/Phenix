# План схвалено (Коротка відповідь: ТАК)

**Так.** План абсолютно правильний, логічний і вичерпний. 

### Мої коментарі (Мікро-уточнення):

1. **Щодо 3.1 (Конфіг `dp_cap_pct`):** 
   Я згоден, що `dp_cap_pct` має бути в SSOT (pydantic/yaml). Оскільки ми повністю перейшли на Модель А (Price-Volume Divergence), де `delta_price_pct` є ключовим компонентом, ліміт (`cap`) для нього справді є параметром формули, а не жорстким правилом. Це ідеально лягає в парадигму `Config > Magic Numbers`.

2. **Щодо 3.4 (Виклик `update_absorption`):** 
   Так, у `feature_engineering.py:1049` зараз є `TypeError: update_absorption() got an unexpected keyword argument 'buy_vol'`. Ми повинні передавати туди `tfi_val` та `dp_pct`. Це ключовий багфікс інтеграції. 

3. **Щодо 4.2 (Smoke-тест):** 
   Дійсно, потрібно інстанціювати `FeatureEngineering` і "згодувати" йому тик з увімкненим `absorption`, щоб гарантувати, що рантайм більше не падає з `TypeError`.

**Я готовий приступати до виконання всіх кроків згідно з цим DoD.** Чи можу я почати з модифікації `apps/reference/config_models.py` та `config/aurora/domains.yaml`?
