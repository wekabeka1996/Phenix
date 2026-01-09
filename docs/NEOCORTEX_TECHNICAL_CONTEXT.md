# Neocortex Technical Context

Technical extraction from Aurora/vFoundation codebase for Neocortex domain integration.

---

## 1. vFoundation Contract

### 1.1 Message Structure

**Location:** `vfoundation/core/protocol.py`

```python
class Message(BaseModel):
    v: int = 1
    op: Op  # Literal["ASK", "DEC", "CMD", "EVT", "UPD", "ERR"]
    verb: str
    src: str
    dst: str | Literal["any"]
    rid: str  # request ID (UUID)
    span_id: str  # tracing span ID
    parent_span_id: Optional[str] = None
    ts: int  # timestamp milliseconds
    ttl_ms: int = 2000  # TTL 1..30000
    key: Optional[str] = None
    idempotent_key: Optional[str] = None
    pld: Dict[str, Any]  # payload
    why: Optional[str] = None  # <=80 chars
    why_explain_ref: Optional[str] = None
    intent: Optional[IntentType] = None
    data_ref: List[str] = []
    sig: Optional[str] = None
    mode: str = "live"  # live, backtest, paper
    mode_contract: Optional[str] = None
    corr_id: Optional[str] = None
    oco_group_id: Optional[str] = None
    parent_client_order_id: Optional[str] = None
    link_ack_id: Optional[str] = None
    link_fill_id: Optional[str] = None
```

**Key Fields:**
- `op`: Operation type (EVT for events, CMD for commands, DEC for decisions)
- `verb`: Action token (e.g., "FEATURES_CALCULATED", "TRADE_INTENT_PROPOSED")
- `pld`: Payload dictionary (feature data, order details, etc.)
- `rid`: Request correlation ID
- `ts`: Timestamp in milliseconds
- `ttl_ms`: Message TTL (range: 1..30000 ms)
- `why`: Causality string (max 80 chars)

### 1.2 Event Bus

**Location:** `vfoundation/core/fsm_core.py`

**Subscribe to events:**
```python
def listen(self, event_name: str, callback: Callable) -> None:
    """Register event listener."""
    if event_name not in self.listeners:
        self.listeners[event_name] = []
    self.listeners[event_name].append(callback)
```

**Emit events:**
```python
def emit(self, event_name: str, payload: Dict[str, Any], why: str, data_ref: Optional[List[str]] = None) -> None:
    """Emit event to all registered listeners."""
    message = Message(
        op="EVT",
        verb=event_name.split(":")[1],
        src="fsm_core",
        dst="any",
        pld=payload,
        why=why,
        data_ref=data_ref or [],
    )
    for callback in self.listeners[event_name]:
        callback(message)
```

**Usage Example:**
```python
# Subscribe
self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features_calculated)

# Emit
self.fsm.emit("EVT:FEATURES_CALCULATED", payload=features_payload, why="features_calculated")
```

### 1.3 Domain YAML Structure

**Location:** `config/aurora/domains.yaml`

**Example Domain Config:**
```yaml
decision_making:
  position_sizing:
    min_position_size_usd: 10
    liquidity_based_cap_usd: 10000
    risk_fraction_q: null
    liquidity_kappa: 1.0
    kappa_mode: dynamic
  
  qos:
    exposure_block_cooldown_sec: 60
    symbol_cooldown_sec: 3
    max_intents_per_minute_per_symbol: 20
    mode: enforce
    enforce: true
    apply_to_strategies: ["aurora"]
  
  features:
    ttl_sec: 30

feature_engineering:
  enable_new_metrics: true
  volume_input_mode: integrate
  enabled_timeframes_sec: [180, 300]
  
  ema:
    period_short: 3
    period_long: 7
  
  volume:
    sma_length: 5
    window_sec: 60
    min_window_volume_usd: 1000.0
```

**Key Patterns:**
- Top-level keys = domain names
- Nested config for subsystems (position_sizing, qos, etc.)
- Lists for multi-value configs (enabled_timeframes_sec)
- Numeric configs for thresholds/parameters

---

## 2. Features Data (EVT:FEATURES_CALCULATED)

### 2.1 Event Payload Structure

**Location:** `apps/reference/domains/feature_engineering/contracts.py`

**Full Payload Schema:**
```python
class FeaturesCalculatedPayloadV1(BaseModel):
    ts: int  # timestamp milliseconds
    symbol: str  # e.g., "BTCUSDT"
    tf_sec: int  # timeframe seconds (180, 300)
    features: Dict[str, str]  # feature_name -> string value
    warmup: Optional[Dict[str, Any]]  # readiness state
    price_motion: Optional[Dict[str, Any]]  # multi-window returns/vol
```

### 2.2 Feature Set V1 (11 features)

**Base Features (always computed):**
```json
{
  "price": "50123.45",
  "obi": "0.15",
  "tfi": "-0.23",
  "delta_price": "10.5",
  "absorption": "0.0",
  "liquidity_kappa": "0.75"
}
```

