# Атлас домену Regime Allowlist

## 1. Огляд (Scope & Purpose)
Домен **regime_allowlist** — це контролер логічної цілісності стратегій. Його мета — переконатися, що призначені стратегії (напр. Mean Reversion) мають дозволені режими ринку, у яких вони фізично здатні працювати.

**Межі відповідальності:**
- Валідація конфігурації `allowed_regimes` для кожного символу.
- Перевірка сумісності між типом стратегії та дозволеними фазами ринку.
- Надання зрозумілих пояснень (Explainability) у разі блокування торгівлі через режим.

## 2. Карта залежностей (Dependencies)
```mermaid
graph TD
    subgraph "Configuration SSOT"
        S[strategies.yaml]
        A[aurora.yaml]
    end
    subgraph "Domain: regime_allowlist"
        RAC[RegimeAllowlistContract]
        SVC[StrategyRegimeConfig]
    end
    subgraph "Runtime"
        DM[decision_making]
    end

    S --> RAC
    A --> RAC
    RAC -->|validate| SVC
    DM -->|is_regime_allowed| RAC
```

- **Вхідні:** Конфігурації стратегій та інструментів.
- **Вихідні:** `RegimeAllowlistError` (на старті) або логування порушень.

## 3. Карта файлів (File Map)
- `contract.py`: Містить усю логіку валідації, реєстр сумісних режимів та класи порушень.

## 4. Карта подій (Event Map)
*Домен не використовує події FSM*. Він викликається як сервіс валідації під час старту системи або як утиліта пояснення причин блокування в `decision_making`.

## 5. Діаграма послідовності (Startup Validation)
```mermaid
sequenceDiagram
    participant S as Startup Hook
    participant RAC as RegimeAllowlistContract
    participant C as Config (YAML)

    S->>RAC: validate_all(assignments, aurora_assets)
    RAC->>C: extract allowed_regimes
    RAC->>RAC: check compatibility (e.g. MR needs FLAT)
    alt Critical Violation
        RAC-->>S: Raise RegimeAllowlistError (FAIL-CLOSED)
    else OK
        RAC-->>S: Validation Success
    end
```
