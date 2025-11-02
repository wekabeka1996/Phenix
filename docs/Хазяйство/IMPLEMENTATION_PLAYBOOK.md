# 🛠️ IMPLEMENTATION PLAYBOOK: From Current State to Production + Alpha Search

**Дата**: 2 листопада 2025
**Цільова дата**: 16 листопада (2 тижні для P0)
**Мета**: Робочий production + alpha discovery pipeline

---

## 📋 ФАЗИ РЕАЛІЗАЦІЇ

### ФАЗА 1: PRODUCTION STABILIZATION (5-6 днів)

Цель: Зупинити критичні баги, підготувати до живого торгування.

#### 1.1 RID Garbage Collection (День 1)

**Файли для створення**:
- `vfoundation/dr/wal_gc.py` (new)
- `vfoundation/dr/wal_rotator.py` (new)

**Реалізація**:
```python
# vfoundation/dr/wal_gc.py
from pathlib import Path
import time
from threading import Thread, Event
import logging

class WALGarbageCollector:
    """
    Manages WAL file lifecycle: rotation, cleanup, archival.
    Runs as background daemon thread.
    """

    def __init__(
        self,
        wal_dir: Path,
        retention_days: int = 7,
        max_file_size_mb: int = 100,
        logger: logging.Logger = None
    ):
        self.wal_dir = Path(wal_dir)
        self.retention_days = retention_days
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.logger = logger or logging.getLogger(__name__)
        self._stop_event = Event()

    def start_background_gc(self, interval_sec: int = 3600) -> Thread:
        """Start GC thread (runs every 1 hour by default)."""
        thread = Thread(
            target=self._gc_loop,
            args=(interval_sec,),
            daemon=True,
            name="WAL-GC"
        )
        thread.start()
        return thread

    def _gc_loop(self, interval_sec: int):
        """Background GC loop."""
        while not self._stop_event.is_set():
            try:
                self.cleanup_old_wals()
                self.rotate_current_wal()
            except Exception as e:
                self.logger.error(f"GC error: {e}")

            self._stop_event.wait(interval_sec)

    def cleanup_old_wals(self) -> int:
        """Remove WAL files older than retention_days."""
        cutoff_ts = time.time() - (self.retention_days * 86400)
        removed = 0

        for wal_file in self.wal_dir.glob("wal_*.jsonl"):
            # Skip current WAL
            if wal_file.name == "wal_current.jsonl":
                continue

            file_mtime = wal_file.stat().st_mtime
            if file_mtime < cutoff_ts:
                try:
                    # Archive to S3/cloud (optional)
                    # self._archive_to_s3(wal_file)
                    wal_file.unlink()
                    removed += 1
                    self.logger.info(f"GC: Removed WAL {wal_file.name}")
                except Exception as e:
                    self.logger.error(f"Failed to remove {wal_file}: {e}")

        return removed

    def rotate_current_wal(self) -> bool:
        """Rotate WAL file when size exceeds max."""
        current_wal = self.wal_dir / "wal_current.jsonl"
        if not current_wal.exists():
            return False

        file_size = current_wal.stat().st_size
        if file_size > self.max_file_size_bytes:
            try:
                ts = int(time.time())
                new_name = self.wal_dir / f"wal_{ts}.jsonl"
                current_wal.rename(new_name)
                self.logger.info(f"GC: Rotated WAL (size was {file_size} bytes)")
                return True
            except Exception as e:
                self.logger.error(f"Failed to rotate WAL: {e}")

        return False

    def stop(self):
        """Stop background GC."""
        self._stop_event.set()

    def get_stats(self) -> dict:
        """Return WAL directory stats."""
        total_size = sum(f.stat().st_size for f in self.wal_dir.glob("wal_*.jsonl"))
        file_count = len(list(self.wal_dir.glob("wal_*.jsonl")))
        return {
            'total_size_mb': total_size / (1024 * 1024),
            'file_count': file_count,
        }
```

**Інтеграція в main.py**:
```python
# apps/reference/main.py
from vfoundation.dr.wal_gc import WALGarbageCollector

# In __main__:
wal_dir = Path("ops/wal")
gc = WALGarbageCollector(wal_dir, retention_days=7, max_file_size_mb=100)
gc_thread = gc.start_background_gc(interval_sec=3600)

# On shutdown:
gc.stop()
gc_thread.join(timeout=5)
```

**Тестування**:
```python
# tests/test_wal_gc.py
def test_cleanup_old_wals(tmp_path):
    """Verify GC removes old WAL files."""
    # Create 2 WAL files: one old, one fresh
    old_wal = tmp_path / "wal_1000000.jsonl"
    old_wal.write_text("{}")
    (old_wal.stat().st_mtime - 8 * 86400)  # 8 days old

    fresh_wal = tmp_path / "wal_current.jsonl"
    fresh_wal.write_text("{}")

    gc = WALGarbageCollector(tmp_path, retention_days=7)
    removed = gc.cleanup_old_wals()

    assert removed == 1
    assert old_wal not in tmp_path.glob("*.jsonl")
    assert fresh_wal.exists()
```

