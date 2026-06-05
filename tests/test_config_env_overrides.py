"""
Tests for FSMP-P1-T04: ENV-based config system
Tests ENV overrides, validation, defaults, and reload_config()
"""

import pathlib
from vfoundation.config import reload_config, config


class TestConfigDefaults:
    """Test default values when ENV vars not set"""

    def test_dev_default_admin_token(self, monkeypatch):
        """Verify dev-admin-token default when RBAC_ADMIN_TOKENS unset"""
        monkeypatch.delenv("RBAC_ADMIN_TOKENS", raising=False)
        reload_config()

        assert config.rbac_admin_tokens == ["dev-admin-token"]

    def test_dev_default_signing_key(self, monkeypatch):
        """Verify 64-byte zero key default when SIGNING_KEY unset"""
        monkeypatch.delenv("SIGNING_KEY", raising=False)
        reload_config()

        assert config.signing_key == "0" * 64
        assert len(config.signing_key) == 64

    def test_operational_defaults(self, monkeypatch):
        """Verify operational knobs use documented defaults"""
        for var in [
            "RBAC_ADMIN_TOKENS",
            "SIGNING_KEY",
            "WAL_DIR",
            "WAL_LOCK_TIMEOUT_SEC",
            "CB_THRESHOLD",
            "CB_COOLDOWN_SEC",
            "IDEM_TTL_MS",
            "IDEM_MAX_ENTRIES",
            "DRIFT_TIME_WINDOW_SEC",
        ]:
            monkeypatch.delenv(var, raising=False)
        reload_config()

        assert config.wal_dir.name == "wal"
        assert config.wal_lock_timeout_sec == 5.0
        assert config.cb_threshold == 5
        assert config.cb_cooldown_sec == 60.0
        assert config.idem_ttl_ms == 600_000
        assert config.idem_max_entries == 10_000
        assert config.drift_time_window_sec == 1.0


class TestConfigENVOverrides:
    """Test ENV variable overrides"""

    def test_single_admin_token_override(self, monkeypatch):
        """Test single token in RBAC_ADMIN_TOKENS"""
        monkeypatch.setenv("RBAC_ADMIN_TOKENS", "prod-token-abc123")
        reload_config()

        assert config.rbac_admin_tokens == ["prod-token-abc123"]

    def test_multiple_admin_tokens_override(self, monkeypatch):
        """Test comma-separated tokens in RBAC_ADMIN_TOKENS"""
        monkeypatch.setenv("RBAC_ADMIN_TOKENS", "token1,token2,token3")
        reload_config()

        assert config.rbac_admin_tokens == ["token1", "token2", "token3"]

    def test_whitespace_trimmed_tokens(self, monkeypatch):
        """Test tokens with leading/trailing whitespace are trimmed"""
        monkeypatch.setenv("RBAC_ADMIN_TOKENS", " token1 , token2 , token3 ")
        reload_config()

        assert config.rbac_admin_tokens == ["token1", "token2", "token3"]

    def test_signing_key_override(self, monkeypatch):
        """Test SIGNING_KEY override"""
        test_key = "a" * 64
        monkeypatch.setenv("SIGNING_KEY", test_key)
        reload_config()

        assert config.signing_key == test_key

    def test_wal_dir_override(self, monkeypatch):
        """Test WAL_DIR override"""
        monkeypatch.setenv("WAL_DIR", "/custom/wal/path")
        reload_config()

        # pathlib normalizes path separators on Windows
        assert config.wal_dir == pathlib.Path("/custom/wal/path")

    def test_int_env_overrides(self, monkeypatch):
        """Test integer ENV overrides"""
        monkeypatch.setenv("CB_THRESHOLD", "10")
        monkeypatch.setenv("CB_COOLDOWN_SEC", "120")
        monkeypatch.setenv("IDEM_TTL_MS", "300000")
        monkeypatch.setenv("IDEM_MAX_ENTRIES", "5000")
        reload_config()

        assert config.cb_threshold == 10
        assert config.cb_cooldown_sec == 120.0
        assert config.idem_ttl_ms == 300_000
        assert config.idem_max_entries == 5_000

    def test_float_env_overrides(self, monkeypatch):
        """Test float ENV overrides"""
        monkeypatch.setenv("WAL_LOCK_TIMEOUT_SEC", "10.5")
        monkeypatch.setenv("DRIFT_TIME_WINDOW_SEC", "2.5")
        reload_config()

        assert config.wal_lock_timeout_sec == 10.5
        assert config.drift_time_window_sec == 2.5


