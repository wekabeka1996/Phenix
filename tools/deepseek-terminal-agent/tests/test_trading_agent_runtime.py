from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from deepseek_terminal_agent.config import DeepSeekConfig
from deepseek_terminal_agent.sessions.p42_config import load_dual_agent_config
from deepseek_terminal_agent.sessions.trading_agent_runtime import (
    OpenAICompatibleTradingAgentRuntime,
    RestrictedCLITradingAgentRuntime,
    TradingResponse,
    TradingTurnContext,
    build_trading_agent_runtime,
)


ROOT = Path(__file__).resolve().parents[3]
P42_CONFIG = ROOT / "config" / "p42_dual_agent_mvp.yaml"


def api_config(retry_count: int = 0, timeout: int = 2):
    cfg = load_dual_agent_config(P42_CONFIG).agents["api_agent_01"]
    return cfg.model_copy(update={"retry_count": retry_count, "response_timeout_sec": timeout})


def cli_config(*, timeout: int = 2, **updates):
    cfg = load_dual_agent_config(P42_CONFIG).agents["cli_agent_01"]
    return cfg.model_copy(update={"response_timeout_sec": timeout, **updates})


def context(
    *,
    turn_id: str = "turn-1",
    symbol: str = "ETHUSDT",
    version: str = "collective-1",
    instruction: str = "manifest-1",
    tools: list[str] | None = None,
    owned_symbols: list[str] | None = None,
) -> TradingTurnContext:
    configured_symbols = owned_symbols or ["ETHUSDT", "SOLUSDT"]
    return TradingTurnContext(
        session_id="session-p43b",
        turn_id=turn_id,
        agent_id="api_agent_01",
        agent_number=1,
        owned_symbols=configured_symbols,
        owned_symbol=symbol,
        current_market_context={"ETHUSDT": {"price": 2000}},
        portfolio_state={"mode": "testnet"},
        own_positions_orders={"positions": [], "orders": []},
        peer_publications=[{"agent_id": "cli_agent_01", "summary": "risk stable"}],
        instruction_versions={"manifest": instruction},
        instruction_version=instruction,
        current_checkpoint_summary="Checkpoint is bounded and current.",
        recent_private_reflection_summaries=["Recent reflection summary only."],
        available_tools=tools or [],
        deadline="2099-01-01T00:00:00+00:00",
        current_collective_state_version=version,
    )


def response_payload(ctx: TradingTurnContext, **updates):
    payload = {
        "action": "WAIT",
        "agent_id": ctx.agent_id,
        "session_id": ctx.session_id,
        "turn_id": ctx.turn_id,
        "based_on_collective_version": ctx.current_collective_state_version,
        "instruction_version": ctx.instruction_version,
        "owned_symbol": ctx.owned_symbol,
        "rationale_summary": "No valid setup is present.",
        "requested_tool": "none",
        "confidence": 0.12,
        "payload": {},
    }
    payload.update(updates)
    return payload


def cli_context(*, turn_id: str = "turn-1") -> TradingTurnContext:
    return context(
        turn_id=turn_id,
        symbol="XRPUSDT",
        owned_symbols=["XRPUSDT", "BNBUSDT"],
    ).model_copy(
        update={
            "agent_id": "cli_agent_01",
            "agent_number": 2,
            "owned_symbols": ["XRPUSDT", "BNBUSDT"],
            "owned_symbol": "XRPUSDT",
        }
    )


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


