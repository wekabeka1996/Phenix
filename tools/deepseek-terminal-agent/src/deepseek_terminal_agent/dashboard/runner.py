"""Dashboard runner — background jobs, live output, and recent-run persistence."""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from ..logging_utils import redact


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_MODEL = "waiting_model"
    TOOL_CALL = "tool_call"
    EXECUTING_COMMAND = "executing_command"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = {
    RunStatus.SUCCEEDED.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
}


_ITERATION_RE = re.compile(r"\[AGENT\]\s+iteration\s+(\d+)/(\d+)")
_RUN_DIR_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:\\|/)?[^\s]*\.agent_runs[^\s]*)")


@dataclass
class RunEvent:
    ts: str
    run_id: str
    type: str
    phase: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResult:
    run_id: str
    prompt: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    created_at: str
    run_dir: Optional[str]
    status: str = RunStatus.SUCCEEDED.value
    finished_at: Optional[str] = None


@dataclass
class _RunState:
    run_id: str
    prompt: str
    created_at: str
    created_monotonic: float
    status: RunStatus = RunStatus.QUEUED
    current_phase: str = RunStatus.QUEUED.value
    latest_event: str = "Queued"
    started_at: Optional[str] = None
    started_monotonic: Optional[float] = None
    finished_at: Optional[str] = None
    finished_monotonic: Optional[float] = None
    duration_ms: int = 0
    exit_code: Optional[int] = None
    error: Optional[str] = None
    run_dir: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    truncated: bool = False
    events: list[RunEvent] = field(default_factory=list)
    process: Optional[subprocess.Popen[str]] = None
    thread: Optional[threading.Thread] = None
    lock: threading.RLock = field(default_factory=threading.RLock)
    cancel_requested: bool = False
    cancel_requested_monotonic: Optional[float] = None
    conversation_offset: int = 0
    terminal_offset: int = 0
    summary_emitted: bool = False
    seen_tool_calls: set[str] = field(default_factory=set)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate_preview(text: str, max_chars: int = 240) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


def _append_limited(existing: str, chunk: str, limit: int) -> tuple[str, bool]:
    merged = existing + chunk
    if len(merged) <= limit:
        return merged, False
    return merged[-limit:], True


