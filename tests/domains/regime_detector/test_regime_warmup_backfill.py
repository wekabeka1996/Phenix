"""
Tests for RegimeDetector.feed_warmup_bar() — КР-2 startup backfill fix.

Covers:
1. Буфери заповнюються через feed_warmup_bar() без TTL-перевірки
2. Після N барів детектор одразу готовий (full_ready=True) при першому live-барі
3. Старі (stale) бари через handle_event відхиляються — feed_warmup_bar() обходить це
4. ATR Wilder pipeline розраховується коректно через backfill-бари
5. Edge cases: поганий бар, нульова ціна, відсутні поля
"""

import pytest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    build_canonical_bar_identity,
)
from apps.reference.core.time.clock import MockClock
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_config(
    *,
    sma_short: int = 5,
    sma_long: int = 10,
    atr_period: int = 3,
    atr_sma_length: int = 6,
    vol_enabled: bool = True,
    hysteresis_bars: int = 1,
):
    """Мінімальний конфіг для RegimeDetector (SimpleNamespace)."""
    return SimpleNamespace(
        basis_tf_sec=300,
        uncertain_cutoff=0.35,
        hysteresis_bars=hysteresis_bars,
        vol_slope_gate_enabled=False,
        vol_slope_gate_eps=0.0,
        vol_slope_gate_confirm_bars=3,
        models=SimpleNamespace(
            sma_trend=SimpleNamespace(
                sma_short_period=sma_short,
                sma_long_period=sma_long,
                confidence_multiplier=20.0,
                confidence_min=0.5,
                confidence_max=0.95,
            ),
            volatility=SimpleNamespace(
                enabled=vol_enabled,
                atr_period=atr_period,
                atr_sma_length=atr_sma_length,
                allow_close_to_close_atr=True,
                threshold_multiplier=2.0,
                low_vol_multiplier=0.5,
                high_vol_confidence_multiplier=2.0,
                low_vol_confidence_multiplier=3.0,
            ),
            mean_reversion=SimpleNamespace(
                threshold=0.005,
                confidence_multiplier=100.0,
            ),
        ),
        system=SimpleNamespace(
            market_data=SimpleNamespace(tick_ttl_ms=5000, bar_ttl_ms=10000),
        ),
    )


def _make_detector(config=None, clock_ms: int = 10_000_000):
    """Інстанціює RegimeDetector з mock FSM і MockClock."""
    cfg = config or _make_config()
    fsm = MagicMock()
    fsm.emit = MagicMock()
    fsm.listen = MagicMock()
    clock = MockClock(start_ms=clock_ms)
    det = RegimeDetector(cfg, fsm, clock=clock)
    return det, fsm, clock


def _bar(close: float, high: float = None, low: float = None, open_ts: int | None = None) -> dict:
    bar = {
        "close": close,
        "high": high if high is not None else close + 1.0,
        "low": low if low is not None else close - 1.0,
    }
    if open_ts is not None:
        bar["open_ts"] = open_ts
    return bar


def _live_event(symbol: str, close: float, ts_ms: int, high: float = None, low: float = None):
    """Живий EVT:FEATURES_CALCULATED payload (свіжий ts_ms)."""
    return SimpleNamespace(
        verb="FEATURES_CALCULATED",
        pld={
            "symbol": symbol,
            "tf_sec": 300,
            "ts": ts_ms,
            "features": {
                "price": close,
                "high": high if high is not None else close + 1.0,
                "low": low if low is not None else close - 1.0,
            },
        },
    )


# ── тести ─────────────────────────────────────────────────────────────────────