**Phase 1 Features (config-gated by `enable_new_metrics`):**
```json
{
  "ema_bias": "0.65",
  "volume_spike": "0.82",
  "volatility_state": "0.43",
  "depth_imbalance": "0.58",
  "macro_sync": "0.71"
}
```

**Optional Features (R1/R2/V2):**
```json
{
  "macro_resid": "0.12",
  "absorption": "0.0",
  "volume_zscore": "1.25",
  "large_trade_imbalance": "0.34",
  "spread_bps": "5.2",
  "funding_rate_normalized": "-0.05",
  "oi_delta_pct": "2.3"
}
```

### 2.3 Data Types & Ranges

| Feature | Type | Range | Neutral | Notes |
|---------|------|-------|---------|-------|
| price | Decimal | ℝ+ | - | Current price |
| obi | Decimal | [-1, 1] | 0 | Order book imbalance |
| tfi | Decimal | [-1, 1] | 0 | Trade flow imbalance |
| delta_price | Decimal | ℝ | 0 | Price change |
| liquidity_kappa | Decimal | [0.3, 1] | 0.5 | Liquidity measure |
| ema_bias | Decimal | [0, 1] | 0.5 | EMA trend bias |
| volume_spike | Decimal | [0, 1] | 0 | Volume anomaly |
| volatility_state | Decimal | [0, 1] | 0 | Volatility measure |
| depth_imbalance | Decimal | [0, 1] | 0.5 | Book depth skew |
| macro_sync | Decimal | [0, 1] | 0.5 | BTC/ETH correlation |
| macro_resid | Decimal | ℝ | 0 | Beta-adjusted residual |

**NaN Handling:**
- Features emit `None` (null) during warmup
- Downstream consumers must fail-closed on null features
- `warmup.full_ready` indicates when all features are valid

### 2.4 Example Real Payload

```json
{
  "ts": 1736332800000,
  "symbol": "BTCUSDT",
  "tf_sec": 180,
  "features": {
    "price": "50123.45",
    "obi": "0.15",
    "tfi": "-0.23",
    "delta_price": "10.5",
    "absorption": "0.0",
    "liquidity_kappa": "0.75",
    "ema_bias": "0.65",
    "volume_spike": "0.82",
    "volatility_state": "0.43",
    "depth_imbalance": "0.58",
    "macro_sync": "0.71",
    "macro_resid": "0.12",
    "volume_zscore": "1.25",
    "large_trade_imbalance": "0.34",
    "spread_bps": "5.2"
  },
  "warmup": {
    "ticks_seen": 150,
    "full_ready": true,
    "ready": {
      "obi": true,
      "tfi": true,
      "ema_bias": true,
      "volume_spike": true,
      "volatility_state": true,
      "depth_imbalance": true,
      "macro_sync": true,
      "macro_resid": true,
      "volume_zscore": true,
      "large_trade_imbalance": true,
      "spread_bps": true
    },
    "reasons": []
  },
  "price_motion": {
    "ret_10s": 0.0021,
    "ret_60s": 0.0043,
    "ret_300s": 0.0087,
    "vol_pct_10s": 0.0015,
    "vol_pct_60s": 0.0032,
    "vol_pct_300s": 0.0065,
    "pm_norm_10s": 1.4,
    "pm_norm_60s": 1.34,
    "pm_norm_300s": 1.33
  }
}
```

### 2.5 Parsing Features

**Location:** `apps/reference/domains/feature_engineering/contracts.py`

```python
from decimal import Decimal
from apps.reference.domains.feature_engineering.contracts import (
    parse_features_v1,
    validate_features_payload_v1,
)

# Parse full payload
payload = validate_features_payload_v1(event.pld)

# Extract typed features
features = parse_features_v1(payload.features)

# Access as Decimal
obi = features.obi  # Decimal('0.15')
price = features.price  # Decimal('50123.45')
```

---

## 3. PPO Model (Living Latent)

### 3.1 Existing Neural Components

**Location:** `apps/reference/domains/neocortex/living_latent/core/`

**Viability Model (Autoencoder):**
```python
class OneClassAE(nn.Module):
    def __init__(self, input_dim: int = 6, latent_dim: int = 16):
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, latent_dim)
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 32),
            nn.ReLU(),
            nn.Linear(32, input_dim)
        )
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded
```

**World Model (VAE):**
```python
class WorldModel:
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # Returns (recon, latent_params)
        ...
```

### 3.2 PPO Architecture (Expected)

**Typical PPO Network:**
```python
class PPOPolicy(nn.Module):
    def __init__(self, input_dim: int, action_dim: int):
        self.shared = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
        )
        self.actor = nn.Linear(64, action_dim)
        self.critic = nn.Linear(64, 1)
    
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        features = self.shared(state)
        action_logits = self.actor(features)
        value = self.critic(features)
        return action_logits, value
```

**Input/Output Shapes:**
- `input_shape`: (batch_size, num_features) - typically 11-20 features
- `output_shape`: (batch_size, action_dim) - e.g., 3 actions (long/flat/short)
- `value_shape`: (batch_size, 1) - state value estimate

---

## 4. System Paths

### 4.1 Logs

**Primary Log Directory:** `logs/`

