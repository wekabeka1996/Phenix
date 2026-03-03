# Звіт про виконання P0 (Absorption Rewrite)

Я успішно імплементував усі зміни згідно з планом P0:

1. **Конфіг-SSOT (`apps/reference/config_models.py` та `config/aurora/domains.yaml`)**
   - Додано поле `dp_cap_pct` у `AbsorptionConfig` із жорсткою валідацією `extra='forbid'`.
   - Додано `model_validator`, який вимагає `dp_cap_pct`, якщо `mode != 'disabled'`.
   - В `domains.yaml` встановлено `dp_cap_pct: 0.02`.

2. **Типізований доступ (`apps/reference/domains/feature_engineering/types.py`)**
   - Створено властивість `absorption_dp_cap_pct`, яка жорстко перевіряє наявність конфіга і не має мовчазних магічних чисел (кидає `ValueError`, якщо параметру немає).

3. **Логіка без хардкоду (`apps/reference/domains/feature_engineering/calculation_engine.py`)**
   - В `compute_absorption` замінено `dp_cap = 0.02` на `dp_cap = self.cfg.absorption_dp_cap_pct`.
   - В dedup-телеметрії замінено захардкоджене вікно перевірки довжини списку `10` на `self.cfg.absorption_dedup_window`.

4. **Виправлення контракту виклику (`apps/reference/domains/feature_engineering/feature_engineering.py`)**
   - Знайдено рядок `1049`, який падав з `TypeError` (бо передавалися старі аргументи `buy_vol` і `sell_vol`).
   - Виклик змінено на новий контракт: передаються `tfi` та `delta_price_pct`.

*Зверніть увагу:* Оскільки мій доступ до виконання шелл-команд перерваний помилкою NodeJS (`conpty.node`), я не можу безпосередньо запустити тести (`pytest`) чи `tools.validate_configs`. 

Будь ласка, запустіть локально команди перевірки з пункту 5 нашого плану, щоб переконатися, що все працює ідеально. Я повністю впевнений у цих змінах!