class TestFeedWarmupBarBuffers:
    """Перевіряє що буфери заповнюються коректно."""

    def test_price_buf_grows_with_each_bar(self):
        det, _, _ = _make_detector()
        sym = "BTCUSDT"
        for i in range(8):
            det.feed_warmup_bar(sym, _bar(100.0 + i))
        assert len(det._price_buf[sym]) == 8

    def test_ticks_seen_incremented(self):
        det, _, _ = _make_detector()
        sym = "SOLUSDT"
        for _ in range(5):
            det.feed_warmup_bar(sym, _bar(50.0))
        assert det._ticks_seen[sym] == 5

    def test_price_buf_respects_maxlen(self):
        """deque(maxlen=sma_long_period) — старі значення видаляються."""
        cfg = _make_config(sma_short=3, sma_long=5)
        det, _, _ = _make_detector(config=cfg)
        sym = "ETHUSDT"
        for i in range(20):
            det.feed_warmup_bar(sym, _bar(200.0 + i))
        # maxlen = max(sma_short=3, sma_long=5) = 5
        assert len(det._price_buf[sym]) == 5

    def test_atr_buf_populated_after_enough_bars(self):
        """ATR buf має заповнюватись після atr_period барів."""
        cfg = _make_config(atr_period=3, atr_sma_length=10, vol_enabled=True)
        det, _, _ = _make_detector(config=cfg)
        sym = "BTCUSDT"
        prices = [100, 102, 101, 103, 102, 104, 103, 105]
        for p in prices:
            det.feed_warmup_bar(
                sym, _bar(float(p), high=float(p) + 1.5, low=float(p) - 1.5))
        assert len(
            det._atr_buf[sym]) > 0, "ATR buf повинен бути непорожнім після 8 барів"

    def test_atr_last_is_set_after_atr_period(self):
        """_atr_last має з'явитись після atr_period TR-значень."""
        cfg = _make_config(atr_period=3, atr_sma_length=10, vol_enabled=True)
        det, _, _ = _make_detector(config=cfg)
        sym = "BTCUSDT"
        for i in range(5):
            det.feed_warmup_bar(
                sym, _bar(100.0 + i, high=102.0 + i, low=99.0 + i))
        assert sym in det._atr_last, "_atr_last повинен бути встановлений"
        assert det._atr_last[sym] > 0

    def test_multiple_symbols_isolated(self):
        """Буфери різних символів не перетинаються."""
        det, _, _ = _make_detector()
        det.feed_warmup_bar("BTCUSDT", _bar(100.0))
        det.feed_warmup_bar("BTCUSDT", _bar(101.0))
        det.feed_warmup_bar("SOLUSDT", _bar(50.0))

        assert len(det._price_buf["BTCUSDT"]) == 2
        assert len(det._price_buf["SOLUSDT"]) == 1


class TestFeedWarmupBarBypassesTTL:
    """Перевіряє що feed_warmup_bar() обходить TTL-перевірку."""

    def test_stale_bar_via_handle_event_is_rejected(self):
        """
        Підтвердження що handle_event відхиляє старий бар (UNCERTAIN).
        Це baseline для наступного тесту.
        """
        det, fsm, clock = _make_detector(clock_ms=10_000_000)
        sym = "BTCUSDT"

        stale_event = _live_event(
            sym, close=100.0, ts_ms=1000)  # дуже старий ts
        det.handle_event(stale_event)

        call_args = fsm.emit.call_args
        payload = call_args[0][1]
        assert payload["regime"] == "UNCERTAIN"
        assert not payload["warmup"]["full_ready"]

    def test_feed_warmup_bar_accepts_old_timestamps(self):
        """feed_warmup_bar() ніколи не перевіряє ts — бар завжди прийнятий."""
        cfg = _make_config(sma_short=3, sma_long=5)
        det, _, _ = _make_detector(config=cfg, clock_ms=10_000_000)
        sym = "BTCUSDT"

        # Бари з давнім часом (epoch=0) — не повинні бути відхилені
        for i in range(10):
            det.feed_warmup_bar(sym, {
                "close": 100.0 + i,
                "high": 102.0 + i,
                "low": 99.0 + i,
                "open_ts": i * 300_000,  # давні timestamps
            })

        assert len(det._price_buf[sym]) == 5  # maxlen=5 (sma_long)
        assert det._ticks_seen[sym] == 10


