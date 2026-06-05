"""Deterministic task routing for bounded workbench orchestration."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .tool_policy import ToolPolicyName

TaskType = Literal[
    "direct_answer",
    "repo_search",
    "test_run",
    "doc_write",
    "log_scan",
    "mixed",
]
RouteMode = Literal["direct", "orchestrated"]
ProfileStrategy = Literal["current", "flash_scout", "flash_fast"]


class SuggestedSubagent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., min_length=1)
    task: str = Field(..., min_length=1)
    tool_policy: ToolPolicyName
    profile_strategy: ProfileStrategy = "flash_scout"
    reason: str = Field(..., min_length=1)


class TaskRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    route: RouteMode
    reason: str = Field(..., min_length=1)
    suggested_subagents: list[SuggestedSubagent] = Field(default_factory=list)


class TaskRouter:
    _LOG_SCAN_RE = re.compile(
        r"\b(log|logs|jsonl|metadata|order_log|read-only)\b"
    )
    _TEST_RE = re.compile(
        r"\b(pytest|test report|testreport|tests?|ruff|compileall|smoke)\b"
    )
    _DOC_RE = re.compile(
        r"\b(readme|operator note|operator guide|documentation|docs|how to use|guide)\b"
    )
    _SEARCH_RE = re.compile(
        r"\b(find|search|where|inspect|scan|evidence pack|evidencepack|read-only)\b"
    )
    # Mixed: explicit evidence + test keywords in the same prompt
    _EVIDENCE_RE = re.compile(
        r"\b(evidencepack|evidence.?pack|scout|evidenz)\b"
    )
    _TESTREPORT_RE = re.compile(
        r"\b(testreport|test.?report|testscout)\b"
    )

    def route(self, *, user_message: str) -> TaskRouteDecision:
        text = " ".join(str(user_message or "").lower().split())
        if self._looks_like_mixed(text):
            return TaskRouteDecision(
                task_type="mixed",
                route="orchestrated",
                reason="The request targets both evidence collection and test execution.",
                suggested_subagents=[
                    SuggestedSubagent(
                        role="ScoutAgent",
                        task=(
                            "Search the repository read-only and return a compact EvidencePack artifact: "
                            f"{user_message}"
                        ),
                        tool_policy="read_only",
                        profile_strategy="flash_scout",
                        reason="Collect file and command evidence read-only.",
                    ),
                    SuggestedSubagent(
                        role="TestScoutAgent",
                        task=(
                            "Run the relevant tests for dashboard, session memory, subagents and context builder. "
                            "Return a compact TestReport artifact. Do not edit any files. "
                            f"{user_message}"
                        ),
                        tool_policy="tests_only",
                        profile_strategy="flash_fast",
                        reason="Execute bounded validation and produce TestReport.",
                    ),
                ],
            )
        if self._looks_like_log_scan(text):
            return TaskRouteDecision(
                task_type="log_scan",
                route="orchestrated",
                reason="The request targets log metadata or read-only log inspection.",
                suggested_subagents=[
                    SuggestedSubagent(
                        role="LogScanner",
                        task=(
                            "Inspect the requested logs read-only and produce a compact evidence pack: "
                            f"{user_message}"
                        ),
                        tool_policy="read_only",
                        profile_strategy="flash_fast",
                        reason="Gather log metadata without printing full files.",
                    )
                ],
            )
        if self._looks_like_test_run(text):
            return TaskRouteDecision(
                task_type="test_run",
                route="orchestrated",
                reason="The request asks for test execution or a bounded validation report.",
                suggested_subagents=[
                    SuggestedSubagent(
                        role="TestRunner",
                        task=f"Run the requested bounded validation and return a compact test report: {user_message}",
                        tool_policy="tests_only",
                        profile_strategy="flash_fast",
                        reason="Use the tests-only tool policy for narrow validation.",
                    )
                ],
            )
        if self._looks_like_doc_write(text):
            return TaskRouteDecision(
                task_type="doc_write",
                route="orchestrated",
                reason="The request is documentation-oriented and benefits from read-only context gathering first.",
                suggested_subagents=[
                    SuggestedSubagent(
                        role="DocsScout",
                        task=f"Gather read-only documentation evidence before writing: {user_message}",
                        tool_policy="read_only",
                        profile_strategy="flash_scout",
                        reason="Collect repo facts before the parent model drafts documentation.",
                    )
                ],
            )
        if self._looks_like_repo_search(text):
            return TaskRouteDecision(
                task_type="repo_search",
                route="orchestrated",
                reason="The request is primarily repository discovery and evidence collection.",
                suggested_subagents=[
                    SuggestedSubagent(
                        role="ScoutAgent",
                        task=f"Search the repository read-only and return a compact evidence pack: {user_message}",
                        tool_policy="read_only",
                        profile_strategy="flash_scout",
                        reason="Collect file and command evidence before the parent answer.",
                    )
                ],
            )
        return TaskRouteDecision(
            task_type="direct_answer",
            route="direct",
            reason="The request is simple enough for a direct parent-session answer.",
        )

    def _looks_like_mixed(self, text: str) -> bool:
        has_evidence = bool(self._EVIDENCE_RE.search(text))
        has_testreport = bool(self._TESTREPORT_RE.search(text))
        return has_evidence and has_testreport

    def _looks_like_log_scan(self, text: str) -> bool:
        return bool(self._LOG_SCAN_RE.search(text) and ("log" in text or "jsonl" in text))

    def _looks_like_test_run(self, text: str) -> bool:
        return bool(self._TEST_RE.search(text))

    def _looks_like_doc_write(self, text: str) -> bool:
        return bool(self._DOC_RE.search(text))

    def _looks_like_repo_search(self, text: str) -> bool:
        return bool(self._SEARCH_RE.search(text))
