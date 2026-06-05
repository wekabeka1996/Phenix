# Neocortex — контракти подій (schemas)

Цей документ задає **контракти** для подій, які продукує Neocortex.  
Мета: зробити ці події “перекладними” у код 1:1 (payload schema + інваріанти).

> Усе нижче — SSOT. Якщо код/лог відрізняється — це баг/розсинхрон.

---

## 0) Загальні правила Message Envelope (vFoundation)

Якщо Neocortex працює in‑proc і емить події у FSM‑шину, конверт повинен відповідати `vfoundation/core/protocol.py`:
- `op="EVT"`
- `verb` = без префікса (наприклад `NEOCORTEX_STATE_UPDATED`), а повне імʼя в шіні: `EVT:NEOCORTEX_STATE_UPDATED`
- `src="neocortex"`
- `dst="any"` або конкретний домен
- `rid`: UUID (або стабільний rid епізоду)
- `ts`: unix ms
- `why`: ≤ 80 символів (або використовувати `truncate_why`)
- `data_ref`: WHY‑chain (деталі виносимо сюди)

У Standalone режимі ці ж контракти пишуться у JSONL без `Message`, але поля мають співпадати семантично.

---

## 1) `EVT:NEOCORTEX_STATE_UPDATED`

### Призначення
Періодичний “стан” Neocortex: метрики, latency‑safe summary, model hashes.

### Payload (schema sketch)
```json
{
  "ts": 1732900000000,
  "symbol": "BTCUSDT",
  "phase": "R1",
  "latent": {
    "z": [0.01, -0.20, 0.33],
    "dim": 3
  },
  "metrics": {
    "efe": 0.123,
    "surprisal": 2.34,
    "disagreement": 0.045,
    "empowerment": 0.67,
    "viability": {
      "tau": 0.0123,
      "error": 0.0101,
      "alive": true
    }
  },
  "models": {
    "world_model_hash": "sha256:...",
    "viability_hash": "sha256:..."
  }
}
```

### Інваріанти
- `ts` обовʼязковий, unix ms.
- `phase ∈ {R0,R1,R2,R3}`.
- `metrics.efe` існує з R1 (у R0 може бути відсутній або `null`, але це має бути вирішено в YAML контрактом).

---

## 2) `EVT:NEOCORTEX_ALERT`

### Призначення
Фіксація інваріантів, контракт‑помилок, OOD/аномалій, churn/flip storms.

### Payload
```json
{
  "ts": 1732900000000,
  "severity": "WARN",
  "code": "INVARIANT_MISSING_BRACKETS",
  "symbol": "ETHUSDT",
  "rid": "30ada409-8e77-4829-9ad8-2dec51d94606",
  "context": {
    "window_s": 60,
    "details": {
      "expected": "BRACKETS_PLACED",
      "found": []
    }
  }
}
```

### Інваріанти
- `severity ∈ {INFO,WARN,ERROR,CRITICAL}`
- `code` — строгий allowlist з YAML (щоб не плодити “рандомні” коди в рантаймі)

---

## 3) `EVT:NEOCORTEX_SHADOW_INTENT_PROPOSED` (R2)

### Призначення
Рекомендація без впливу: “що б я зробив”.

### Payload
```json
{
  "ts": 1732900000000,
  "symbol": "BTCUSDT",
  "action": "OPEN_LONG",
  "confidence": 0.62,
  "efe": 0.21,
  "empowerment": 0.55,
  "viability_alive": true,
  "why": [
    "efe=0.21",
    "emp=0.55",
    "regime=TREND_UP",
    "gate:risk_ok"
  ],
  "idempotent_key": "neocortex:R2:BTCUSDT:OPEN_LONG:1732900000:sha256:..."
}
```

### Інваріанти
- `idempotent_key` обовʼязковий (щоб не “спамити” репорти).
- `why[]` — max length/size з YAML.

---

## 4) `EVT:NEOCORTEX_TRADE_INTENT_PROPOSED` (R3, gated)

### Призначення
Реальний trade intent (окремий канал), який може бути конвертований bridge‑ом у `CMD:OPEN/CLOSE` **тільки якщо** дозволено YAML‑гейтами.

### Payload
Payload має відповідати `apps/reference/domains/decision_making/schemas/trade_intent_v1.json`, додатково:
```json
{
  "...trade_intent_v1_fields": "...",
  "idempotent_key": "neocortex:R3:ETHUSDT:OPEN_LONG:..."
}
```

### Інваріанти
- заборонено емити без `require_viability_calibrated_for_intents=true` (YAML gate).
- заборонено емити якщо freshness‑gates не пройдені (features/portfolio TTL).

---

## 5) `EVT:NEOCORTEX_MODULATION_PROPOSED` (R3, gated)

### Призначення
“Мʼяка” пропозиція overlay‑параметрів (thresholds/multipliers/cooldowns) без зміни SSOT.

### Payload
```json
{
  "ts": 1732900000000,
  "symbol": "BTCUSDT",
  "ttl_ms": 60000,
  "overlay": {
    "decision_making.signal_threshold_bias": -0.02,
    "decision_making.cooldown_mult": 1.5
  },
  "bounds_ref": "neocortex.safety.modulation_bounds.v1",
  "why": [
    "efe_high",
    "viability_ok",
    "reduce_churn"
  ],
  "idempotent_key": "neocortex:R3:BTCUSDT:MODULATE:..."
}
```

### Інваріанти
- тільки allowlist ключів (YAML).
- тільки bounded deltas (YAML).
- TTL обовʼязковий.

