# Інструкція з Розгортання та Запуску: Neocortex (Shadow Baseline Stage 0.3)

Цей документ містить офіційні команди для правильного запуску ізольованого мікросервісу `neocortex` у тіньовому режимі (Shadow Mode) поверх існуючого рантайму Aurora.

---

## 1. Загальні Вимоги до Середовища (Environment)

Мікросервіс `neocortex` працює як **абсолютно незалежний процес операційної системи**. Він взаємодіє з головним двигуном Aurora виключно через IPC (Inter-Process Communication) шину (Event Tap Endpoint).

**Важливо:**
1. Переконайтеся, що ви знаходитесь у корені проєкту (`C:\Users\user\Music\Phenix`).
2. Віртуальне середовище має бути активованим (префікс `(.venv)` у консолі).
3. Змінна `PYTHONPATH` має вказувати на корінь проєкту, щоб Python міг знайти пакет `apps`.

### Налаштування `PYTHONPATH` (Windows PowerShell):
```powershell
$env:PYTHONPATH = "."
```
*(Цю команду потрібно виконувати кожного разу при відкритті нового вікна PowerShell перед запуском бота).*

---

## 2. Команда Запуску (The Launch Command)

Для запуску Neocortex використовується синтаксис виконання модуля `python -m`, який гарантує правильну резолюцію імпортів всередині пакета `apps`.

### 2.1. Базовий Запуск (Дефолтні шляхи)
Якщо всі конфігурації лежать на стандартних місцях (`config/aurora` та `apps/reference/domains/neocortex/config`), а навчена модель знаходиться у `data/checkpoints/baseline_logreg_v1.pkl`, використовуйте базову команду:

```powershell
python -m apps.reference.domains.neocortex.main
```

### 2.2. Запуск із Перевизначенням Шляхів (Custom Parameters)
Утиліта підтримує аргументи командного рядка (CLI Arguments) для тонкого налаштування, якщо ви тестуєте різні версії моделей або конфігів:

```powershell
python -m apps.reference.domains.neocortex.main `
  --config-dir apps/reference/domains/neocortex/config `
  --aurora-config-dir config/aurora `
  --model-path data/checkpoints/baseline_logreg_v1.pkl `
  --event-tap-endpoint tcp://127.0.0.1:7101
```

#### Пояснення параметрів:
- `--config-dir`: Вказує на папку з `neuro.yaml`, `ingest.yaml`, `replay.yaml` та `system.yaml` специфічними для Neocortex.
- `--aurora-config-dir`: Вказує на кореневу папку конфігів (`domains.yaml`, `trading.yaml`), звідки Neocortex зчитує загальні ліміти та дозволені символи.
- `--model-path`: Шлях до серіалізованої `.pkl` моделі Логістичної Регресії (Dumb Baseline), натренованої на Експерименті 0.2.
- `--event-tap-endpoint`: Мережева адреса (IPC/TCP), на якій Neocortex слухатиме потік подій від основного процесу `AuroraCore`. (Має збігатися з `shadow_telemetry.ingest.tap_url` у `domains.yaml`).

---

## 3. Системні Попередження (Warnings) при Старті

При запуску ви побачите декілька `UserWarning` від `vfoundation.config`:
```text
UserWarning: RBAC_ADMIN_TOKENS not set - using INSECURE dev default...
UserWarning: SIGNING_KEY not set - using INSECURE dev default...
UserWarning: WORKER_ID not set - using generated ID...
```
**Це нормальна поведінка для локального/тестового середовища.** 
Оскільки Neocortex наразі працює у режимі `Shadow Mode` (Тіньовий Baseline) і не виставляє реальних ордерів, ви можете сміливо ігнорувати ці попередження про відсутність криптографічних ключів підпису (`SIGNING_KEY`). 
Коли (і якщо) ми переведемо Neocortex у бойовий режим (`enforce`), ці ключі потрібно буде налаштувати через `.env` файл для безпеки API.

---

## 4. Порядок Розгортання (Deployment Order)

Оскільки Neocortex — це відокремлений слухач, порядок запуску процесів має значення для уникнення помилок з'єднання (Connection Refused):

1. **Термінал 1:** Запустіть головний процес Aurora (`main.py`). Він підніме торгову шину та відкриє IPC порт (`7101`).
2. **Термінал 2:** Виконайте `$env:PYTHONPATH = "."`.
3. **Термінал 2:** Запустіть Neocortex: `python -m apps.reference.domains.neocortex.main`.
4. Перевірте логи: Neocortex має успішно підключитися до Tap Endpoint, завантажити `.pkl` модель і повідомити, що він увійшов у режим прослуховування.