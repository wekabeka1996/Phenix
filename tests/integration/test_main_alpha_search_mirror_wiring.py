import logging
from types import SimpleNamespace

import apps.reference.main as main_mod


class _FakePlugin:
    def __init__(self, *, event_bus, config):
        self.event_bus = event_bus
        self.config = config
        self.providers = {"aurora": object()}


class _FakeWriter:
    def __init__(self, *, event_bus, output_path, symbols):
        self.event_bus = event_bus
        self.output_path = output_path
        self.symbols = symbols


def _provider(*, enabled=True, symbols=None):
    return SimpleNamespace(enabled=enabled, symbols=symbols)


def test_resolve_alpha_search_mirror_symbols_uses_enabled_bounded_providers() -> None:
    cfg = SimpleNamespace(
        providers={
            "aurora": _provider(symbols=["ethusdt", "BTCUSDT"]),
            "md_amr": _provider(enabled=False, symbols=["SOLUSDT"]),
        }
    )

    assert main_mod._resolve_alpha_search_mirror_symbols(cfg) == ["BTCUSDT", "ETHUSDT"]


def test_resolve_alpha_search_mirror_symbols_returns_none_for_unbounded_provider() -> None:
    cfg = SimpleNamespace(
        providers={
            "aurora": _provider(symbols=["BTCUSDT"]),
            "ta_ensemble": _provider(symbols=None),
        }
    )

    assert main_mod._resolve_alpha_search_mirror_symbols(cfg) is None


def test_bootstrap_alpha_search_shadow_registers_feature_mirror_writer(tmp_path) -> None:
    cfg = SimpleNamespace(
        enabled=True,
        shadow_mode=True,
        providers={
            "aurora": _provider(symbols=["BTCUSDT"]),
            "ta_ensemble": _provider(symbols=None),
        },
    )

    bundle = main_mod._bootstrap_alpha_search_shadow(
        event_bus=object(),
        project_root=tmp_path,
        logger=logging.getLogger("test.alpha_search"),
        load_config_fn=lambda _: cfg,
        plugin_cls=_FakePlugin,
        mirror_writer_cls=_FakeWriter,
    )

    expected_output = tmp_path / "logs" / "alpha_input" / "alpha_input_v1.jsonl"
    assert bundle["plugin"].config is cfg
    assert bundle["mirror_symbols"] is None
    assert bundle["mirror_output_path"] == expected_output
    assert bundle["mirror_writer"].output_path == expected_output
    assert bundle["mirror_writer"].symbols is None