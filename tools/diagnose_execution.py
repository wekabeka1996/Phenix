import sys
import os
import time
from pathlib import Path

# Setup path
sys.path.append(os.getcwd())


def test_guardian_config():
    print("\n--- TEST 1: Order Guardian Configuration Wiring ---")
    try:
        from apps.reference.domains.execution_position.order_guardian import OrderGuardian

        try:
            # Load real config (no network calls).
            cfg = None
            try:
                from apps.reference.config_loader import get_config

                cfg = get_config()
            except Exception as e:
                print(f"⚠️ Could not load config via get_config(): {e}")

            # Instantiate guardian in shadow-safe mode: no adapter calls are made.
            og = OrderGuardian(adapter=None, config=cfg, poll_interval_ms=0, bus=None)

            # Try to discover underlying ledger path (if unified + LedgerStoreAdapter).
            db_path = "UNKNOWN"
            try:
                from apps.reference.services.ledger_store_adapter import LedgerStoreAdapter

                impl = getattr(og, "_impl", None)
                store = getattr(impl, "store", None)
                if isinstance(store, LedgerStoreAdapter):
                    db_path = getattr(store.ledger, "db_path", "UNKNOWN")
                else:
                    db_path = type(store).__name__ if store is not None else ":memory:"
            except Exception as e:
                print(f"⚠️ Could not inspect underlying store/ledger: {e}")

            print(f"[RESULTS] OrderGuardian Ledger Path: '{db_path}'")

            if db_path == ":memory:" or db_path is None:
                print("❌ CRITICAL: Ledger is running in RAM. State will be lost on restart.")
            else:
                print("✅ PASSED: Ledger is using persistent storage.")

            # Show config fields to diagnose wiring (non-invasive).
            if cfg is not None:
                try:
                    guardian_root = getattr(cfg, "guardian", None)
                    execution_root = getattr(cfg, "execution", None)
                    trading_exec = getattr(getattr(cfg, "trading", None), "execution", None)
                    print(f"[CONFIG] cfg.guardian = {guardian_root!r}")
                    print(f"[CONFIG] cfg.execution = {execution_root!r}")
                    print(f"[CONFIG] cfg.trading.execution = {trading_exec!r}")
                    if execution_root is not None:
                        print(f"[CONFIG] cfg.execution.order_guardian = {getattr(execution_root, 'order_guardian', None)!r}")
                    if trading_exec is not None:
                        print(f"[CONFIG] cfg.trading.execution.order_guardian = {getattr(trading_exec, 'order_guardian', None)!r}")
                except Exception as e:
                    print(f"⚠️ Could not print config wiring: {e}")

        except Exception as e:
            print(f"⚠️ Initialization Error (might be due to missing deps, check logs): {e}")
            # Fallback: check how it tries to load config
            import inspect

            src = inspect.getsource(OrderGuardian.__init__)
            if "cfg.guardian" in src:
                print("❌ STATIC ANALYSIS CONFIRMED: Code looks for 'cfg.guardian' which may not exist in SSOT.")

    except ImportError:
        print("Could not import OrderGuardian.")


def test_id_determinism():
    print("\n--- TEST 2: Client Order ID Determinism (Restart Simulation) ---")
    try:
        from apps.reference.domains.execution_position.utils import generate_client_order_id

        symbol = "BTCUSDT"
        role = "ENTRY"
        # Simulate a specific trade intent (RID)
        rid = "trade-12345"

        print(f"Simulating Trade Intent: {rid}")

        # Attempt 1 (Time T)
        id1 = generate_client_order_id(role, rid, extra=symbol)
        print(f"Attempt 1 ID: {id1}")

        # Simulate Process Crash & Restart (Time passes)
        time.sleep(0.1)

        # Attempt 2 (Time T+0.1s, same trade intent)
        id2 = generate_client_order_id(role, rid, extra=symbol)
        print(f"Attempt 2 ID: {id2}")

        if id1 == id2:
            print("✅ PASSED: IDs are deterministic. Safe to retry.")
        else:
            print("❌ CRITICAL: IDs changed! Retrying this trade would open a DOUBLE POSITION.")

    except ImportError:
        print("Could not import utils.")


if __name__ == "__main__":
    print("running diagnostics...")
    test_guardian_config()
    test_id_determinism()

