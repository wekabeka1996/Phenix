# 📄 Semantic Configuration Passport: `apps/reference/domains/neocortex/config/ingest.yaml` (Full File)

> AUDIT SUMMARY
> - Document path: config/docs/Gemini/ingest_passport_gemini_v1.md
> - Scope: Full File of `apps/reference/domains/neocortex/config/ingest.yaml`
> - Purpose: Capability mapping for raw feature ingestion, normalization, and clipping for AI models.

Цей паспорт описує "фронтенд" даних для Neocortex: які саме фічі він збирає з торгової шини, і як їх математично "причісує" (нормалізує) перед тим, як згодувати нейромережі (VAE/PPO).

---

## 1. Feature Selection (`feature_list`)
- **Capability:** Суворий перелік із 20 ринкових фічів (OBI, TFI, Delta Price, Macro Sync тощо), які Neocortex має право бачити. 
- **Sensitivity:** Довжина цього списку (20) жорстко прив'язана до параметра `input_dim: 20` у конфігурації VAE (`neuro.yaml`). Додавання нової фічі сюди вимагає перекомпіляції всієї архітектури енкодера, інакше виникне `Shape Mismatch` помилка в PyTorch.

## 2. Normalization & Scaling (`normalization`)
Нейромережі руйнуються, якщо вхідні дані мають різний масштаб (напр., ціна 60,000 і OBI 0.5). Цей блок стандартизує світ.
- **`normalization_method: "zscore"`:** Кожна фіча приводиться до нормального розподілу (середнє 0, відхилення 1) на основі ковзного вікна в 500 барів (`normalization_window`).
- **`normalization_scope: "per_symbol"`:** Нормалізація рахується для кожного активу окремо (BTC не змішується з ETH). Запобігає Cross-Asset Poisoning.
- **`price_feature_mode: "log"` / `delta_price_mode: "pct"`:** Цінові дані екстремально нестаціонарні. Передача їх як абсолютних значень зведе ШІ з розуму. Тому ціна логарифмується, а зміна ціни передається як відсоток (`pct`).

## 3. Safety Clipping (`feature_clip_abs`)
- **Capability:** "Хард-кліпінг" (Жорстке обрізання) важких хвостів розподілу (Heavy-tail features) перед нормалізацією.
- **Причинність:** Ринкові аномалії (напр., ліквідації) генерують божевільні значення фічів (`volume_zscore = 100`). Z-score нормалізатор не впорається з таким викидом, і в мережу залетить величезна цифра, знищивши градієнти (Exploding Gradients).
- **Межі:** `delta_price` зрізається на 20% (0.2), `macro_resid` на 5.0, а `volume_zscore` на 10.0. Все, що вище, прирівнюється до цих значень.

## 4. Buffering, Warmup & Robustness
- **`min_samples_before_ready: 100`:** ШІ не почне робити висновки після старту системи, доки не збере 100 свіжих зразків для побудови адекватної Z-Score статистики. До цього моменту Neocortex повертає `not_ready`.
- **`nan_strategy: "zero"`:** Якщо фіча зникає (напр. біржа не віддала стакан), вона прирівнюється до 0 (середнє значення в нормалізованому просторі). Це не ламає мережу, а просто означає для неї "нейтральний/невідомий стан" даної фічі.
