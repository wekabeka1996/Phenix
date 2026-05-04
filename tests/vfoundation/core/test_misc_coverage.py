"""Coverage tests for retry_cb, base adapters, wal_archiver, perf_benchmark, snapshot."""
import pytest
import time
from vfoundation.core.retry_cb import RetryPolicy, CircuitBreaker
from vfoundation.core.adapters.base import (
    ExchangeOrderParams, ExchangeOrderResponse, ExchangePosition
)
from vfoundation.dataref.wal_archiver import WalArchiver, ArchiveResult
from vfoundation.testing.perf_benchmark import PerfBenchmark, BenchmarkResult
from vfoundation.dr.snapshot import save, load_latest


# ── RetryPolicy ─────────────────────────────────────────────────
class TestRetryPolicyCoverage:
    def test_backoff_increases(self):
        p = RetryPolicy()
        b0 = p.backoff_ms(0)
        b3 = p.backoff_ms(3)
        assert b3 > b0

    def test_backoff_capped_at_max(self):
        p = RetryPolicy(max_ms=100)
        assert p.backoff_ms(20) <= 100


# ── CircuitBreaker ──────────────────────────────────────────────
class TestCircuitBreakerCoverage:
    def test_closed_allows(self):
        cb = CircuitBreaker(threshold=3)
        assert cb.allow() is True

    def test_open_after_threshold_failures(self):
        cb = CircuitBreaker(threshold=2, cool_down_s=10)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == "OPEN"

    def test_open_blocks_requests(self):
        cb = CircuitBreaker(threshold=1, cool_down_s=100)
        cb.on_failure()
        assert cb.allow() is False  # Line 57

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(threshold=1, cool_down_s=0)
        cb.on_failure()  # Opens CB
        time.sleep(0.01)
        assert cb.allow() is True  # Line 50: HALF_OPEN allows
        assert cb.state == "HALF_OPEN"

    def test_half_open_allows_probe(self):
        cb = CircuitBreaker(threshold=1, cool_down_s=0)
        cb.on_failure()
        time.sleep(0.01)
        cb.allow()  # Transitions to HALF_OPEN
        assert cb.allow() is True  # Line 50

    def test_success_resets_to_closed(self):
        cb = CircuitBreaker(threshold=1)
        cb.on_failure()
        cb.on_success()
        assert cb.state == "CLOSED"
        assert cb.failures == 0

    def test_default_fallback_unreachable_but_covered(self):
        # Line 58: return True — default fallback, hit if state is unexpected
        cb = CircuitBreaker(threshold=5)
        cb.state = "WEIRD"
        assert cb.allow() is True


# ── Exchange Adapter Base dataclasses ───────────────────────────
class TestBaseAdaptersCoverage:
    def test_order_params_creation(self):
        p = ExchangeOrderParams(symbol="BTC", side="BUY", order_type="MARKET", quantity="0.01")
        assert p.symbol == "BTC"
        assert p.reduce_only is False

    def test_order_response_to_dict(self):
        r = ExchangeOrderResponse(
            order_id="123", client_order_id="c1", symbol="BTC", side="BUY",
            quantity="0.01", filled_qty="0.01", price="50000", status="FILLED",
            timestamp_ms=1000
        )
        d = r.to_dict()
        assert d["orderId"] == "123"
        assert d["status"] == "FILLED"

    def test_order_response_with_reason(self):
        r = ExchangeOrderResponse(
            order_id="1", client_order_id=None, symbol="ETH", side="SELL",
            quantity="1", filled_qty="0", price=None, status="REJECTED",
            timestamp_ms=1000, reason="insufficient balance"
        )
        d = r.to_dict()
        assert d["reason"] == "insufficient balance"

    def test_position_to_dict(self):
        p = ExchangePosition(
            symbol="BTC", position_side="BOTH", side="LONG",
            position_amount="0.5", entry_price="50000", mark_price="51000",
            unrealized_profit="500", leverage=10, margin_type="CROSS",
            isolated_margin=0.0, update_time_ms=1000
        )
        d = p.to_dict()
        assert d["symbol"] == "BTC"
        assert d["positionSide"] == "BOTH"
        assert d["positionAmt"] == "0.5"
        assert d["position_amount"] == "0.5"


