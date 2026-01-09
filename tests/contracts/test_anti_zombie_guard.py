
import subprocess
import sys
import unittest

class TestAntiZombieGuard(unittest.TestCase):
    """
    TASK-ANTI-ZOMBIE-GUARD-02:
    Ensure that no legacy spot code (AccountObserver, python-binance in runtime) is reintroduced.
    """

    def test_no_account_observer_in_runtime_imports(self):
        """Verify that 'AccountObserver' is NOT imported or defined in apps/reference/main.py or apps/reference/domains/**."""
        # We search specifically in python files, excluding docs and tests
        cmd = [
            "rg",
            "from.*account_observer|import.*AccountObserver|class.*AccountObserver",
            "apps/reference/main.py",
            "apps/reference/domains",
            "-g", "*.py",
            "--no-heading"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # If grep finds something, it exits with 0 -> which means we FAILED the guard
        if result.returncode == 0:
            print(f"\n[ZOMBIE ALERT] Found AccountObserver references:\n{result.stdout}")
        
        self.assertNotEqual(result.returncode, 0, "Found forbidden AccountObserver code/imports in runtime!")

    def test_no_binance_client_in_runtime(self):
        """Verify that 'from binance.client import Client' is NOT present in runtime code (apps/)."""
        cmd = [
            "rg",
            "from binance\.client import Client",
            "apps/reference",
            "-g", "*.py",
            "--no-heading"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"\n[ZOMBIE ALERT] Found python-binance Client imports:\n{result.stdout}")
        
        self.assertNotEqual(result.returncode, 0, "Found forbidden 'binance.client.Client' import in runtime! Use BinanceAdapter instead.")

if __name__ == "__main__":
    unittest.main()