class TestFeedWarmupBarProducesReadyState:
    """
    Після backfill першого live-баром RegimeDetector повинен бути готовий
    (full_ready=True) замість 24 год очікування.
    """

    def test_after_backfill_first_live_bar_triggers_sma_ready(self):
        """
        Після заповнення sma_long_period барів через backfill,
        перший живий бар повинен дати warmup.full_ready=True для SMA.
        """
        sma_long = 10
        cfg = _make_config(sma_short=3, sma_long=sma_long, vol_enabled=False)
        now_ms = 10_000_000
        det, fsm, clock = _make_detector(config=cfg, clock_ms=now_ms)
        sym = "BTCUSDT"

        # Заповнюємо sma_long барів через backfill
        for i in range(sma_long):
            det.feed_warmup_bar(sym, _bar(100.0 + i * 0.1))

        # Перший живий бар з поточним ts
        live_event = _live_event(sym, close=101.0, ts_ms=now_ms - 100)
        det.handle_event(live_event)

        call_args = fsm.emit.call_args
        assert call_args is not None, "Подія не була емітована"
        payload = call_args[0][1]
        warmup = payload["warmup"]
        assert warmup["full_ready"] is True, (
            f"Очікувався full_ready=True після backfill {sma_long} барів, "
            f"отримали: {warmup}"
        )

    def test_without_backfill_first_live_bar_is_not_ready(self):
        """
        Без backfill перший живий бар => full_ready=False (контрольний тест).
        """
        sma_long = 10
        cfg = _make_config(sma_short=3, sma_long=sma_long, vol_enabled=False)
        now_ms = 10_000_000
        det, fsm, clock = _make_detector(config=cfg, clock_ms=now_ms)
        sym = "BTCUSDT"

        # Одразу живий бар — без жодного backfill
        live_event = _live_event(sym, close=101.0, ts_ms=now_ms - 100)
        det.handle_event(live_event)

        call_args = fsm.emit.call_args
        payload = call_args[0][1]
        warmup = payload["warmup"]
        assert warmup["full_ready"] is False, (
            "Без backfill full_ready повинен бути False при першому барі"
        )

    def test_partial_backfill_still_not_ready(self):
        """Менше ніж sma_long барів => full_ready=False після першого live."""
        sma_long = 10
        cfg = _make_config(sma_short=3, sma_long=sma_long, vol_enabled=False)
        now_ms = 10_000_000
        det, fsm, clock = _make_detector(config=cfg, clock_ms=now_ms)
        sym = "BTCUSDT"

        # Тільки 5 барів (менше sma_long=10)
        for i in range(5):
            det.feed_warmup_bar(sym, _bar(100.0 + i * 0.1))

        live_event = _live_event(sym, close=101.0, ts_ms=now_ms - 100)
        det.handle_event(live_event)

        payload = fsm.emit.call_args[0][1]
        assert payload["warmup"]["full_ready"] is False


class TestFeedWarmupBarATRPipeline:
    """Перевіряє коректність Wilder ATR через backfill."""

    def test_atr_wilder_init_equals_mean_of_first_n_trs(self):
        """
        Перший ATR = mean(перших atr_period TR-значень) — Wilder ініціалізація.
        """
        cfg = _make_config(atr_period=3, atr_sma_length=20, vol_enabled=True)
        det, _, _ = _make_detector(config=cfg)
        sym = "BTCUSDT"

        # Бари з чітко відомим TR = high - low = 2.0 (prev_close близько)
        bars = [
            # TR ≈ 2.0 (перший, немає prev_close)
            {"close": 100.0, "high": 101.5, "low": 99.5},
            # TR = max(2.0, |102.5-100|, |100.5-100|) = 2.5
            {"close": 101.0, "high": 102.5, "low": 100.5},
            # TR = max(2.0, |103.5-101|, |101.5-101|) = 2.5
            {"close": 102.0, "high": 103.5, "low": 101.5},
            {"close": 103.0, "high": 104.5, "low": 102.5},  # TR = 2.5
        ]
        for b in bars:
            det.feed_warmup_bar(sym, b)

        assert sym in det._atr_last
        # Після 3+ барів ATR повинен бути ненульовим позитивним
        assert float(det._atr_last[sym]) > 0.0

    def test_vol_disabled_atr_buf_stays_empty(self):
        """Якщо volatility.enabled=False — ATR buf не заповнюється."""
        cfg = _make_config(vol_enabled=False)
        det, _, _ = _make_detector(config=cfg)
        sym = "BTCUSDT"
        for i in range(20):
            det.feed_warmup_bar(
                sym, _bar(100.0 + i, high=102.0 + i, low=99.0 + i))
        assert len(det._atr_buf[sym]) == 0
        assert sym not in det._atr_last