def api_response(data, *, usage=True):
    result = {"choices": [{"message": {"content": json.dumps(data)}}]}
    if usage:
        result["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    return result


def run(coro):
    return asyncio.run(coro)


def test_response_schema_allows_only_declared_actions_and_requires_metadata():
    ctx = context(tools=[])
    response = TradingResponse.model_validate(response_payload(ctx))
    assert response.action == "WAIT"
    assert response.agent_id == "api_agent_01"
    with pytest.raises(ValueError):
        TradingResponse.model_validate(response_payload(ctx, action="BUY", requested_tool="none"))
    with pytest.raises(ValueError):
        TradingResponse.model_validate(response_payload(ctx, action="REQUEST_ORDER", requested_tool="none"))


def test_runtime_factory_has_no_kind_or_provider_fallback():
    api_agent = api_config()
    runtime = build_trading_agent_runtime(
        api_agent,
        provider_config=DeepSeekConfig(api_key="test-only-key"),
        client=FakeClient([]),
    )
    assert runtime.runtime_kind == "api"
    with pytest.raises(ValueError, match="provider configuration"):
        build_trading_agent_runtime(api_agent)


def test_context_is_bounded_and_does_not_embed_full_private_memory():
    ctx = context()
    large = ctx.model_copy(update={"recent_private_reflection_summaries": ["x" * 50000]})
    compact = large.compact_payload(max_chars=1000)
    assert compact["recent_private_reflection_summaries"] == []
    assert "x" * 10000 not in json.dumps(compact)


def test_api_runtime_uses_configured_model_and_token_usage():
    ctx = context(tools=[])
    fake = FakeClient([api_response(response_payload(ctx))])
    runtime = OpenAICompatibleTradingAgentRuntime(
        api_config(),
        DeepSeekConfig(api_key="test-only-key", model="configured-provider-model"),
        client=fake,
    )
    health = run(runtime.start_session(ctx.session_id))
    result = run(runtime.submit_turn(ctx))
    assert health.state == "READY"
    assert result.provider_state == "OK"
    assert result.token_usage is not None
    assert fake.chat.completions.calls[0]["model"] == "configured-provider-model" or fake.chat.completions.calls[0]["model"] == "deepseek-v4-pro"
    assert "test-only-key" not in json.dumps(fake.chat.completions.calls[0]["messages"])
    run(runtime.shutdown())


def test_api_retry_and_explicit_provider_failure():
    ctx = context()
    fake = FakeClient([RuntimeError("transient"), api_response(response_payload(ctx))])
    runtime = OpenAICompatibleTradingAgentRuntime(
        api_config(retry_count=1),
        DeepSeekConfig(api_key="test-only-key"),
        client=fake,
    )
    run(runtime.start_session(ctx.session_id))
    result = run(runtime.submit_turn(ctx))
    assert result.provider_state == "OK"
    assert len(fake.chat.completions.calls) == 2

    missing = OpenAICompatibleTradingAgentRuntime(api_config(), DeepSeekConfig(api_key=""))
    blocked = run(missing.start_session(ctx.session_id))
    failure = run(missing.submit_turn(ctx))
    assert blocked.state == "BLOCKED_MISSING_PROVIDER_CREDENTIAL"
    assert failure.error_code == "MISSING_PROVIDER_CREDENTIAL"


def test_api_timeout_and_cancellation():
    async def slow(**_kwargs):
        await asyncio.sleep(10)

    ctx = context()
    fake = FakeClient([])
    fake.chat.completions.create = slow
    runtime = OpenAICompatibleTradingAgentRuntime(
        api_config(timeout=1), DeepSeekConfig(api_key="test-only-key"), client=fake
    )
    async def cancellable(**_kwargs):
        await asyncio.sleep(10)

    fake.chat.completions.create = cancellable
    async def cancel_flow():
        await runtime.start_session(ctx.session_id)
        # First prove the explicit timeout state in the same event loop.
        fake.chat.completions.create = slow
        result = await runtime.submit_turn(ctx)
        assert result.error_code == "PROVIDER_TIMEOUT"
        fake.chat.completions.create = cancellable
        task = asyncio.create_task(runtime.submit_turn(context(turn_id="turn-cancel")))
        await asyncio.sleep(0.15)
        assert await runtime.cancel_turn("turn-cancel") is True
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await runtime.health()).state == "CANCELLED"
    run(cancel_flow())


@pytest.mark.parametrize(
    "data,expected",
    [
        ("not-json", "MALFORMED_JSON"),
        ({"action": "WAIT", "requested_tool": "request_order"}, "MALFORMED_STRUCTURED_RESPONSE"),
    ],
)
def test_api_rejects_malformed_structured_output(data, expected):
    ctx = context()
    if isinstance(data, str):
        response = {"choices": [{"message": {"content": data}}]}
    else:
        response = api_response({**response_payload(ctx), **data})
    fake = FakeClient([response])
    runtime = OpenAICompatibleTradingAgentRuntime(
        api_config(), DeepSeekConfig(api_key="test-only-key"), client=fake
    )
    run(runtime.start_session(ctx.session_id))
    assert run(runtime.submit_turn(ctx)).error_code == expected


def test_api_rejects_wrong_symbol_stale_collective_and_unauthorized_tool():
    ctx = context(tools=["request_order"])
    wrong_symbol = response_payload(ctx, owned_symbol="BNBUSDT")
    stale = response_payload(ctx, based_on_collective_version="collective-old")
    unauthorized_tool = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "execute_shell", "arguments": "{}"}}
                    ]
                }
            }
        ]
    }
    for response, expected in (
        (api_response(wrong_symbol), "WRONG_SYMBOL_REJECTION"),
        (api_response(stale), "STALE_COLLECTIVE_VERSION"),
        (unauthorized_tool, "UNAUTHORIZED_TOOL"),
    ):
        runtime = OpenAICompatibleTradingAgentRuntime(
            api_config(), DeepSeekConfig(api_key="test-only-key"), client=FakeClient([response])
        )
        run(runtime.start_session(ctx.session_id))
        assert run(runtime.submit_turn(ctx)).error_code == expected


