# 📄 Semantic Configuration Passport: `apps/reference/domains/neocortex/config/neuro.yaml` (Part 2)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/neuro_passport_gemini_v2.md
> - Scope: Lines 101-152 of `apps/reference/domains/neocortex/config/neuro.yaml`
> - Purpose: Capability mapping for the PPO agent, reward semantics, and dreaming cycles.

Цей паспорт описує конфігурацію Policy-мережі (PPO), її гіперпараметри, правила оцінки та офлайн-цикли навчання.

---

## 6. PPO (Proximal Policy Optimization)

Модель, яка безпосередньо приймає рішення (Policy) на основі латентного простору ($Z_t$).

### Архітектура та Інтерфейс
- **`state_dim: 16`:** Розмірність входу. Суворо відповідає `latent_dim: 16` з конфігурації VAE. PPO "бачить" не сирі ринкові дані, а лише стиснений латентний вектор. Це рішення проблеми Curse of Dimensionality (POMDP).
- **`action_dim: 5`:** Вихідна розмірність. Наразі PPO не видає команди `ALLOW`/`BLOCK`, а намагається класифікувати 5 макро-режимів ринку (TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY, EXHAUSTION).
- **`policy_training_mode: "disabled"`:** Тренування політики примусово вимкнено в поточному рантаймі (узгоджується з архітектурною ізоляцією Actor-Learner).

### Семантика Винагороди (`reward_mode`)
- **`reward_mode: "regime_oracle"`:**
  - *Capability:* Модель нагороджується не за фінансовий PnL (`"pnl"`), а за здатність правильно передбачити майбутній ринковий режим (Self-Supervised Regime Prediction).
  - *Причинність (Red Team Audit):* Це підтверджує висновки аудиту: поточна реалізація `neocortex` ближча до класифікатора режимів (Regime Classifier), ніж до справжнього Trust Controller-а, оскільки її нагорода не враховує `Opportunity Cost` або втручання в FSM.

### Гіперпараметри Навчання (PPO Core)
- **`clip_epsilon: 0.2`:** Класичний ліміт PPO для запобігання надто великим змінам ваг за одну ітерацію (Trust Region).
- **`entropy_coef: 0.05`:** Бонус за ентропію (Entropy Bonus). 
  - *Sensitivity:* Змушує модель досліджувати нові варіанти дій. Занадто низьке значення (`0.01`) призводить до "Mode Collapse" (модель видає лише одну й ту саму дію). Занадто високе (`0.15`) — топить корисний сигнал у шумі. `0.08 - 0.05` визначено як ідеальний баланс.
- **`entropy_schedule`:** Динамічно зменшує бонус за експлорацію від `0.05` до `0.01` протягом `10000` кроків, дозволяючи моделі наприкінці навчання сфокусуватися на знайденому оптимумі (Convergence).

## 7. Checkpointing & Dreaming

### `checkpoint_every_n_steps`
- **Type:** `int` (100).
- **Capability:** Частота збереження ваг моделі (`.pt` файли). Для бектестів знижено до 100, щоб мати більш гранульовану історію навчання.

### `dream_episode_threshold` ("Сновидіння")
- **Type:** `int` (20).
- **Capability:** Визначає кількість завершених епізодів, які PPO має накопичити в Replay Buffer перед тим, як запустити процес оновлення ваг (Backpropagation / "Dreaming"). 
- **Причинність:** Оскільки `regime_oracle` стабілізується приблизно за 5 барів, збір 20 епізодів гарантує достатню статистичну вибірку для нормалізації (Advantage Normalization). Якщо брати менше (наприклад, 1 епізод), стандартне відхилення (std) буде нульовим, що призведе до математичної помилки (Degenerate NaN loss).