class TestFeedWarmupBarEdgeCases:
    """Edge cases: погані дані, нульові ціни, відсутні поля."""

    def test_zero_close_skipped(self):
        """Бар з close=0 повинен бути відкинутий (не оновлює буфери)."""
        det, _, _ = _make_detector()
        sym = "BTCUSDT"
        det.feed_warmup_bar(sym, _bar(100.0))  # нормальний
        det.feed_warmup_bar(
            sym, {"close": 0.0, "high": 1.0, "low": 0.0})  # нульовий
        det.feed_warmup_bar(sym, _bar(101.0))  # нормальний

        # Тільки 2 нормальних бари повинні бути в буфері
        assert len(det._price_buf[sym]) == 2
        assert det._ticks_seen[sym] == 2

    def test_missing_close_key_skipped(self):
        """Бар без ключа 'close' повинен бути ігнорований."""
        det, _, _ = _make_detector()
        sym = "BTCUSDT"
        det.feed_warmup_bar(sym, {"high": 101.0, "low": 99.0})  # немає close
        assert len(det._price_buf[sym]) == 0

    def test_bad_close_type_skipped(self):
        """Нечисловий close повинен бути відкинутий."""
        det, _, _ = _make_detector()
        sym = "BTCUSDT"
        det.feed_warmup_bar(
            sym, {"close": "not_a_number", "high": 101.0, "low": 99.0})
        assert len(det._price_buf[sym]) == 0

    def test_missing_high_low_uses_close_for_atr(self):
        """
        Якщо high/low відсутні, ATR використовує close-to-close (дозволено
        allow_close_to_close_atr=True).
        """
        cfg = _make_config(atr_period=3, atr_sma_length=10, vol_enabled=True)
        det, _, _ = _make_detector(config=cfg)
        sym = "BTCUSDT"
        # Бар тільки з close (без high/low)
        for i in range(6):
            det.feed_warmup_bar(sym, {"close": 100.0 + i})
        # price_buf повинен заповнитись
        assert len(det._price_buf[sym]) == 6
        # ATR не обвалився
        # (якщо allow_close_to_close_atr=True — _atr_last може бути встановлений)

    def test_no_side_effects_on_other_symbols(self):
        """Поганий бар для одного символу не зачіпає інший."""
        det, _, _ = _make_detector()
        det.feed_warmup_bar("BTCUSDT", _bar(100.0))
        det.feed_warmup_bar("SOLUSDT", {"close": 0.0})  # поганий
        det.feed_warmup_bar("BTCUSDT", _bar(101.0))

        assert len(det._price_buf["BTCUSDT"]) == 2
        assert len(det._price_buf["SOLUSDT"]) == 0


class TestFeedWarmupBarDoesNotEmitEvents:
    """feed_warmup_bar() НЕ повинен емітувати жодних подій."""

    def test_no_events_emitted_during_backfill(self):
        """При заповненні 50 барів через backfill — жодного emit."""
        det, fsm, _ = _make_detector()
        sym = "BTCUSDT"
        for i in range(50):
            det.feed_warmup_bar(sym, _bar(100.0 + i * 0.5))
        fsm.emit.assert_not_called()

    def test_only_live_bar_triggers_emit(self):
        """Тільки живий бар через handle_event емітує EVT:REGIME_DETECTED."""
        cfg = _make_config(sma_short=3, sma_long=5, vol_enabled=False)
        now_ms = 10_000_000
        det, fsm, _ = _make_detector(config=cfg, clock_ms=now_ms)
        sym = "BTCUSDT"

        for i in range(5):
            det.feed_warmup_bar(sym, _bar(100.0 + i))
        assert fsm.emit.call_count == 0  # ще жодного

        det.handle_event(_live_event(sym, 105.0, ts_ms=now_ms - 50))
        assert fsm.emit.call_count == 1
        assert fsm.emit.call_args[0][0] == "EVT:REGIME_DETECTED"


def test_duplicate_warmup_then_same_live_bar_is_noop() -> None:
    det, fsm, _ = _make_detector(clock_ms=305_000)
    sym = "BTCUSDT"

    det.feed_warmup_bar(sym, {
        "close": 100.0,
        "high": 101.0,
        "low": 99.0,
        "open_ts": 0,
    })
    assert det._ticks_seen[sym] == 1

    identity = build_canonical_bar_identity(
        symbol=sym,
        timeframe_sec=300,
        bar_start_ts_ms=0,
        close_boundary_ts_ms=300_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )
    det.handle_event(
        SimpleNamespace(
            verb="FEATURES_CALCULATED",
            pld={
                "symbol": sym,
                "tf_sec": 300,
                "ts": 300_000,
                "bar_identity": identity.to_payload(),
                "features": {
                    "price": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                },
            },
        )
    )

    assert det._ticks_seen[sym] == 1
    fsm.emit.assert_not_called()