def _write_cli(tmp_path: Path, mode: str = "valid") -> Path:
    script = tmp_path / "restricted_agent.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json, sys, time
            for line in sys.stdin:
                request = json.loads(line)
                if request.get('type') == 'shutdown':
                    break
                if request.get('type') == 'turn':
                    if {mode!r} == 'corrupt':
                        print('not-json', flush=True)
                        continue
                    if {mode!r} == 'timeout':
                        time.sleep(10)
                        continue
                    if {mode!r} == 'crash':
                        sys.exit(3)
                    response_id = 'duplicate' if {mode!r} == 'duplicate' else request['turn_id']
                    print(json.dumps({{
                        'response_id': response_id,
                        'turn_id': request['turn_id'],
                        'action': 'WAIT',
                        'agent_id': request['agent_id'],
                        'session_id': request['session_id'],
                        'based_on_collective_version': request['context']['current_collective_state_version'],
                        'instruction_version': request['context']['instruction_version'],
                        'owned_symbol': request['context']['owned_symbol'],
                        'rationale_summary': 'CLI has no valid setup.',
                        'requested_tool': 'none',
                        'confidence': 0.2,
                        'payload': {{}},
                    }}), flush=True)
            """
        ),
        encoding="utf-8",
    )
    return script


def cli_runtime(tmp_path: Path, mode: str = "valid", timeout: int = 2):
    script = _write_cli(tmp_path, mode)
    cfg = cli_config(timeout=timeout)
    return RestrictedCLITradingAgentRuntime(
        cfg,
        command=[sys.executable, str(script)],
        working_dir=tmp_path,
        approved_paths=[tmp_path],
    )


def test_cli_json_protocol_heartbeat_and_clean_shutdown(tmp_path):
    runtime = cli_runtime(tmp_path)
    async def flow():
        health = await runtime.start_session("session-p43b")
        result = await runtime.submit_turn(cli_context())
        assert health.state == "READY"
        assert result.action == "WAIT"
        assert result.response_id == "turn-1"
        assert (await runtime.health()).last_heartbeat is not None
        await runtime.shutdown()
        assert (await runtime.health()).clean_shutdown is True
    run(flow())


def test_cli_missing_installation_and_forbidden_command_are_blocked(tmp_path):
    missing = RestrictedCLITradingAgentRuntime(cli_config())
    assert run(missing.start_session("session-p43b")).state == "BLOCKED_CLI_NOT_CONFIGURED"
    forbidden = RestrictedCLITradingAgentRuntime(
        cli_config(), command=["git", "status"], working_dir=tmp_path, approved_paths=[tmp_path]
    )
    assert run(forbidden.start_session("session-p43b")).state == "BLOCKED_CLI_FORBIDDEN_EXECUTABLE"


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("corrupt", "CORRUPTED_CLI_RESPONSE"),
        ("timeout", "CLI_TURN_TIMEOUT"),
        ("crash", "CLI_PROCESS_CRASH"),
    ],
)
def test_cli_rejects_corrupt_timeout_and_crashed_process(tmp_path, mode, expected):
    runtime = cli_runtime(tmp_path, mode=mode, timeout=1)
    async def flow():
        await runtime.start_session("session-p43b")
        assert (await runtime.submit_turn(cli_context())).error_code == expected
        await runtime.shutdown()
    run(flow())


def test_cli_duplicate_response_rejected(tmp_path):
    runtime = cli_runtime(tmp_path, mode="duplicate")
    async def flow():
        await runtime.start_session("session-p43b")
        first = await runtime.submit_turn(cli_context())
        second = await runtime.submit_turn(cli_context(turn_id="turn-2"))
        assert first.action == "WAIT"
        assert second.error_code == "DUPLICATE_RESPONSE"
        await runtime.shutdown()
    run(flow())


def test_cli_working_directory_outside_approved_paths_is_blocked(tmp_path):
    approved = tmp_path / "approved"
    outside = tmp_path / "outside"
    approved.mkdir()
    outside.mkdir()
    script = _write_cli(approved)
    runtime = RestrictedCLITradingAgentRuntime(
        cli_config(),
        command=[sys.executable, str(script)],
        working_dir=outside,
        approved_paths=[approved],
    )
    assert run(runtime.start_session("session-p43b")).state == "BLOCKED_CLI_WORKING_DIR_OUTSIDE_APPROVED_PATH"


def test_source_has_no_exchange_or_repository_execution_imports():
    source = Path(__file__).resolve().parents[1] / "src/deepseek_terminal_agent/sessions/trading_agent_runtime.py"
    text = source.read_text(encoding="utf-8")
    assert "ExchangeACL" not in text
    assert "subprocess.run" not in text
    assert "git checkout" not in text
