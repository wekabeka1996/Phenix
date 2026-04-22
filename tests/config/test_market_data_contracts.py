from __future__ import annotations

import importlib
import logging
import shutil
from multiprocessing import Queue
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest
import yaml
from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
import apps.reference.config.system.market_data as system_market_data
import apps.reference.config_models as cm
from apps.reference.domains.decision_making.gates import ttl_gate
from apps.reference.domains.market_data.proxy import MarketDataProxy
from apps.reference.domains.market_data.worker import MarketDataWorker


CONFIG_DIR = Path("config/aurora")


def _is_optional_union(tp: Any) -> bool:
    return type(None) in get_args(tp)


def _annotation_includes(tp: Any, expected: Any) -> bool:
    return tp is expected or expected in get_args(tp)


def _assert_literal_values(tp: Any, expected: tuple[Any, ...]) -> None:
    assert get_args(tp) == expected


def _assert_field_contract(
    model_cls: type,
    *,
    required: set[str],
    defaults: dict[str, Any],
    optional_fields: set[str] | None = None,
) -> None:
    optional_fields = optional_fields or set()
    fields = model_cls.model_fields
    expected_fields = required | set(defaults)

    assert set(fields) == expected_fields
    assert model_cls.model_config.get("extra") == "forbid"

    for name in required:
        field_info = fields[name]
        assert field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay required"
        )
        assert field_info.default_factory is None

    for name, expected_default in defaults.items():
        field_info = fields[name]
        assert not field_info.is_required(), (
            f"{model_cls.__name__}.{name} must stay optional/defaulted"
        )
        assert field_info.default == expected_default
        assert field_info.default_factory is None

    for name in optional_fields:
        assert _is_optional_union(fields[name].annotation), (
            f"{model_cls.__name__}.{name} must stay Optional in the extraction contract"
        )


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    return cfg_dir


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


class _Clock:
    def __init__(self, now_ms: int) -> None:
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms


def test_market_data_facade_reexports_are_exact_identity() -> None:
    assert cm.MarketDataConfig is system_market_data.MarketDataConfig
    assert cm.BarAggregatorConfig is system_market_data.BarAggregatorConfig
    assert cm.MacroSyncConfig is system_market_data.MacroSyncConfig
    assert cm.SystemMarketDataConfig is system_market_data.SystemMarketDataConfig


def test_market_data_canonical_definitions_live_only_in_extracted_module() -> None:
    facade_source = Path(cm.__file__).read_text(encoding="utf-8")
    module_source = Path(
        system_market_data.__file__).read_text(encoding="utf-8")

    for marker in (
        "\nclass MacroSyncConfig(",
        "\nclass BarAggregatorConfig(",
        "\nclass MarketDataConfig(",
        "\nclass SystemMarketDataConfig(",
    ):
        assert facade_source.count(marker) == 0, (
            f"{marker.strip()} should no longer be defined in config_models.py after Phase 4 / Pkg 3 extraction."
        )
        assert module_source.count(marker) == 1, (
            f"{marker.strip()} must have exactly one top-level definition in apps.reference.config.system.market_data."
        )