**Effort**: 4-6 часов
**Impact**: ✅ Prevents OOM, enables 24/7 trading

---

#### 1.2 Fix Dynamic Risk Scoring (День 1)

**Файл для редагування**: `apps/reference/domains/risk_management/risk_management.py`

**Поточна проблема** (лінії ~150-160):
```python
# BROKEN: always returns 0.85
risk_score = Decimal(decision_config.get('base_risk_score', '0.85'))
```

**Вирішення**:
```python
def _calculate_dynamic_risk_score(self) -> Decimal:
    """
    Risk score dynamically adjusted based on:
    1. Portfolio leverage (leverage_ratio: 0.0 - 1.0)
    2. Market regime volatility
    3. Position correlation
    4. Recent drawdown

    Formula: 0.3 + (leverage_ratio * 0.4) + (volatility_factor * 0.2) + (drawdown_recovery * 0.1)
    """

    # 1. LEVERAGE RATIO
    current_notional = sum(
        abs(pos['size'] * pos['entry_price'])
        for pos in self.positions.values()
    )
    max_notional = self.portfolio['equity_usd'] * Decimal('5.0')  # 5x max leverage
    leverage_ratio = min(current_notional / max_notional, Decimal('1.0')) if max_notional > 0 else Decimal('0.0')

    # 2. VOLATILITY FACTOR
    volatility_factor = Decimal('1.0')
    if self.latest_regime:
        regime = self.latest_regime.get('regime', 'UNCERTAIN')
        confidence = Decimal(self.latest_regime.get('confidence', '0.5'))

        if regime == 'HIGH_VOLATILITY':
            volatility_factor = Decimal('1.3')  # +30% risk in high vol
        elif regime == 'MEAN_REVERSION':
            volatility_factor = Decimal('0.8')  # -20% risk in ranging market
        elif regime == 'TREND_UP' or regime == 'TREND_DOWN':
            volatility_factor = Decimal('1.0')  # Neutral in trend

    # 3. CORRELATION FACTOR (simplified: use number of positions)
    correlation_factor = Decimal('1.0')
    position_count = len([p for p in self.positions.values() if p['size'] != 0])
    if position_count >= 3:
        correlation_factor = Decimal('0.9')  # -10% risk if diversified

    # 4. DRAWDOWN RECOVERY
    drawdown_recovery = Decimal('1.0')
    if 'max_drawdown_pct' in self.portfolio:
        current_dd = self.portfolio.get('current_drawdown_pct', Decimal('0'))
        max_dd = self.portfolio.get('max_drawdown_pct', Decimal('1.0'))
        if max_dd > 0:
            recovery_ratio = current_dd / max_dd
            drawdown_recovery = Decimal('1.0') - (recovery_ratio * Decimal('0.2'))  # Max -20%

    # AGGREGATE
    risk_score = (
        Decimal('0.3')  # Base
        + (leverage_ratio * Decimal('0.4'))
        + (volatility_factor * Decimal('0.2'))
        + (drawdown_recovery * Decimal('0.1'))
    )

    # Clamp to [0.1, 0.95]
    risk_score = max(Decimal('0.1'), min(risk_score, Decimal('0.95')))

    self.logger.debug(
        f"Risk score calculated: {risk_score} "
        f"(leverage={leverage_ratio}, volatility={volatility_factor}, "
        f"correlation={correlation_factor}, drawdown_recovery={drawdown_recovery})"
    )

    return risk_score
```

**Тестування**:
```python
# tests/domains/test_risk_manager_dynamic_scoring.py
def test_risk_score_varies_with_leverage():
    """Risk score should increase with leverage."""
    rm = RiskManager(config=mock_config, fsm=mock_fsm)
    rm.portfolio = {'equity_usd': Decimal('10000')}

    # No positions
    rm.positions = {}
    score_no_pos = rm._calculate_dynamic_risk_score()

    # One position (30% leverage)
    rm.positions = {'BTC': {'size': Decimal('1'), 'entry_price': Decimal('30000')}}
    score_with_pos = rm._calculate_dynamic_risk_score()

    assert score_with_pos > score_no_pos

def test_risk_score_increases_in_high_volatility():
    """Risk score should increase in HIGH_VOLATILITY regime."""
    rm = RiskManager(config=mock_config, fsm=mock_fsm)
    rm.portfolio = {'equity_usd': Decimal('10000')}
    rm.positions = {}

    # Normal regime
    rm.latest_regime = {'regime': 'UNCERTAIN', 'confidence': '0.5'}
    score_normal = rm._calculate_dynamic_risk_score()

    # High volatility
    rm.latest_regime = {'regime': 'HIGH_VOLATILITY', 'confidence': '0.9'}
    score_high_vol = rm._calculate_dynamic_risk_score()

    assert score_high_vol > score_normal
```

