"""Tests for vfoundation.config — Config singleton, ENV-driven knobs, reload."""

from __future__ import annotations

import os
import pathlib
import warnings

import pytest


# ── Helper: fresh Config from ENV ─────────────────────────────────────────

def _make_config(**env_overrides: str):
    """Create a Config instance with controlled ENV vars (isolated from singleton)."""
    from vfoundation.config import Config
    _saved = {}
    for k, v in env_overrides.items():
        _saved[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        return Config()
    finally:
        for k, orig in _saved.items():
            if orig is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = orig


# ── Defaults (no ENV set) ────────────────────────────────────────────────


class TestConfigDefaults:
    def test_wal_dir_default(self) -> None:
        cfg = _make_config(WAL_DIR=None)
        assert str(cfg.wal_dir) in ("ops/wal", "ops\\wal")

    def test_cb_threshold_default(self) -> None:
        cfg = _make_config(CB_THRESHOLD=None)
        assert cfg.cb_threshold == 5

    def test_cb_cooldown_default(self) -> None:
        cfg = _make_config(CB_COOLDOWN_SEC=None)
        assert cfg.cb_cooldown_sec == 60.0

    def test_idem_ttl_default(self) -> None:
        cfg = _make_config(IDEM_TTL_MS=None)
        assert cfg.idem_ttl_ms == 600_000

    def test_execution_mode_default(self) -> None:
        cfg = _make_config(EXECUTION_MODE=None)
        assert cfg.execution_mode == "dry_run"

    def test_redis_url_default(self) -> None:
        cfg = _make_config(REDIS_URL=None)
        assert cfg.redis_url == "redis://localhost:6379/0"


# ── Integer ENV with bounds ───────────────────────────────────────────────


class TestIntEnv:
    def test_valid_int(self) -> None:
        cfg = _make_config(CB_THRESHOLD="10")
        assert cfg.cb_threshold == 10

    def test_below_min_clamps(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(CB_THRESHOLD="0")
        assert cfg.cb_threshold == 1  # min_val
        assert any("below minimum" in str(x.message) for x in w)

    def test_above_max_clamps(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(CB_THRESHOLD="999")
        assert cfg.cb_threshold == 100  # max_val
        assert any("exceeds maximum" in str(x.message) for x in w)

    def test_non_integer_falls_back(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(CB_THRESHOLD="abc")
        assert cfg.cb_threshold == 5  # default
        assert any("not a valid integer" in str(x.message) for x in w)


# ── Float ENV with bounds ─────────────────────────────────────────────────


class TestFloatEnv:
    def test_valid_float(self) -> None:
        cfg = _make_config(CB_COOLDOWN_SEC="30.5")
        assert cfg.cb_cooldown_sec == 30.5

    def test_below_min_clamps(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(CB_COOLDOWN_SEC="0.01")
        assert cfg.cb_cooldown_sec == 1.0  # min_val
        assert any("below minimum" in str(x.message) for x in w)

    def test_above_max_clamps(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(CB_COOLDOWN_SEC="9999")
        assert cfg.cb_cooldown_sec == 3600.0  # max_val

    def test_non_float_falls_back(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(CB_COOLDOWN_SEC="xyz")
        assert cfg.cb_cooldown_sec == 60.0
        assert any("not a valid number" in str(x.message) for x in w)


# ── RBAC tokens ───────────────────────────────────────────────────────────


class TestRbacTokens:
    def test_custom_tokens_csv(self) -> None:
        cfg = _make_config(RBAC_ADMIN_TOKENS="tok1, tok2, tok3 ")
        assert cfg.rbac_admin_tokens == ["tok1", "tok2", "tok3"]

    def test_empty_rbac_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(RBAC_ADMIN_TOKENS="")
        assert cfg.rbac_admin_tokens == ["dev-admin-token"]
        assert any("INSECURE dev default" in str(x.message) for x in w)

    def test_blank_csv_warns_no_access(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(RBAC_ADMIN_TOKENS=" , , ")
        assert cfg.rbac_admin_tokens == []
        assert any("no admin access" in str(x.message) for x in w)


# ── Signing key ───────────────────────────────────────────────────────────


class TestSigningKey:
    def test_unset_uses_dev_default(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(SIGNING_KEY=None)
        assert cfg.signing_key == "0" * 64
        assert any("INSECURE dev default" in str(x.message) for x in w)

    def test_valid_64_hex(self) -> None:
        key = "a" * 64
        cfg = _make_config(SIGNING_KEY=key)
        assert cfg.signing_key == key

    def test_wrong_length_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(SIGNING_KEY="short")
        assert cfg.signing_key == "short"
        assert any("64 hex characters" in str(x.message) for x in w)


# ── Execution mode ────────────────────────────────────────────────────────


class TestExecutionMode:
    def test_dry_run(self) -> None:
        cfg = _make_config(EXECUTION_MODE="dry_run")
        assert cfg.execution_mode == "dry_run"

    def test_invalid_mode_falls_back(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(EXECUTION_MODE="turbo")
        assert cfg.execution_mode == "dry_run"
        assert any("invalid" in str(x.message) for x in w)

    def test_live_without_creds_raises(self) -> None:
        with pytest.raises(RuntimeError, match="EXECUTION_MODE=live requires"):
            _make_config(
                EXECUTION_MODE="live",
                EXCHANGE_API_KEY=None,
                EXCHANGE_API_SECRET=None,
                EXCHANGE_BASE_URL=None,
            )

    def test_paper_with_all_creds(self) -> None:
        cfg = _make_config(
            EXECUTION_MODE="paper",
            EXCHANGE_API_KEY="k",
            EXCHANGE_API_SECRET="s",
            EXCHANGE_BASE_URL="http://fake",
        )
        assert cfg.execution_mode == "paper"


# ── Worker ID ─────────────────────────────────────────────────────────────


class TestWorkerId:
    def test_auto_generated_when_unset(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _make_config(WORKER_ID=None)
        # Generated: <hostname>-<8hex>
        assert len(cfg.worker_id) > 8
        assert any("generated ID" in str(x.message) for x in w)

    def test_explicit_worker_id(self) -> None:
        cfg = _make_config(WORKER_ID="worker-1")
        assert cfg.worker_id == "worker-1"


# ── reload_config ─────────────────────────────────────────────────────────


class TestReloadConfig:
    def test_reload_updates_singleton(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from vfoundation.config import config, reload_config

        original_threshold = config.cb_threshold

        monkeypatch.setenv("CB_THRESHOLD", "42")
        reload_config()

        assert config.cb_threshold == 42

        # Restore
        monkeypatch.delenv("CB_THRESHOLD", raising=False)
        reload_config()