def test_market_data_extraction_preserves_field_contracts() -> None:
    _assert_field_contract(
        cm.MacroSyncConfig,
        required={
            "enabled",
            "anchors",
            "window",
            "emit_abs",
            "align_mode",
            "min_buffer_size",
            "time_diff_threshold_ms",
            "anchor_update_from_ticks",
        },
        defaults={},
    )
    _assert_field_contract(
        cm.BarAggregatorConfig,
        required={"enabled", "timeframes_sec"},
        defaults={},
    )
    _assert_field_contract(
        cm.MarketDataConfig,
        required={
            "poll_interval_sec",
            "use_multiprocessing",
            "websocket_streams",
            "macro_sync",
        },
        defaults={"bar_aggregator": None},
        optional_fields={"macro_sync", "bar_aggregator"},
    )
    _assert_field_contract(
        cm.SystemMarketDataConfig,
        required={
            "queue_maxsize",
            "tick_ttl_ms",
            "ws_heartbeat_sec",
            "ws_receive_timeout_sec",
            "proxy_batch_size",
            "proxy_queue_get_timeout_sec",
            "proxy_idle_sleep_sec",
        },
        defaults={
            "local_queue_maxsize": 10000,
            "emit_workers": 4,
            "bar_ttl_ms": 10000,
            "bar_event_age_mode": "received",
        },
        optional_fields={"bar_ttl_ms"},
    )

    market_data_fields = cm.MarketDataConfig.model_fields
    system_fields = cm.SystemMarketDataConfig.model_fields

    assert _annotation_includes(
        market_data_fields["macro_sync"].annotation, cm.MacroSyncConfig)
    assert _annotation_includes(
        market_data_fields["bar_aggregator"].annotation, cm.BarAggregatorConfig)
    _assert_literal_values(
        system_fields["bar_event_age_mode"].annotation,
        ("received", "close_ts"),
    )


def test_market_data_extraction_preserves_assembly_annotations() -> None:
    trading_fields = cm.TradingConfig.model_fields
    system_fields = cm.SystemConfig.model_fields

    assert _annotation_includes(
        trading_fields["market_data"].annotation, cm.MarketDataConfig)
    assert _annotation_includes(
        system_fields["market_data"].annotation, cm.SystemMarketDataConfig)


def test_current_aurora_config_loads_market_data_contract() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    assert type(cfg.trading.market_data) is cm.MarketDataConfig
    assert type(cfg.trading.market_data.macro_sync) is cm.MacroSyncConfig
    assert type(cfg.trading.market_data.bar_aggregator) is cm.BarAggregatorConfig
    assert cfg.trading.market_data.poll_interval_sec == 5.0
    assert cfg.trading.market_data.use_multiprocessing is True
    assert cfg.trading.market_data.websocket_streams == ["bookTicker", "trade"]
    assert cfg.trading.market_data.macro_sync.anchors == ["BTCUSDT", "ETHUSDT"]
    assert cfg.trading.market_data.bar_aggregator.timeframes_sec == [
        180, 300, 900, 14400, 86400]

    assert type(cfg.system.market_data) is cm.SystemMarketDataConfig
    assert cfg.system.market_data.queue_maxsize == 10000
    assert cfg.system.market_data.tick_ttl_ms == 2000
    assert cfg.system.market_data.bar_ttl_ms == 10000
    assert cfg.system.market_data.bar_event_age_mode == "received"

    assert not hasattr(cfg.trading.market_data, "queue_maxsize")
    assert not hasattr(cfg.system.market_data, "poll_interval_sec")


def test_market_data_runtime_import_smoke() -> None:
    modules = {
        name: importlib.import_module(name)
        for name in (
            "apps.reference.config_models",
            "apps.reference.config.system.market_data",
            "apps.reference.config.system.observability",
            "apps.reference.config.system.ops",
            "apps.reference.config_loader",
            "apps.reference.domains.market_data.proxy",
            "apps.reference.domains.market_data.worker",
            "apps.reference.domains.market_data.market_data_connector",
            "apps.reference.domains.decision_making.gates.ttl_gate",
            "apps.reference.domains.decision_making.readiness_gates",
            "apps.reference.domains.regime_detector.regime_detector",
        )
    }

    assert hasattr(
        modules["apps.reference.config.system.market_data"], "MarketDataConfig")
    assert hasattr(
        modules["apps.reference.domains.market_data.proxy"], "MarketDataProxy")
    assert hasattr(
        modules["apps.reference.domains.market_data.worker"], "MarketDataWorker")