**Effort**: 2-3 часа
**Impact**: ✅ Risk manager starts working, risk_score varies with market conditions

---

#### 1.3 Setup Alerts & Monitoring (День 2-3)

**Файли для створення**:
- `apps/reference/telemetry/alerts.py` (new)
- `apps/reference/telemetry/monitoring.py` (new)

**Реалізація alerts**:
```python
# apps/reference/telemetry/alerts.py
import asyncio
from enum import Enum
from typing import Callable, List
from pydantic import BaseModel

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class Alert(BaseModel):
    level: AlertLevel
    title: str
    body: str
    timestamp: int

    def format_slack(self) -> str:
        """Format alert for Slack message."""
        emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
        }[self.level]

        return f"{emoji} {self.title}\n{self.body}"

class AlertManager:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.handlers: List[Callable] = []
        self._setup_handlers()

    def _setup_handlers(self):
        """Register alert handlers (Slack, email, etc.)."""
        if self.config.get('slack_webhook'):
            self.handlers.append(self._send_to_slack)
        if self.config.get('pagerduty_key'):
            self.handlers.append(self._send_to_pagerduty)

    async def emit(self, alert: Alert) -> None:
        """Broadcast alert to all handlers."""
        tasks = [handler(alert) for handler in self.handlers]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_to_slack(self, alert: Alert) -> None:
        """Send alert to Slack."""
        import aiohttp

        webhook = self.config.get('slack_webhook')
        payload = {
            'text': alert.format_slack(),
            'attachments': [{
                'color': {
                    AlertLevel.INFO: '#36a64f',
                    AlertLevel.WARNING: '#ff9900',
                    AlertLevel.CRITICAL: '#ff0000',
                }[alert.level],
                'title': alert.title,
                'text': alert.body,
            }]
        }

        async with aiohttp.ClientSession() as session:
            try:
                await session.post(webhook, json=payload, timeout=5)
            except Exception as e:
                print(f"Failed to send Slack alert: {e}")

    async def _send_to_pagerduty(self, alert: Alert) -> None:
        """Send critical alerts to PagerDuty."""
        if alert.level != AlertLevel.CRITICAL:
            return

        import aiohttp

        pd_key = self.config.get('pagerduty_key')
        payload = {
            'routing_key': pd_key,
            'event_action': 'trigger',
            'payload': {
                'summary': alert.title,
                'severity': 'critical',
                'source': 'phenix-trading',
                'custom_details': {'body': alert.body},
            }
        }

        async with aiohttp.ClientSession() as session:
            try:
                await session.post(
                    'https://events.pagerduty.com/v2/enqueue',
                    json=payload,
                    timeout=5
                )
            except Exception as e:
                print(f"Failed to send PagerDuty alert: {e}")

# Alert triggers (in respective domains)
class TradingAlerts:
    def __init__(self, alert_manager: AlertManager):
        self.alert_manager = alert_manager

    async def alert_risk_gate_blocking(self, blocked_count: int, total_count: int) -> None:
        """Alert if risk manager blocks >80% of trades."""
        block_rate = blocked_count / total_count if total_count > 0 else 0
        if block_rate > 0.8:
            await self.alert_manager.emit(Alert(
                level=AlertLevel.CRITICAL,
                title="Risk gate blocking 80%+ trades",
                body=f"Risk manager rejected {blocked_count}/{total_count} intents. "
                     f"Check risk configuration.",
                timestamp=int(time.time())
            ))

    async def alert_circuit_breaker_active(self, domain: str, reason: str) -> None:
        """Alert when circuit breaker activates."""
        await self.alert_manager.emit(Alert(
            level=AlertLevel.CRITICAL,
            title=f"Circuit breaker active: {domain}",
            body=f"Domain exceeded error threshold. Reason: {reason}",
            timestamp=int(time.time())
        ))

    async def alert_high_leverage(self, leverage: Decimal, threshold: Decimal) -> None:
        """Alert when leverage exceeds safe threshold."""
        if leverage > threshold:
            await self.alert_manager.emit(Alert(
                level=AlertLevel.WARNING,
                title=f"High leverage: {float(leverage):.2f}x",
                body=f"Portfolio leverage exceeded {float(threshold):.2f}x threshold.",
                timestamp=int(time.time())
            ))

    async def alert_wal_size(self, size_mb: float) -> None:
        """Alert when WAL files grow too large."""
        if size_mb > 500:  # 500 MB threshold
            await self.alert_manager.emit(Alert(
                level=AlertLevel.WARNING,
                title=f"WAL directory large: {size_mb:.1f} MB",
                body=f"Consider running GC manually or increasing retention.",
                timestamp=int(time.time())
            ))
```