**Domain-Specific Logs:**
- `logs/domain_feature_engineering.log` - Feature calculations
- `logs/domain_decision_making.log` - Trading decisions
- `logs/domain_risk_management.log` - Risk assessments
- `logs/domain_execution_management.log` - Order execution
- `logs/domain_regime_detector.log` - Market regime
- `logs/aurora_core.log` - Core system events
- `logs/aurora_events.jsonl` - Structured event stream
- `logs/order_log_v1.jsonl` - Order lifecycle

**Feature-Specific Logs:**
- `logs/features/` - Feature calculation traces

**Mean Reversion Strategy:**
- `logs/mean_reversion/` - MR strategy logs

### 4.2 Configuration

**Primary Config Directory:** `config/aurora/`

**Key Config Files:**
- `config/aurora/domains.yaml` - Domain-specific configs
- `config/aurora/strategies.yaml` - Strategy parameters
- `config/aurora/system.yaml` - System-wide settings
- `config/aurora/trading.yaml` - Trading parameters
- `config/aurora/regime.yaml` - Market regime detection

### 4.3 WAL (Write-Ahead Log)

**WAL Directory:** `ops/wal/`

**Format:** JSONL (one JSON object per line)

**Example WAL Entry:**
```json
{"v":1,"op":"EVT","verb":"FEATURES_CALCULATED","src":"feature_engineering","dst":"any","rid":"uuid-here","ts":1736332800000,"pld":{"symbol":"BTCUSDT","features":{...}},"why":"features_calculated"}
```

### 4.4 Reports & Artifacts

**Reports Directory:** `reports/`

**Verb Registry:** `apps/reference/dictionaries/verb_registry_v1.yaml`

**Governance Dictionaries:**
- `vfoundation/dictionaries/global_v2_2_framework.yaml`
- `apps/reference/dictionaries/global_v2_2.yaml`
- `vfoundation/dictionaries/domains/domain_*.yaml`

---

## 5. Quick Start Integration

### 5.1 Subscribe to Features

```python
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.protocol import Message

class NeocortexDomain:
    def __init__(self, fsm: FSMCore):
        self.fsm = fsm
        self.fsm.listen("EVT:FEATURES_CALCULATED", self.on_features)
    
    def on_features(self, event: Message) -> None:
        symbol = event.pld["symbol"]
        features = event.pld["features"]
        warmup = event.pld.get("warmup", {})
        
        # Check readiness
        if not warmup.get("full_ready", False):
            return  # Skip during warmup
        
        # Extract features
        obi = float(features["obi"])
        tfi = float(features["tfi"])
        price = float(features["price"])
        
        # Process...
```

### 5.2 Emit Decisions

```python
def emit_trade_intent(self, symbol: str, direction: str, confidence: float):
    payload = {
        "symbol": symbol,
        "direction": direction,  # "long", "short", "flat"
        "confidence": confidence,
        "strategy_id": "neocortex",
        "reason": "ppo_policy_decision",
    }
    self.fsm.emit(
        "EVT:TRADE_INTENT_PROPOSED",
        payload=payload,
        why="neocortex_decision"
    )
```

### 5.3 Domain Config Template

```yaml
# config/aurora/domains.yaml

neocortex:
  enabled: true
  model_path: "models/neocortex/ppo_latest.pt"
  
  policy:
    input_dim: 11
    action_dim: 3
    hidden_dim: 128
  
  inference:
    batch_size: 1
    device: "cpu"
    warmup_ticks: 100
  
  risk:
    max_position_size_usd: 1000
    stop_loss_pct: 0.02
    take_profit_pct: 0.05
```

---

## 6. Validation Commands

**Test Feature Parsing:**
```bash
pytest -q tests/domains/feature_engineering/
```

**Validate Verb Registry:**
```bash
pytest -q tests/vfoundation/test_verb_registry_warn_only.py
```

**Check Dictionaries:**
```bash
python -m vfoundation.cli.vfound dict validate --report ops/reports/dict_validate.json
```

**Run Full Test Suite:**
```bash
pytest -q tests/vfoundation/
```

---

## Appendix: Feature Engineering Flow

```
EVT:MARKET_TICK_RECEIVED
         ↓
  FeatureEngineering.on_market_tick()
         ↓
  Calculate 11+ features
         ↓
  Build warmup state
         ↓
  Emit EVT:FEATURES_CALCULATED
         ↓
  [RiskManagement, DecisionMaking, Neocortex, ...]
```

**Event Chain:**
1. `EVT:MARKET_TICK_RECEIVED` → FeatureEngineering
2. `EVT:FEATURES_CALCULATED` → RiskManagement + DecisionMaking + Neocortex
3. `EVT:RISK_ASSESSMENT_COMPLETED` → DecisionMaking
4. `EVT:TRADE_INTENT_PROPOSED` → ExecutionManagement
5. `CMD:PLACE_ORDER` → BinanceAdapter
6. `EVT:ORDER_PLACED` → Portfolio tracking

---

**Document Version:** 1.0  
**Generated:** 2026-01-08  
**Source:** Aurora/vFoundation codebase scan  