# ── WalArchiver ─────────────────────────────────────────────────
class TestWalArchiverCoverage:
    def test_compression_ratio_zero_bytes(self):
        r = ArchiveResult(files_archived=0, files_skipped=0,
                          total_bytes_original=0, total_bytes_compressed=0,
                          archive_dir="/tmp")
        assert r.compression_ratio == 0.0  # Line 33

    def test_archive_skips_small_files(self, tmp_path):
        wal_dir = tmp_path / "wal"
        wal_dir.mkdir()
        archive_dir = tmp_path / "archive"
        (wal_dir / "test.jsonl").write_text("tiny")
        archiver = WalArchiver(str(wal_dir), str(archive_dir), min_size_bytes=1000)
        result = archiver.archive()
        assert result.files_skipped == 1
        assert result.files_archived == 0

    def test_list_archives_no_dir(self, tmp_path):
        archiver = WalArchiver(str(tmp_path), str(tmp_path / "nonexistent"))
        assert archiver.list_archives() == []  # Line 103-104


# ── PerfBenchmark ───────────────────────────────────────────────
class TestPerfBenchmarkCoverage:
    def test_p50_p95_p99(self):
        r = BenchmarkResult(name="t", iterations=10, latencies_ms=[1,2,3,4,5,6,7,8,9,10])
        assert r.p50_ms > 0  # Line 26
        assert r.p95_ms > 0  # Line 34
        assert r.p99_ms > 0  # Line 34

    def test_throughput_rps(self):
        r = BenchmarkResult(name="t", iterations=2, latencies_ms=[100, 100])
        assert r.throughput_rps > 0  # Line 41

    def test_throughput_zero_latency(self):
        r = BenchmarkResult(name="t", iterations=0, latencies_ms=[])
        assert r.throughput_rps == 0.0  # Line 41

    def test_meets_slo(self):
        r = BenchmarkResult(name="t", iterations=3, latencies_ms=[1, 2, 3])
        assert r.meets_slo(100.0) is True  # Line 46
        assert r.meets_slo(0.001) is False

    def test_empty_latencies_percentile(self):
        r = BenchmarkResult(name="t", iterations=0, latencies_ms=[])
        assert r.p50_ms == 0.0  # Line 46

    def test_run_with_warmup(self):
        b = PerfBenchmark(name="warmup_test", warmup_rounds=2, iterations=3)
        calls = []
        result = b.run(lambda: calls.append(1))
        assert len(calls) == 5  # 2 warmup + 3 measured
        assert result.warmup_rounds == 2
        assert result.iterations == 3
        assert len(result.latencies_ms) == 3


# ── Snapshot ────────────────────────────────────────────────────
class TestSnapshotCoverage:
    def test_save_and_load(self, tmp_path, monkeypatch):
        import vfoundation.dr.snapshot as snap_mod
        monkeypatch.setattr(snap_mod, "SNAP_DIR", tmp_path / "snaps")
        path = save("test_domain", {"key": "value"})
        assert "test_domain" in path
        loaded = load_latest("test_domain")
        assert loaded is not None
        assert loaded["key"] == "value"

    def test_load_latest_no_dir(self, tmp_path, monkeypatch):
        import vfoundation.dr.snapshot as snap_mod
        monkeypatch.setattr(snap_mod, "SNAP_DIR", tmp_path / "nonexistent")
        assert load_latest("x") is None

    def test_load_latest_empty_dir(self, tmp_path, monkeypatch):
        import vfoundation.dr.snapshot as snap_mod
        d = tmp_path / "snaps" / "empty_domain"
        d.mkdir(parents=True)
        monkeypatch.setattr(snap_mod, "SNAP_DIR", tmp_path / "snaps")
        assert load_latest("empty_domain") is None  # Line 24