def _safe_json_loads(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if isinstance(value, dict):
        return value
    return {}


def _extract_run_dir_from_text(text: str) -> Optional[str]:
    match = _RUN_DIR_RE.search(text)
    if not match:
        return None
    candidate = match.group("path").strip(".,;:[]()")
    return candidate or None


class DashboardRunner:
    def __init__(
        self,
        *,
        log_dir: str,
        max_prompt_chars: int = 12000,
        max_output_chars: int = 30000,
        recent_runs_limit: int = 20,
        poll_interval_sec: float = 0.2,
        command_factory: Optional[Callable[[str], list[str]]] = None,
        popen_factory: Optional[Callable[..., subprocess.Popen[str]]] = None,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_prompt_chars = max_prompt_chars
        self.max_output_chars = max_output_chars
        self.recent_runs_limit = recent_runs_limit
        self.poll_interval_sec = poll_interval_sec
        self._command_factory = command_factory or self._default_command_factory
        self._popen_factory = popen_factory or subprocess.Popen
        self._runs: dict[str, _RunState] = {}
        self._lock = threading.RLock()
        self._claimed_run_dirs: set[str] = set()

    def create_run(self, prompt: str) -> dict[str, Any]:
        safe_prompt = redact(prompt)
        if len(safe_prompt) > self.max_prompt_chars:
            raise ValueError(
                f"Prompt too long: {len(safe_prompt)} chars > max {self.max_prompt_chars}. "
                "Shorten the prompt and try again."
            )

        run_id = uuid.uuid4().hex[:12]
        state = _RunState(
            run_id=run_id,
            prompt=safe_prompt,
            created_at=_utc_now_iso(),
            created_monotonic=time.monotonic(),
        )
        self._append_event(
            state,
            event_type="status",
            phase=RunStatus.QUEUED.value,
            message="Queued",
            metadata={"status": RunStatus.QUEUED.value},
        )
        thread = threading.Thread(
            target=self._run_job, args=(state,), daemon=True)
        state.thread = thread
        with self._lock:
            self._runs[run_id] = state
        thread.start()
        return self.get_status(run_id)

    def get_status(self, run_id: str) -> dict[str, Any]:
        state = self._get_state(run_id)
        with state.lock:
            duration_ms = self._duration_ms(state)
            return {
                "run_id": state.run_id,
                "prompt": state.prompt,
                "status": state.status.value,
                "created_at": state.created_at,
                "started_at": state.started_at,
                "finished_at": state.finished_at,
                "duration_ms": duration_ms,
                "exit_code": state.exit_code,
                "current_phase": state.current_phase,
                "latest_event": state.latest_event,
                "error": state.error,
                "run_dir": state.run_dir,
            }

    def get_output(self, run_id: str) -> dict[str, Any]:
        state = self._get_state(run_id)
        with state.lock:
            return {
                "run_id": state.run_id,
                "status": state.status.value,
                "output": state.output,
                "stdout": state.stdout,
                "stderr": state.stderr,
                "truncated": state.truncated,
                "run_dir": state.run_dir,
            }

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        state = self._get_state(run_id)
        with state.lock:
            return [asdict(event) for event in state.events]

    def cancel(self, run_id: str) -> bool:
        state = self._get_state(run_id)
        with state.lock:
            if state.status.value in TERMINAL_STATUSES:
                return False
            state.cancel_requested = True
            state.cancel_requested_monotonic = time.monotonic()
            state.latest_event = "Cancellation requested"
            proc = state.process
        self._append_event(
            state,
            event_type="status",
            phase=state.current_phase,
            message="Cancellation requested",
            metadata={"status": state.status.value},
        )
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        return True

    def list_runs(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        effective_limit = limit or self.recent_runs_limit
        with self._lock:
            active = [self.get_status(run_id) for run_id in self._runs]
        persisted = load_recent_runs(str(self.log_dir), limit=effective_limit)
        merged: dict[str, dict[str, Any]] = {}
        for record in persisted:
            record = dict(record)
            record.setdefault("status", self._persisted_status(record))
            record.setdefault("current_phase", record["status"])
            record.setdefault("latest_event", record["status"])
            merged[record["run_id"]] = record
        for record in active:
            merged[record["run_id"]] = record
        runs = sorted(
            merged.values(),
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )
        return runs[:effective_limit]

    def _run_job(self, state: _RunState) -> None:
        existing_dirs = {path.name for path in self._list_log_dirs()}
        self._transition(
            state,
            status=RunStatus.RUNNING,
            phase=RunStatus.RUNNING.value,
            latest_event="Starting agent process",
        )
        try:
            proc = self._popen_factory(
                self._command_factory(state.prompt),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except Exception as exc:  # noqa: BLE001
            self._fail_run(state, f"Failed to start agent process: {exc}")
            return

        with state.lock:
            state.process = proc
        self._transition(
            state,
            status=RunStatus.RUNNING,
            phase=RunStatus.WAITING_MODEL.value,
            latest_event="Waiting for model response",
        )

        readers = self._start_stream_readers(state, proc)

        try:
            while True:
                self._discover_run_dir(state, existing_dirs)
                self._consume_run_logs(state)
                if state.cancel_requested and proc.poll() is None:
                    cancel_age = time.monotonic() - (state.cancel_requested_monotonic or time.monotonic())
                    if cancel_age >= 2.0:
                        try:
                            proc.kill()
                        except OSError:
                            pass
                if proc.poll() is not None:
                    break
                time.sleep(self.poll_interval_sec)
        except Exception as exc:  # noqa: BLE001
            self._fail_run(state, f"Dashboard runner error: {exc}")
            return
        finally:
            self._join_readers(readers)

        self._transition(
            state,
            status=RunStatus.RUNNING,
            phase=RunStatus.FINALIZING.value,
            latest_event="Finalizing run",
        )
        self._discover_run_dir(state, existing_dirs)
        self._consume_run_logs(state, final=True)
        self._emit_summary_if_available(state)

        exit_code = proc.wait()
        if state.cancel_requested:
            status = RunStatus.CANCELLED
            latest_event = "Run cancelled"
        elif exit_code == 0:
            status = RunStatus.SUCCEEDED
            latest_event = "Run completed successfully"
        else:
            status = RunStatus.FAILED
            latest_event = f"Run failed with exit code {exit_code}"

        self._transition(
            state,
            status=status,
            phase=status.value,
            latest_event=latest_event,
            exit_code=exit_code,
            finish=True,
        )
        append_dashboard_run(str(self.log_dir), self._result_from_state(state))

    def _default_command_factory(self, prompt: str) -> list[str]:
        return ["deepseek-agent", "--verbose", "run", prompt]

    def _get_state(self, run_id: str) -> _RunState:
        with self._lock:
            state = self._runs.get(run_id)
        if state is None:
            raise KeyError(run_id)
        return state

    def _list_log_dirs(self) -> list[Path]:
        if not self.log_dir.exists():
            return []
        return [path for path in self.log_dir.iterdir() if path.is_dir()]

    def _discover_run_dir(self, state: _RunState, existing_dirs: set[str]) -> None:
        with state.lock:
            if state.run_dir:
                return
        candidates = sorted(self._list_log_dirs(),
                            key=lambda path: path.stat().st_mtime)
        for candidate in candidates:
            if candidate.name in existing_dirs:
                continue
            candidate_str = str(candidate)
            with self._lock:
                if candidate_str in self._claimed_run_dirs:
                    continue
                self._claimed_run_dirs.add(candidate_str)
            with state.lock:
                state.run_dir = candidate_str
                state.latest_event = f"Run logs: {candidate_str}"
            self._append_event(
                state,
                event_type="status",
                phase=state.current_phase,
                message=f"Run logs: {candidate_str}",
                metadata={"run_dir": candidate_str,
                          "status": state.status.value},
            )
            return

    def _start_stream_readers(
        self,
        state: _RunState,
        proc: subprocess.Popen[str],
    ) -> list[threading.Thread]:
        threads: list[threading.Thread] = []
        for stream_name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if stream is None:
                continue
            thread = threading.Thread(
                target=self._read_stream,
                args=(state, stream_name, stream),
                daemon=True,
            )
            thread.start()
            threads.append(thread)
        return threads

    def _join_readers(self, threads: list[threading.Thread]) -> None:
        for thread in threads:
            thread.join(timeout=1.0)

    def _read_stream(self, state: _RunState, stream_name: str, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                self._handle_process_line(state, stream_name, line)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _handle_process_line(self, state: _RunState, stream_name: str, line: str) -> None:
        safe_line = redact(line)
        self._append_output(state, stream_name, safe_line)

        stripped = safe_line.strip()
        if not stripped:
            return

        iteration_match = _ITERATION_RE.search(stripped)
        if iteration_match:
            iteration = int(iteration_match.group(1))
            max_iterations = int(iteration_match.group(2))
            message = f"Agent iteration {iteration}/{max_iterations}"
            self._transition(
                state,
                status=RunStatus.RUNNING,
                phase=RunStatus.WAITING_MODEL.value,
                latest_event=message,
            )
            return

        if "Run logs:" in stripped:
            candidate = _extract_run_dir_from_text(stripped)
            if candidate:
                with state.lock:
                    state.run_dir = candidate
                self._append_event(
                    state,
                    event_type="status",
                    phase=state.current_phase,
                    message=f"Run logs: {candidate}",
                    metadata={"run_dir": candidate,
                              "status": state.status.value},
                )
            return

        if stream_name == "stderr" and ("[ERROR]" in stripped or "[MAX ITERATIONS]" in stripped):
            self._append_event(
                state,
                event_type="error",
                phase=state.current_phase,
                message=_truncate_preview(stripped),
                metadata={"stream": stream_name},
            )

    def _consume_run_logs(self, state: _RunState, final: bool = False) -> None:
        with state.lock:
            run_dir = state.run_dir
        if not run_dir:
            return
        run_path = Path(run_dir)
        self._consume_conversation_log(state, run_path / "conversation.jsonl")
        self._consume_terminal_log(state, run_path / "terminal.log")
        if final:
            self._emit_summary_if_available(state)

    def _consume_conversation_log(self, state: _RunState, path: Path) -> None:
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            with state.lock:
                handle.seek(state.conversation_offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                with state.lock:
                    state.conversation_offset = handle.tell()
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._handle_conversation_record(state, record)

    def _handle_conversation_record(self, state: _RunState, record: dict[str, Any]) -> None:
        role = record.get("role")
        if role != "assistant":
            return

        content = redact(str(record.get("content") or "")).strip()
        if content:
            self._append_event(
                state,
                event_type="model_message",
                phase=RunStatus.WAITING_MODEL.value,
                message=_truncate_preview(content),
                metadata={"content_preview": _truncate_preview(
                    content, max_chars=400)},
            )

        tool_calls = record.get("tool_calls")
        if not isinstance(tool_calls, list):
            return

        for tool_call in tool_calls:
            call_id = str(tool_call.get("id") or "")
            if not call_id:
                continue
            with state.lock:
                if call_id in state.seen_tool_calls:
                    continue
                state.seen_tool_calls.add(call_id)
            function = tool_call.get("function") or {}
            tool_name = str(function.get("name") or "")
            arguments = _safe_json_loads(
                str(function.get("arguments") or "{}"))
            metadata: dict[str, Any] = {
                "tool_name": tool_name, "call_id": call_id}
            if "cwd" in arguments and arguments.get("cwd") not in (None, ""):
                metadata["cwd"] = redact(str(arguments.get("cwd")))
            if "timeout_sec" in arguments and arguments.get("timeout_sec") is not None:
                metadata["timeout_sec"] = arguments.get("timeout_sec")
            cmd = arguments.get("cmd")
            if cmd not in (None, ""):
                metadata["cmd"] = redact(str(cmd))

            self._transition(
                state,
                status=RunStatus.RUNNING,
                phase=RunStatus.TOOL_CALL.value,
                latest_event=f"Tool call: {tool_name}",
            )
            self._append_event(
                state,
                event_type="tool_call",
                phase=RunStatus.TOOL_CALL.value,
                message=f"Tool call: {tool_name}",
                metadata=metadata,
            )

            if cmd not in (None, ""):
                self._transition(
                    state,
                    status=RunStatus.RUNNING,
                    phase=RunStatus.EXECUTING_COMMAND.value,
                    latest_event=f"Running: {metadata['cmd']}",
                )
                self._append_event(
                    state,
                    event_type="command_start",
                    phase=RunStatus.EXECUTING_COMMAND.value,
                    message=f"Running: {metadata['cmd']}",
                    metadata=metadata,
                )

    def _consume_terminal_log(self, state: _RunState, path: Path) -> None:
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            with state.lock:
                handle.seek(state.terminal_offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                with state.lock:
                    state.terminal_offset = handle.tell()
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self._handle_terminal_record(state, record)

    def _handle_terminal_record(self, state: _RunState, record: dict[str, Any]) -> None:
        cmd = redact(str(record.get("cmd") or ""))
        exit_code = record.get("exit_code")
        timed_out = bool(record.get("timed_out"))
        metadata: dict[str, Any] = {
            "cmd": cmd,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "cwd": redact(str(record.get("cwd") or "")),
        }
        self._append_event(
            state,
            event_type="command_end",
            phase=RunStatus.EXECUTING_COMMAND.value,
            message=f"Command finished ({exit_code}): {cmd}",
            metadata=metadata,
        )

        stdout = redact(str(record.get("stdout") or ""))
        stderr = redact(str(record.get("stderr") or ""))
        if stdout:
            self._append_command_output(state, cmd, "stdout", stdout)
        if stderr:
            self._append_command_output(state, cmd, "stderr", stderr)
        if record.get("output_truncated"):
            self._append_event(
                state,
                event_type="command_output",
                phase=RunStatus.EXECUTING_COMMAND.value,
                message=f"Command output truncated: {cmd}",
                metadata={"cmd": cmd, "output_truncated": True},
            )
        self._transition(
            state,
            status=RunStatus.RUNNING,
            phase=RunStatus.WAITING_MODEL.value,
            latest_event=f"Command finished ({exit_code}): {cmd}",
        )

    def _append_command_output(self, state: _RunState, cmd: str, stream_name: str, text: str) -> None:
        block = f"\n$ {cmd}\n{text}"
        self._append_output(state, stream_name, block)
        self._append_event(
            state,
            event_type="command_output",
            phase=RunStatus.EXECUTING_COMMAND.value,
            message=f"{stream_name}: {_truncate_preview(text)}",
            metadata={
                "cmd": cmd,
                "stream": stream_name,
                "excerpt": _truncate_preview(text, max_chars=400),
            },
        )

    def _emit_summary_if_available(self, state: _RunState) -> None:
        with state.lock:
            if state.summary_emitted or not state.run_dir:
                return
            summary_path = Path(state.run_dir) / "summary.md"
        if not summary_path.exists():
            return
        content = redact(summary_path.read_text(encoding="utf-8")).strip()
        if not content:
            return
        with state.lock:
            state.summary_emitted = True
        self._append_event(
            state,
            event_type="final",
            phase=RunStatus.FINALIZING.value,
            message=_truncate_preview(content),
            metadata={"final_answer": content},
        )

    def _append_output(self, state: _RunState, stream_name: str, chunk: str) -> None:
        if not chunk:
            return
        with state.lock:
            if stream_name == "stdout":
                state.stdout, truncated_stdout = _append_limited(
                    state.stdout, chunk, self.max_output_chars)
            else:
                state.stderr, truncated_stdout = _append_limited(
                    state.stderr, chunk, self.max_output_chars)
            state.output, truncated_output = _append_limited(
                state.output, chunk, self.max_output_chars)
            state.truncated = state.truncated or truncated_stdout or truncated_output

    def _append_event(
        self,
        state: _RunState,
        *,
        event_type: str,
        phase: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        event = RunEvent(
            ts=_utc_now_iso(),
            run_id=state.run_id,
            type=event_type,
            phase=phase,
            message=redact(message),
            metadata=metadata or {},
        )
        with state.lock:
            state.events.append(event)

    def _transition(
        self,
        state: _RunState,
        *,
        status: RunStatus,
        phase: str,
        latest_event: str,
        exit_code: Optional[int] = None,
        error: Optional[str] = None,
        finish: bool = False,
    ) -> None:
        with state.lock:
            state.status = status
            state.current_phase = phase
            state.latest_event = redact(latest_event)
            if state.started_at is None and status != RunStatus.QUEUED:
                state.started_at = _utc_now_iso()
                state.started_monotonic = time.monotonic()
            if exit_code is not None:
                state.exit_code = exit_code
            if error is not None:
                state.error = redact(error)
            state.duration_ms = self._duration_ms(state)
            if finish:
                state.finished_at = _utc_now_iso()
                state.finished_monotonic = time.monotonic()
                state.duration_ms = self._duration_ms(state)
        self._append_event(
            state,
            event_type="status",
            phase=phase,
            message=latest_event,
            metadata={"status": status.value,
                      "exit_code": exit_code, "error": error},
        )

    def _duration_ms(self, state: _RunState) -> int:
        started = state.started_monotonic or state.created_monotonic
        finished = state.finished_monotonic or time.monotonic()
        return max(0, int((finished - started) * 1000))

    def _result_from_state(self, state: _RunState) -> RunResult:
        with state.lock:
            return RunResult(
                run_id=state.run_id,
                prompt=state.prompt,
                stdout=state.stdout,
                stderr=state.stderr,
                exit_code=state.exit_code if state.exit_code is not None else -1,
                duration_ms=self._duration_ms(state),
                created_at=state.created_at,
                run_dir=state.run_dir,
                status=state.status.value,
                finished_at=state.finished_at,
            )

    def _fail_run(self, state: _RunState, error_message: str) -> None:
        safe_error = redact(error_message)
        self._append_event(
            state,
            event_type="error",
            phase=RunStatus.FAILED.value,
            message=safe_error,
            metadata={},
        )
        self._transition(
            state,
            status=RunStatus.FAILED,
            phase=RunStatus.FAILED.value,
            latest_event=safe_error,
            exit_code=-1,
            error=safe_error,
            finish=True,
        )
        append_dashboard_run(str(self.log_dir), self._result_from_state(state))

    @staticmethod
    def _persisted_status(record: dict[str, Any]) -> str:
        if record.get("status") in TERMINAL_STATUSES:
            return str(record["status"])
        exit_code = record.get("exit_code")
        if exit_code == 0:
            return RunStatus.SUCCEEDED.value
        return RunStatus.FAILED.value


def run_agent(prompt: str, max_prompt_chars: int = 12000) -> RunResult:
    """Spawn ``deepseek-agent run <prompt>`` as a synchronous subprocess.

    - Validates prompt length.
    - Redacts secrets from stdout/stderr before returning.
    - Does NOT accept arbitrary shell commands — only the prompt string.
    """
    if len(prompt) > max_prompt_chars:
        raise ValueError(
            f"Prompt too long: {len(prompt)} chars > max {max_prompt_chars}. "
            "Shorten the prompt and try again."
        )

    run_id = uuid.uuid4().hex[:12]
    created_at = datetime.now(timezone.utc).isoformat()

    start = time.monotonic()
    try:
        proc = subprocess.run(
            ["deepseek-agent", "run", prompt],
            capture_output=True,
            text=True,
            timeout=600,  # hard cap: 10 min
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            run_id=run_id,
            prompt=prompt,
            stdout="",
            stderr="[DASHBOARD] Command timed out after 600 seconds.",
            exit_code=-1,
            duration_ms=600_000,
            created_at=created_at,
            run_dir=None,
            status=RunStatus.FAILED.value,
            finished_at=created_at,
        )

    duration_ms = int((time.monotonic() - start) * 1000)

    stdout = redact(proc.stdout or "")
    stderr = redact(proc.stderr or "")

    # Best-effort: extract run_dir from stderr (RunLogger prints it on MaxIterationsError)
    run_dir: Optional[str] = None
    for line in stderr.splitlines():
        if ".agent_runs" in line:
            # Extract the path segment that looks like a run dir
            for part in line.split():
                if ".agent_runs" in part:
                    run_dir = part.strip(".,;:")
                    break

    return RunResult(
        run_id=run_id,
        prompt=prompt,
        stdout=stdout,
        stderr=stderr,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        created_at=created_at,
        run_dir=run_dir,
        status=RunStatus.SUCCEEDED.value if proc.returncode == 0 else RunStatus.FAILED.value,
        finished_at=_utc_now_iso(),
    )


def append_dashboard_run(log_dir: str, result: RunResult) -> None:
    """Append run metadata to .agent_runs/dashboard_runs.jsonl."""
    runs_file = Path(log_dir) / "dashboard_runs.jsonl"
    runs_file.parent.mkdir(parents=True, exist_ok=True)
    record = asdict(result)
    # Truncate stored output to avoid huge JSONL files
    record["stdout"] = record["stdout"][:4000]
    record["stderr"] = record["stderr"][:2000]
    if "status" not in record or not record["status"]:
        record["status"] = RunStatus.SUCCEEDED.value if result.exit_code == 0 else RunStatus.FAILED.value
    with runs_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_recent_runs(log_dir: str, limit: int = 20) -> list[dict]:
    """Read dashboard_runs.jsonl and return the last ``limit`` entries (newest first)."""
    runs_file = Path(log_dir) / "dashboard_runs.jsonl"
    if not runs_file.exists():
        return []
    lines = runs_file.read_text(encoding="utf-8").splitlines()
    records: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and "status" not in record:
            record["status"] = RunStatus.SUCCEEDED.value if record.get(
                "exit_code") == 0 else RunStatus.FAILED.value
        records.append(record)
    return list(reversed(records[-limit:]))
