"""Agent loop: send messages → process tool calls → iterate → final answer.

The loop:
  1. Prepends system prompt + conversation history
  2. Sends to DeepSeek Chat Completions
  3. If the model responds with tool_calls → executes each, appends results, repeats
  4. If the model responds with a final message → returns it
  5. If max_iterations reached → raises MaxIterationsError (fail-closed)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .config import Settings
from .deepseek_client import DeepSeekClient
from .logging_utils import RunLogger
from .terminal_tool import TOOL_SCHEMA, TerminalExecutor


class MaxIterationsError(RuntimeError):
    """Raised when the agent exhausts max_iterations without a final answer."""


def _load_system_prompt(path: str) -> str:
    p = Path(path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    # Inline fallback — used in tests and when path is not resolved
    return (
        "You are a coding/terminal agent. Use the terminal_exec tool to explore "
        "and modify the repository. Always investigate before modifying. "
        "Never fabricate command output. Report findings honestly. "
        "End every task with a structured Final Report."
    )


class AgentLoop:
    def __init__(
        self,
        settings: Settings,
        client: DeepSeekClient,
        executor: TerminalExecutor,
        logger: RunLogger,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> None:
        self.settings = settings
        self.client = client
        self.executor = executor
        self.logger = logger
        self.dry_run = dry_run
        self.verbose = verbose
        self.system_prompt = _load_system_prompt(
            settings.agent.system_prompt_path)
        # Multi-turn history: user + assistant messages (without tool call internals)
        self.history: list[dict[str, Any]] = []

    def run(self, user_message: str) -> str:
        """Run one user request through the agent loop. Returns final assistant text."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})
        self.logger.log_message({"role": "user", "content": user_message})

        max_iter = self.settings.agent.max_iterations

        for iteration in range(max_iter):
            if self.verbose:
                print(
                    f"[AGENT] iteration {iteration + 1}/{max_iter}",
                    file=sys.stderr,
                )

            response = self.client.chat_completions(
                # snapshot: prevents mock capturing post-call mutations
                messages=list(messages),
                tools=[TOOL_SCHEMA],
            )

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            msg = choice.message

            # Build a JSON-serialisable message dict for history/logging
            msg_dict: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            # DeepSeek thinking mode: reasoning_content MUST be passed back in
            # subsequent turns or the API returns 400 invalid_request_error.
            reasoning_content = getattr(msg, "reasoning_content", None)
            if isinstance(reasoning_content, str) and reasoning_content:
                msg_dict["reasoning_content"] = reasoning_content
            if msg.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(msg_dict)
            self.logger.log_message(msg_dict)

            # ── Final answer ──────────────────────────────────────────────────
            if finish_reason == "stop" or not msg.tool_calls:
                final = msg.content or ""
                # Keep condensed history for multi-turn (no tool internals)
                self.history.extend([
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": final},
                ])
                return final

            # ── Tool calls ────────────────────────────────────────────────────
            for tc in msg.tool_calls:
                tool_result = self._dispatch_tool(tc)

                tool_msg: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result),
                }
                messages.append(tool_msg)
                self.logger.log_message(tool_msg)

        raise MaxIterationsError(
            f"Agent reached max_iterations={max_iter} without a final answer. "
            f"Partial run saved to: {self.logger.run_url()}"
        )

    def _dispatch_tool(self, tc) -> dict[str, Any]:
        """Execute a single tool call and return the result dict."""
        if tc.function.name != "terminal_exec":
            return {
                "ok": False,
                "error": f"Unknown tool: '{tc.function.name}'. Only 'terminal_exec' is available.",
            }

        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError as exc:
            return {"ok": False, "error": f"Invalid JSON in tool arguments: {exc}"}

        cmd = args.get("cmd", "")
        cwd = args.get("cwd")
        timeout_sec = args.get("timeout_sec")

        return self.executor.execute(cmd=cmd, cwd=cwd, timeout_sec=timeout_sec)