class TestConfigValidation:
    """Test validation and bounds checking"""

    def test_cb_threshold_minimum(self, monkeypatch):
        """Test CB_THRESHOLD clamped to minimum 1"""
        monkeypatch.setenv("CB_THRESHOLD", "0")
        reload_config()

        assert config.cb_threshold == 1  # Clamped to min

    def test_cb_cooldown_minimum(self, monkeypatch):
        """Test CB_COOLDOWN_SEC clamped to minimum 1.0"""
        monkeypatch.setenv("CB_COOLDOWN_SEC", "0")
        reload_config()

        assert config.cb_cooldown_sec == 1.0  # Clamped to min

    def test_idem_ttl_minimum(self, monkeypatch):
        """Test IDEM_TTL_MS clamped to minimum 1000"""
        monkeypatch.setenv("IDEM_TTL_MS", "500")
        reload_config()

        assert config.idem_ttl_ms == 1_000  # Clamped to min

    def test_idem_max_entries_minimum(self, monkeypatch):
        """Test IDEM_MAX_ENTRIES clamped to minimum 100"""
        monkeypatch.setenv("IDEM_MAX_ENTRIES", "50")
        reload_config()

        assert config.idem_max_entries == 100  # Clamped to min

    def test_wal_lock_timeout_minimum(self, monkeypatch):
        """Test WAL_LOCK_TIMEOUT_SEC clamped to minimum 0.1"""
        monkeypatch.setenv("WAL_LOCK_TIMEOUT_SEC", "0.01")
        reload_config()

        assert config.wal_lock_timeout_sec == 0.1  # Clamped to min

    def test_drift_window_minimum(self, monkeypatch):
        """Test DRIFT_TIME_WINDOW_SEC clamped to minimum 0.1"""
        monkeypatch.setenv("DRIFT_TIME_WINDOW_SEC", "0.05")
        reload_config()

        assert config.drift_time_window_sec == 0.1  # Clamped to min

    def test_invalid_int_uses_default(self, monkeypatch):
        """Test invalid integer falls back to default with warning"""
        monkeypatch.setenv("CB_THRESHOLD", "not-a-number")
        reload_config()

        assert config.cb_threshold == 5  # Default value

    def test_invalid_float_uses_default(self, monkeypatch):
        """Test invalid float falls back to default with warning"""
        monkeypatch.setenv("WAL_LOCK_TIMEOUT_SEC", "not-a-float")
        reload_config()

        assert config.wal_lock_timeout_sec == 5.0  # Default value


class TestReloadConfig:
    """Test reload_config() function for test isolation"""

    def test_reload_picks_up_new_env_values(self, monkeypatch):
        """Test reload_config() reloads ENV changes"""
        monkeypatch.setenv("RBAC_ADMIN_TOKENS", "initial-token")
        reload_config()
        assert config.rbac_admin_tokens == ["initial-token"]

        # Change ENV and reload
        monkeypatch.setenv("RBAC_ADMIN_TOKENS", "updated-token")
        reload_config()
        assert config.rbac_admin_tokens == ["updated-token"]

    def test_reload_restores_defaults_after_delenv(self, monkeypatch):
        """Test reload_config() restores defaults after ENV removal"""
        monkeypatch.setenv("CB_THRESHOLD", "20")
        reload_config()
        assert config.cb_threshold == 20

        # Remove ENV and reload
        monkeypatch.delenv("CB_THRESHOLD")
        reload_config()
        assert config.cb_threshold == 5  # Back to default
