import sys
from pathlib import Path

# Ensure project root is on sys.path for local package imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

import importlib.util

_ADAPTER_PATH = ROOT / "apps" / "reference" / "domains" / \
    "execution_position" / "binance_execution_adapter.py"
_MODULE_NAME = "apps.reference.domains.execution_position.binance_execution_adapter"

# Seed parent packages so relative imports inside the adapter module resolve
import types as _types
apps_pkg = _types.ModuleType("apps")
apps_pkg.__path__ = [str(ROOT / "apps")]
reference_pkg = _types.ModuleType("apps.reference")
reference_pkg.__path__ = [str(ROOT / "apps" / "reference")]
domains_pkg = _types.ModuleType("apps.reference.domains")
domains_pkg.__path__ = [str(ROOT / "apps" / "reference" / "domains")]
execpos_pkg = _types.ModuleType("apps.reference.domains.execution_position")
execpos_pkg.__path__ = [str(ROOT / "apps" / "reference" / "domains" / "execution_position")]

for _name, _pkg in [
    ("apps", apps_pkg),
    ("apps.reference", reference_pkg),
    ("apps.reference.domains", domains_pkg),
    ("apps.reference.domains.execution_position", execpos_pkg),
]:
    sys.modules.setdefault(_name, _pkg)

_spec = importlib.util.spec_from_file_location(
    _MODULE_NAME, _ADAPTER_PATH)
adapter_mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules[_MODULE_NAME] = adapter_mod
_spec.loader.exec_module(adapter_mod)  # type: ignore
BinanceExecutionAdapter = adapter_mod.BinanceExecutionAdapter


class _DummyResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._payload


class _DummyAsyncClient:
    def __init__(self, response: _DummyResponse | Exception):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, timeout=None):
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


@pytest.mark.asyncio
async def test_time_sync_async_success(monkeypatch):
    adapter = BinanceExecutionAdapter(fsm=None, config={})

    # Deterministic time
    monkeypatch.setattr(adapter_mod.time, "time", lambda: 1.0)

    dummy_resp = _DummyResponse(status_code=200, payload={"serverTime": 1500})
    monkeypatch.setattr(
        adapter_mod.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(dummy_resp),
    )

    await adapter._sync_time_with_server()

    assert adapter.server_time_offset == 500  # serverTime - local_time (1000ms)
    assert adapter.last_time_sync == 1.0


def test_time_sync_blocking_handles_error(monkeypatch):
    adapter = BinanceExecutionAdapter(fsm=None, config={})

    # Ensure async client raises to exercise exception handling path
    monkeypatch.setattr(
        adapter_mod.httpx,
        "AsyncClient",
        lambda *args, **kwargs: _DummyAsyncClient(Exception("boom")),
    )

    # Should not raise, even if underlying async call fails
    adapter._sync_time_with_server_blocking()
