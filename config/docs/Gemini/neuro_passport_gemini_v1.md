# 📄 Semantic Configuration Passport: `apps/reference/domains/neocortex/config/neuro.yaml` (Part 1)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/neuro_passport_gemini_v1.md
> - Scope: Lines 1-100 of `apps/reference/domains/neocortex/config/neuro.yaml`
> - Purpose: Capability mapping for the AI architectures (VAE, World Model) and sequence contracts.

Цей паспорт описує базову архітектуру нейронних мереж домену `neocortex` (ШІ-шару), а також правила гігієни даних та інференсу.

---

## 1. VAE (Variational Autoencoder)
Модель репрезентації (Representation Model). Відповідає за стиснення шумних ринкових фічів у чистий латентний простір ($Z_t$).

- **`input_dim: 20`:** Розмірність вхідного вектора. Жорстко пов'язана з `feature_list` у `ingest.yaml`.
- **`latent_dim: 16`:** Ступінь стиснення. Модель стискає 20 фічів до 16 латентних факторів.
- **`beta: 0.01`:** Вага KL-дивергенції. Налаштовує баланс між точністю відновлення (reconstruction) та регулярністю латентного простору.
- **`free_bits_per_dim: 0.2`:** Захист від `Posterior Collapse` (стану, коли декодер ігнорує латентний простір і VAE перетворюється на звичайний автоенкодер).
- **`regime_aux`:** `enabled: true`. 
  - *Capability:* Додатковий (Auxiliary) лосс. Примушує латентний простір ($Z_t$) не просто стискати дані, а кластеризуватися навколо 5 ринкових режимів (`num_classes: 5`). Це радикально покращує інтерпретованість моделі.

## 2. World Model (RNN Dynamics)
Рекурентна частина архітектури (для побудови справжнього Belief State).

- **`hidden_dim: 128`:** Розмір рекурентної пам'яті.
- **`sequence_length: 50`:** Довжина розгортання в часі для Backpropagation Through Time (BPTT). Модель "пам'ятає" і навчається на послідовностях з 50 кроків.

## 3. Sequence Contract (Правила Інференсу)
Фундаментальні правила роботи з пам'яттю (Memory Isolation).

- **`inference_mode: "stateless_per_event"`:**
  - *Capability:* Наразі агент працює без збереження довгострокової пам'яті (Stateless) на рівні кожного івенту.
  - *Причинність:* Це архітектурний компроміс (зафіксований в Red Team Audit), який обходить проблему `Causal Stream Poisoning`. Агент не накопичує пам'ять, а оцінює кожен стейт як незалежний.
- **`reset_on_*`:** Жорсткі правила обнулення стану. Пам'ять скидається при зміні символу (`reset_on_symbol_switch`), зміні мети (`objective_family_switch`) або на межі епізоду (`episode_boundary`).

## 4. Dataset Hygiene & Evaluation
- **`split`:** `train_ratio: 0.70`, `val: 0.15`, `test: 0.15`. Жорсткий поділ даних для офлайн-навчання. Запобігає перенавчанню (Catastrophic Overfitting).
- **`advisory_status: "forbidden"`:** `neocortex` не має права давати "поради" в основну шину, він працює суворо як ізольований тіньовий процес.

## 5. Performance & Shadow Gates
Захисні бар'єри (Bounded Control) на рівні інтеграції з FSM.

- **`operating_mode: "offline_replay"`:** Модель наразі не працює в онлайні. Вона налаштована лише на перепрогравання історичних логів.
- **`shadow_gates`:**
  - `allow_live_authority: false`: **Найголовніший інваріант безпеки.** ШІ апаратно відрізаний від права видавати реальні команди на відкриття/закриття ордерів у `vfoundation`.
  - `allow_policy_training_reenable: false`: Заборона онлайн-навчання (Online Learning). Ваги можуть оновлюватися лише в офлайні.
