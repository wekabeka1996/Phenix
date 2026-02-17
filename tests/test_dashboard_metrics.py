import unittest
from decimal import Decimal
from apps.reference.domains.decision_making.dashboard import DashboardMetrics, TradeOutcome
from apps.reference.config_models import DashboardConfig

class TestDashboardMetrics(unittest.TestCase):
    def setUp(self):
        self.config = DashboardConfig(
            enabled=True,
            sharpe_window_days=30,
            metrics=["sharpe_ratio", "win_rate"]
        )
        self.dashboard = DashboardMetrics(self.config)

    def test_win_rate_calc(self):
        """Verify Win Rate calculation."""
        # 1 Win, 1 Loss
        self.dashboard.record_trade(TradeOutcome("BTCUSDT", 100, 200, 1.0, 100, True))
        self.dashboard.record_trade(TradeOutcome("ETHUSDT", 300, 400, -0.5, 100, False))
        
        metrics = self.dashboard.get_metrics()
        self.assertEqual(metrics["win_rate"], 50.0)

    def test_sharpe_ratio_calc(self):
        """Verify Sharpe Ratio (raw) calculation."""
        # Consistent returns -> high sharpe
        # Volatile returns -> low sharpe
        
        # Test 1: Consistent +1%
        self.dashboard = DashboardMetrics(self.config)
        for _ in range(5):
             self.dashboard.record_trade(TradeOutcome("BTC", 100, 200, 1.0, 100, True))
             
        m1 = self.dashboard.get_metrics()
        # StdDev of constant series is 0 -> Avoid div/0 handled?
        # mean=1.0, stdev=0.0 -> metrics should be 0.0 per code
        self.assertEqual(m1["sharpe_ratio_raw"], 0.0) 

        # Test 2: Volatile (+2%, -1%)
        self.dashboard = DashboardMetrics(self.config)
        self.dashboard.record_trade(TradeOutcome("BTC", 100, 200, 2.0, 100, True))
        self.dashboard.record_trade(TradeOutcome("BTC", 300, 400, -1.0, 100, False))
        
        m2 = self.dashboard.get_metrics()
        # Mean = 0.5, StdDev approx 2.12
        # Sharpe ~ 0.23
        self.assertGreater(m2["sharpe_ratio_raw"], 0.0)
        self.assertLess(m2["sharpe_ratio_raw"], 1.0)
        
    def test_window_pruning(self):
        """Verify trades older than window are pruned."""
        # Window size 30 days
        now = 10000000.0
        old_ts = now - (31 * 24 * 3600) # 31 days ago
        
        self.dashboard.record_trade(TradeOutcome("OLD", old_ts-100, old_ts, 1.0, 100, True))
        self.dashboard._prune_history(now)
        
        self.assertEqual(len(self.dashboard.closed_trades), 0)
