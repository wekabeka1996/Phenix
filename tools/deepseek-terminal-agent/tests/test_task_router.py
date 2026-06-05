"""Tests for deterministic workbench task routing."""
from __future__ import annotations

from deepseek_terminal_agent.sessions.task_router import TaskRouter


def test_repo_search_routes_to_read_only_scout():
    router = TaskRouter()

    decision = router.route(
        user_message="Find where the dashboard is described and give an evidence pack. Do not change anything."
    )

    assert decision.task_type == "repo_search"
    assert decision.route == "orchestrated"
    assert decision.suggested_subagents[0].tool_policy == "read_only"


def test_test_request_routes_to_tests_only_runner():
    router = TaskRouter()

    decision = router.route(
        user_message="Run tests for deepseek-terminal-agent and give a short test report."
    )

    assert decision.task_type == "test_run"
    assert decision.route == "orchestrated"
    assert decision.suggested_subagents[0].tool_policy == "tests_only"


def test_log_scan_routes_to_log_scanner():
    router = TaskRouter()

    decision = router.route(
        user_message="Analyze metadata logs/order_log_v1.jsonl read-only and do not print the full file."
    )

    assert decision.task_type == "log_scan"
    assert decision.route == "orchestrated"
    assert decision.suggested_subagents[0].role == "LogScanner"


def test_plain_request_stays_direct():
    router = TaskRouter()

    decision = router.route(
        user_message="Summarize the current session state.")

    assert decision.task_type == "direct_answer"
    assert decision.route == "direct"


def test_mixed_audit_spawns_two_subagents():
    """Mixed prompt (EvidencePack + TestReport) routes to 'mixed' with two subagents."""
    router = TaskRouter()
    prompt = (
        "Проаналізуй deepseek-terminal-agent read-only. "
        "Знайди, як працюють dashboard /chat, session memory, subagents і context builder. "
        "Запусти релевантні тести тільки для цих модулів. "
        "Сформуй EvidencePack і TestReport, потім дай короткий фінальний висновок. "
        "Не змінюй код."
    )
    decision = router.route(user_message=prompt)

    assert decision.task_type == "mixed"
    assert decision.route == "orchestrated"
    assert len(decision.suggested_subagents) == 2
    roles = [s.role for s in decision.suggested_subagents]
    assert "ScoutAgent" in roles
    assert "TestScoutAgent" in roles
    policies = {s.role: s.tool_policy for s in decision.suggested_subagents}
    assert policies["ScoutAgent"] == "read_only"
    assert policies["TestScoutAgent"] == "tests_only"


def test_mixed_subagents_profile_strategies():
    router = TaskRouter()
    decision = router.route(user_message="EvidencePack and TestReport please.")
    assert decision.task_type == "mixed"
    scout = next(
        s for s in decision.suggested_subagents if s.role == "ScoutAgent")
    tester = next(
        s for s in decision.suggested_subagents if s.role == "TestScoutAgent")
    assert scout.profile_strategy == "flash_scout"
    assert tester.profile_strategy == "flash_fast"


def test_evidencepack_alone_stays_repo_search():
    """EvidencePack without TestReport → repo_search, not mixed."""
    router = TaskRouter()
    decision = router.route(
        user_message="Create an EvidencePack for this module.")
    assert decision.task_type == "repo_search"
    assert decision.route == "orchestrated"
    assert len(decision.suggested_subagents) == 1