def test_market_data_runtime_split_still_drives_proxy_worker_and_dm_ttl_gate() -> None:
    cfg = ConfigLoader(CONFIG_DIR).load_config()

    proxy = MarketDataProxy(fsm=None, config=cfg)
    assert proxy._queue_maxsize == cfg.system.market_data.queue_maxsize
    assert proxy._batch_size == cfg.system.market_data.proxy_batch_size
    assert proxy._queue_get_timeout_sec == cfg.system.market_data.proxy_queue_get_timeout_sec
    assert proxy._idle_sleep_sec == cfg.system.market_data.proxy_idle_sleep_sec

    queue = Queue()
    try:
        worker = MarketDataWorker(
            queue,
            cfg.model_dump(mode="json"),
            logging.getLogger("pkg3_market_data_contracts"),
        )
    finally:
        queue.close()

    assert worker._anchors == cfg.trading.market_data.macro_sync.anchors
    assert worker._poll_interval == cfg.trading.market_data.poll_interval_sec
    assert worker._ws_heartbeat_sec == float(
        cfg.system.market_data.ws_heartbeat_sec)
    assert worker._ws_receive_timeout_sec == float(
        cfg.system.market_data.ws_receive_timeout_sec)

    reject_ctx = SimpleNamespace(
        dm=SimpleNamespace(features_ttl_sec=1),
        pld={"tf_sec": 300},
        ts_ms=0,
        clock=_Clock(now_ms=15_000),
        config=cfg,
    )
    reject_result = ttl_gate.check(reject_ctx)
    assert reject_result.reason_code == "SIGNAL_STALE"

    relaxed_cfg = cfg.model_copy(update={
        "system": cfg.system.model_copy(update={
            "market_data": cfg.system.market_data.model_copy(update={"bar_ttl_ms": 20_000})
        })
    })
    pass_ctx = SimpleNamespace(
        dm=SimpleNamespace(features_ttl_sec=1),
        pld={"tf_sec": 300},
        ts_ms=0,
        clock=_Clock(now_ms=15_000),
        config=relaxed_cfg,
    )
    pass_result = ttl_gate.check(pass_ctx)
    assert pass_result.outcome.name == "PASS"


def test_market_data_yaml_contract_fails_closed_on_forbidden_trading_market_data_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    payload["trading"]["market_data"]["unexpected_pkg3_market_data_field"] = True
    _write_yaml(trading_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg3_market_data_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_market_data_yaml_contract_fails_closed_on_forbidden_macro_sync_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    payload["trading"]["market_data"]["macro_sync"]["unexpected_pkg3_macro_sync_field"] = True
    _write_yaml(trading_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg3_macro_sync_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_market_data_yaml_contract_fails_closed_on_invalid_bar_aggregator_timeframes_type(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    trading_path = cfg_dir / "trading.yaml"
    payload = _load_yaml(trading_path)
    payload["trading"]["market_data"]["bar_aggregator"]["timeframes_sec"] = ["bad_tf"]
    _write_yaml(trading_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "timeframes_sec" in message
    assert "valid integer" in message.lower() or "int" in message.lower()


def test_market_data_yaml_contract_fails_closed_on_forbidden_system_market_data_extra_field(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    payload = _load_yaml(system_path)
    payload["system"]["market_data"]["unexpected_pkg3_system_market_data_field"] = True
    _write_yaml(system_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "unexpected_pkg3_system_market_data_field" in message
    assert "extra inputs are not permitted" in message.lower()


def test_market_data_yaml_contract_fails_closed_on_invalid_system_bar_event_age_mode(
    tmp_path: Path,
) -> None:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    system_path = cfg_dir / "system.yaml"
    payload = _load_yaml(system_path)
    payload["system"]["market_data"]["bar_event_age_mode"] = "invalid_mode"
    _write_yaml(system_path, payload)

    with pytest.raises(ValidationError) as exc_info:
        ConfigLoader(config_dir=cfg_dir).load_config()

    message = str(exc_info.value)
    assert "bar_event_age_mode" in message
    assert "received" in message or "close_ts" in message
