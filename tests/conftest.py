"""
Root conftest.py for all tests.

Sets up test environment variables to suppress dev warnings.
"""
import os
import warnings


def pytest_configure(config):
    """Configure pytest with test environment variables."""
    # Set test environment variables to suppress config warnings
    if "RBAC_ADMIN_TOKENS" not in os.environ:
        os.environ["RBAC_ADMIN_TOKENS"] = "test-admin-token"
    if "SIGNING_KEY" not in os.environ:
        os.environ["SIGNING_KEY"] = "1" * 64  # Valid 64-char hex for Ed25519
    if "WORKER_ID" not in os.environ:
        os.environ["WORKER_ID"] = "test-worker-123"

    # Register custom markers
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "ws_rest: marks tests as websocket/rest tests")
    config.addinivalue_line("markers", "scen: marks tests as scenario tests")


def pytest_collection_modifyitems(config, items):
    """Filter out expected warnings in config tests."""
    # Filter warnings that are expected in config validation tests
    warnings.filterwarnings(
        "ignore",
        message=".*is below minimum.*",
        category=UserWarning,
        module="vfoundation.config"
    )
    warnings.filterwarnings(
        "ignore",
        message=".*is not a valid.*",
        category=UserWarning,
        module="vfoundation.config"
    )