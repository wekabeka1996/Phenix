import pytest
from unittest.mock import patch, MagicMock
import gc
import time


# This test ensures the main startup doesn't raise TypeError due to config loader signature.
def test_main_startup_no_config_error():
    """
    Verifies that the main application entry point can initialize
    without raising a TypeError related to config loading.
    """
    try:
        # Force garbage collection to close any open database connections from previous tests
        gc.collect()
        time.sleep(0.1)  # Allow DB to fully release lock

        # Mock the infinite loop by making time.sleep raise KeyboardInterrupt
        with patch("time.sleep", side_effect=KeyboardInterrupt):
            # Dynamic import by file path to ensure module resolution in test env
            import importlib.util
            from pathlib import Path

            repo_root = Path(__file__).resolve().parents[2]
            main_path = repo_root / "apps" / "reference" / "main.py"
            # Ensure that vfoundation.core and vfoundation.core.protocol can be imported during module exec
            import sys

            # Ensure the repository root and embedded 'vfoundation' package are on sys.path
            if str(repo_root) not in sys.path:
                sys.path.insert(0, str(repo_root))
            vfound_package_path = repo_root / "vfoundation"
            if str(vfound_package_path) not in sys.path:
                sys.path.insert(0, str(vfound_package_path))

            # Remove any existing conflicting modules injected by other tests
            for mod in ["vfoundation", "vfoundation.core", "vfoundation.core.protocol"]:
                if mod in sys.modules:
                    del sys.modules[mod]

            spec = importlib.util.spec_from_file_location(
                "apps.reference.main", str(main_path)
            )
            main_app = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(main_app)  # type: ignore[attr-defined]
            # Now patch FSMCore in the loaded module so main() will use a mock with expected API
            main_app.FSMCore = MagicMock()
            mock_fsm_inst = main_app.FSMCore.return_value
            mock_fsm_inst.register_domain = MagicMock()
            mock_fsm_inst.listen = MagicMock()
            mock_fsm_inst.emit = MagicMock()
            # Mock domain components on the imported module to avoid side effects during init
            with patch.object(main_app, "MarketDataConnector", MagicMock()):
                with patch.object(main_app, "AccountObserver", MagicMock()):
                    # Call main (it will be interrupted by the mocked time.sleep)
                    main_app.main()
    except TypeError as e:
        pytest.fail(
            f"Startup failed with TypeError, likely due to config loader issue: {e}"
        )
    except KeyboardInterrupt:
        # Expected exit from mocked loop
        pass
    except Exception as e:
        pytest.fail(f"An unexpected error occurred during startup: {e}")
    finally:
        # Cleanup: force garbage collection to ensure all DB connections are closed
        gc.collect()
        time.sleep(0.1)
