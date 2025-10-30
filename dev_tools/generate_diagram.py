import os

def generate_mermaid_file(filename="system_architecture.mmd"):
    mermaid_code = """
%% Direction: Top to Bottom
graph TD

    %% Define Styles for different component types
    classDef data fill:#e6f2ff,stroke:#0066cc
    classDef logic fill:#e6ffe6,stroke:#009933
    classDef core fill:#fff2e6,stroke:#ff9900
    classDef execution fill:#ffe6f2,stroke:#cc0066
    classDef external fill:#f2f2f2,stroke:#666
    classDef contracts fill:#f9f2ff,stroke:#9933ff
    classDef security fill:#ffe6e6,stroke:#cc0000
    classDef dr fill:#e0e0e0,stroke:#333

    %% == 1. Data Ingestion & Analysis (Cold Path) ==
    subgraph "1. Збір та Аналіз Даних (Вхідний Потік)"
        direction TB
        A[/"fa:fa-server Binance Market Stream"/] --> B(MarketDataConnector)
        B -- "EVT:MARKET_TICK_RECEIVED" --> C(FeatureEngineering)
        C -- "EVT:FEATURES_CALCULATED" --> D(DecisionMaking)
        B -- "EVT:MARKET_TICK_RECEIVED" --> E(RiskManagement)
        E -- "EVT:RISK_ASSESSMENT_COMPLETED" --> D
    end

    %% == 2. Прийняття Рішення (Серце Логіки) ==
    subgraph "2. Прийняття Рішення (Серце Логіки)"
        direction TB
        F(PositionTracking) -- "EVT:PORTFOLIO_STATE_UPDATED (Equity)" --> D
        D -- "Збирає фічі, ризик, стан портфеля" --> G{Прийняти Рішення?}
        G -- "Так (Сигнал > Поріг)" --> H["fa:fa-lightbulb EVT:TRADE_INTENT_PROPOSED (з why_chain)"]
        G -- "Ні (Слабкий сигнал / Ризик)" --> I(Відхилено)
    end

    %% == 3. Координація та Надійність (Мозок Системи) ==
    subgraph "3. Координація та Надійність (Мозок Системи)"
        direction TB
        H --> J(OrchestratorFSM)
        J -- "1. Застосувати 'Охоронців'" --> K(Guards)
        subgraph " "
            direction LR
            K_Idem["fa:fa-clone Idempotency"]
            K_TTL["fa:fa-clock TTL"]
            K_CB["fa:fa-bolt Circuit Breaker"]
        end
        K --> K_Idem & K_TTL & K_CB
        K_CB -- "2. Запит валідний" --> L(WAL)
        L -- "3. Запис в журнал (Write-Ahead Log)" --> J
        J -- "4. Створити команду (CMD:OPEN)" --> M(ExecPosFSM)
    end
    
    %% == 4. Виконання (Гарячий Шлях) ==
    subgraph "4. Виконання (Гарячий Шлях)"
        direction TB
        M -- "Обробити команду" --> N(OpenFlowFSM)
        N -- "Пройти Pre-Trade Guards" --> O{Рішення про Виконання}
        O -- "DEC:OPEN" --> P(Security)
        P -- "Підписати (Ed25519) + Перевірити (RBAC)" --> Q(BinanceAdapter)
        Q -- "REST API Call" --> R[/"fa:fa-server Binance API"/]
    end

    %% == 5. Замкнення Циклу (Зворотний Зв'язок) ==
    subgraph "5. Замкнення Циклу (Зворотний Зв'язок)"
        direction TB
        R -- "Execution Report (FILLED/CANCELED)" --> Q
        Q -- "EVT:TRADE_EXECUTED" --> F
        F -- "Оновити PnL та Equity" --> F
    end

    %% == Фундаментальні Компоненти (Cross-Cutting Concerns) ==
    subgraph "Фундаментальні Компоненти"
        direction LR
        subgraph " "
            Contracts["fa:fa-book Dictionaries (*.yaml)"] -- "vfound schema" --> Schemas["fa:fa-file-code JSON Schemas"]
            MetaFSM["fa:fa-cogs MetaFSM"] -- "Валідує дані за схемами" --> Schemas
        end
        subgraph " "
            Observability["fa:fa-binoculars Observability"]
            Logs_["fa:fa-file-alt Logs"]
            Metrics_["fa:fa-chart-line Metrics"]
            Tracing_["fa:fa-sitemap Tracing"]
            Observability --> Logs_ & Metrics_ & Tracing_
        end
    end

    %% Assign Classes
    class A,R external
    class B,C,E,F,Q data
    class D,G,H,I,N,O logic
    class J,K,L,K_Idem,K_TTL,K_CB,M core
    class P security
    class Contracts,Schemas,MetaFSM contracts
    class Observability,Logs_,Metrics_,Tracing_ dr
""
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print(f"✅ Mermaid.js діаграма збережена у файл: {filename}")
        print("\n--- Інструкції для генерації PNG ---")
        print("Ви можете конвертувати цей файл у PNG одним із способів:")
        print("\n1. Використання Mermaid CLI (mmdc):")
        print("   Якщо у вас встановлено Node.js, ви можете встановити mmdc:")
        print("   npm install -g @mermaid-js/mermaid-cli")
        print(f"   Потім виконайте команду:")
        print(f"   mmdc -i {filename} -o system_architecture.png")
        print("\n2. Використання онлайн-редактора Mermaid Live Editor:")
        print(f"   a. Відкрийте https://mermaid.live")
        print(f"   b. Відкрийте файл {filename} у текстовому редакторі.")
        print(f"   c. Скопіюйте весь вміст файлу {filename} і вставте його в ліву панель Mermaid Live Editor.")
        print(f"   d. Натисніть кнопку 'Download' або 'Export' (зазвичай іконка хмари зі стрілкою вниз) і оберіть формат PNG.")
        print("\n3. Використання VS Code з розширенням Mermaid:")
        print("   Якщо у вас встановлено розширення Mermaid для VS Code, просто відкрийте файл .mmd і скористайтеся функцією експорту.")

    except IOError as e:
        print(f"❌ Помилка при збереженні файлу: {e}")

if __name__ == "__main__":
    generate_mermaid_file()