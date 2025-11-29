import pytest
from unittest.mock import Mock
from apps.reference.domains.execution_position.utils_event_bus import LocalBus

class TestLocalBus:
    @pytest.fixture
    def bus(self):
        return LocalBus()

    def test_listen_and_emit_no_payload(self, bus):
        callback = Mock()
        bus.listen("TEST_EVENT", callback)
        
        bus.emit("TEST_EVENT")
        
        callback.assert_called_once()

    def test_listen_and_emit_with_payload(self, bus):
        callback = Mock()
        bus.listen("TEST_EVENT", callback)
        
        payload = {"data": 123}
        bus.emit("TEST_EVENT", payload)
        
        callback.assert_called_once_with(payload)

    def test_multiple_listeners(self, bus):
        cb1 = Mock()
        cb2 = Mock()
        
        bus.listen("TEST_EVENT", cb1)
        bus.listen("TEST_EVENT", cb2)
        
        bus.emit("TEST_EVENT", "payload")
        
        cb1.assert_called_once_with("payload")
        cb2.assert_called_once_with("payload")

    def test_error_isolation(self, bus):
        """Ensure one failing listener doesn't stop others."""
        def failing_callback(payload):
            raise ValueError("Boom!")
            
        success_callback = Mock()
        
        bus.listen("TEST_EVENT", failing_callback)
        bus.listen("TEST_EVENT", success_callback)
        
        # Should not raise exception
        bus.emit("TEST_EVENT", "payload")
        
        success_callback.assert_called_once_with("payload")

    def test_unlisten(self, bus):
        callback = Mock()
        bus.listen("TEST_EVENT", callback)
        
        bus.unlisten("TEST_EVENT", callback)
        bus.emit("TEST_EVENT")
        
        callback.assert_not_called()

    def test_unlisten_not_registered(self, bus):
        """Should not raise error when unlistening non-existent callback."""
        callback = Mock()
        bus.unlisten("TEST_EVENT", callback)  # No event
        
        bus.listen("TEST_EVENT", callback)
        bus.unlisten("TEST_EVENT", Mock()) # Event exists, callback doesn't
        
        bus.emit("TEST_EVENT")
        callback.assert_called_once()

    def test_emit_compatibility_args(self, bus):
        """Test that emit accepts why and data_ref arguments without error."""
        callback = Mock()
        bus.listen("TEST_EVENT", callback)
        
        bus.emit("TEST_EVENT", payload="data", why="testing", data_ref=["ref1"])
        
        callback.assert_called_once_with("data")