**Інтеграція в main.py**:
```python
# apps/reference/main.py
from apps.reference.telemetry.alerts import AlertManager, TradingAlerts

# Initialize
alert_manager = AlertManager(config={
    'slack_webhook': os.getenv('SLACK_WEBHOOK'),
    'pagerduty_key': os.getenv('PAGERDUTY_KEY'),
})
trading_alerts = TradingAlerts(alert_manager)

# In RiskManagement.handle_event():
if approval_count == 0 and len(intents) > 10:
    asyncio.create_task(trading_alerts.alert_risk_gate_blocking(len(intents), len(intents)))
```

**Effort**: 3-4 часа
**Impact**: ✅ Operations can see critical issues immediately

---

### ФАЗА 2: ORCHESTRATION (День 4-6)

#### 2.1 Implement OrchestratorFSM

**Файли для створення**:
- `apps/reference/orchestrator/orchestrator_fsm.py` (new, ~400 строк)
- `apps/reference/orchestrator/__init__.py` (new)
- `tests/test_orchestrator_fsm.py` (new, ~200 строк)

**Ключові методи**:
- `on_trade_intent()` - EVAL фаза
- `on_order_executed()` - OPEN фаза
- `on_position_closed()` - CLOSE фаза
- `get_rid_trace()` - debug endpoint
- `cleanup_expired_rids()` - GC

**Effort**: 8-10 часов
**Impact**: ✅ Centralized RID coordination, WHY chain preservation, signing

---

### ФАЗА 3: ALPHA DISCOVERY PIPELINE (День 7-15)

#### 3.1 AlphaModel Framework (День 7-8)

**Файли для створення**:
- `apps/reference/domains/alpha_search/__init__.py` (new)
- `apps/reference/domains/alpha_search/alpha_model.py` (new, abstract base)
- `apps/reference/domains/alpha_search/models/momentum.py` (new)
- `apps/reference/domains/alpha_search/models/mean_reversion.py` (new)
- `apps/reference/domains/alpha_search/models/volatility.py` (new)

**Інтеграція**:
- Emit EVT:ALPHA_SCORE_CALCULATED на кожен signal
- Aggregator в DecisionMaking збирає scores від всіх моделей

#### 3.2 Multi-Strategy Backtester (День 9-10)

**Файли для створення**:
- `apps/reference/alpha_discovery/backtest_engine.py` (new)
- `apps/reference/data/feature_store.py` (new)

**Функціональність**:
- Завантажити історичні OHLCV
- Розрахувати features
- Прогнати кожен AlphaModel
- Вивести метрики: Sharpe, max DD, win rate

#### 3.3 Feature Store (День 11)

**Файли для створення**:
- `apps/reference/data/feature_store.py`
- Deployment на DuckDB або Parquet

**Retention**: 6 місяців історії (для backtesting)

---

## 🗓️ GANTT CHART

```
День 1: RID GC + Risk Score Fix
День 2: Alert Manager setup
День 3: Integration & testing P0
День 4-6: OrchestratorFSM (3 days)
День 7-8: AlphaModel Framework
День 9-10: Backtester
День 11: Feature Store
День 12-14: Research (test 20+ models)
День 15: Documentation + deployment
```

---

## ✅ SUCCESS CRITERIA

**После P0 (День 6)**:
- ✅ RID GC working (WAL cleanup every 1 hour)
- ✅ Risk score varies (0.1-0.95 based on leverage + regime)
- ✅ Alerts configured (Slack/PagerDuty integration)
- ✅ OrchestratorFSM deployed (RID tracking via `/debug/{rid}`)
- ✅ Test suite passes (800+ tests still passing)

**После P1 (День 15)**:
- ✅ Backtester runs 20+ alpha models
- ✅ Feature store persists historical data
- ✅ Top 5 models identified by Sharpe ratio
- ✅ Ensemble weights optimized
- ✅ Ready for live paper trading

**После P2 (День 30)**:
- ✅ Multi-timeframe filters reduce false signals
- ✅ ML-based regime detection deployed
- ✅ Dashboard live with real-time P&L
- ✅ Monitoring 24/7 (alerts + error recovery)

---

## 💡 TIPS FOR EXECUTION

1. **Test-driven**: Write tests first, then implement
2. **Incremental**: Deploy P0 items one-by-one, verify each
3. **Monitor**: Watch metrics for regressions
4. **Document**: Update README.md + DEPLOYMENT.md as you go
5. **Commit frequently**: Small commits, clear messages

**Версія**: 1.0 | **Статус**: READY FOR EXECUTION
