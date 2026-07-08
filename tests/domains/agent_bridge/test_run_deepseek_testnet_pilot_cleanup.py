import logging
from unittest.mock import patch, MagicMock
from scripts.run_deepseek_testnet_pilot import DeepSeekPilotSession
import apps.reference.main

def test_cleanup_no_wal_gc_graceful(caplog):
    # Ensure apps.reference.main does not have wal_gc, csv_recorder, or guardian_runtime
    with patch("scripts.run_deepseek_testnet_pilot.load_pilot_config") as mock_load:
        mock_load.return_value = MagicMock()
        session = DeepSeekPilotSession()
        session.fsm_listener_active = True
        
        # Explicitly patch main to simulate missing attributes (AttributeError / None)
        with patch.object(apps.reference.main, "wal_gc", new=None, create=True), \
             patch.object(apps.reference.main, "csv_recorder", new=None, create=True), \
             patch.object(apps.reference.main, "guardian_runtime", new=None, create=True):
             
            with caplog.at_level(logging.WARNING):
                session.cleanup()
                
            # Assert no warnings or errors were logged during cleanup
            warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
            assert not warnings, f"Cleanup warned/errored: {warnings}"

            # Verify listener deactivated
            assert not session.fsm_listener_active
