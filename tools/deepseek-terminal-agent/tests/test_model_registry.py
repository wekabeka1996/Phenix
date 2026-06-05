"""Tests for live/cached/static model registry behavior."""
from __future__ import annotations

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.model_registry import ModelRegistry


class FakeClient:
    def __init__(self, models):
        self._models = models

    def list_models(self):
        return self._models


class FailingClient:
    def list_models(self):
        raise RuntimeError("network down")


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def test_static_models_present_when_no_cache_or_live_refresh(tmp_path):
    registry = ModelRegistry(
        make_settings(),
        root_dir=tmp_path,
        client_factory=lambda: FailingClient(),
    )

    catalog = registry.list_models()
    assert catalog.source == "static_fallback"
    assert [model.model_id for model in catalog.models] == [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ]


def test_refresh_from_api_success_updates_live_catalog_and_cache(tmp_path):
    registry = ModelRegistry(
        make_settings(),
        root_dir=tmp_path,
        client_factory=lambda: FakeClient([
            {"id": "deepseek-v4-pro"},
            {"id": "deepseek-v4-flash"},
            {"id": "deepseek-custom"},
        ]),
    )

    catalog = registry.refresh_from_api()
    assert catalog.source == "live"
    assert [model.model_id for model in catalog.models] == [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-custom",
    ]
    assert registry.cache_path.exists()


def test_refresh_api_failure_uses_cache_with_warning(tmp_path):
    settings = make_settings()
    warm_registry = ModelRegistry(
        settings,
        root_dir=tmp_path,
        client_factory=lambda: FakeClient([
            {"id": "deepseek-v4-pro"},
            {"id": "deepseek-v4-flash"},
        ]),
    )
    warm_registry.refresh_from_api()

    failing_registry = ModelRegistry(
        settings,
        root_dir=tmp_path,
        client_factory=lambda: FailingClient(),
    )
    catalog = failing_registry.refresh_from_api()

    assert catalog.source == "cached"
    assert catalog.warning is not None
    assert "cached model registry" in catalog.warning


def test_invalid_model_fails_explicitly(tmp_path):
    registry = ModelRegistry(make_settings(), root_dir=tmp_path)

    try:
        registry.validate_model_id("missing-model")
    except ValueError as exc:
        assert "missing-model" in str(exc)
    else:
        raise AssertionError(
            "validate_model_id should fail for missing models")


def test_manual_advanced_model_id_allowed_only_in_advanced_mode(tmp_path):
    registry = ModelRegistry(make_settings(), root_dir=tmp_path)

    advanced = registry.resolve_model_id(
        "deepseek-manual-preview", advanced_mode=True)
    assert advanced.model_id == "deepseek-manual-preview"
    assert advanced.metadata["advanced_mode"] is True

    try:
        registry.resolve_model_id(
            "deepseek-manual-preview", advanced_mode=False)
    except ValueError as exc:
        assert "deepseek-manual-preview" in str(exc)
    else:
        raise AssertionError(
            "resolve_model_id should fail without advanced_mode")
