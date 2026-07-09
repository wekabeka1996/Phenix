# CLI Timer Runner Contract

## Specifications
- **Inspectable Wakeup Logs**: Every timer loop iteration wakeup event is logged via an inspectable `TimerTick` schema.
- **Bounded execution**: Loops must support strict boundaries (max iterations, max elapsed runtime seconds) and terminate cleanly. Infinite, un-bounded background daemon loops are prohibited.
- **Explicit intervals**: Sleep interval durations to the next scheduled memory refresh are dynamically calculated and capped.
- **Clock & Sleep Mockability**: Functions allow clock and sleep injection callbacks to permit deterministic, zero-delay unit testing.

## Data Schema (TimerTick Pydantic Model)
- `schema_version` (integer, default 1)
- `agent_id` (string, min_length=1)
- `agent_number` (integer, ge=1)
- `scheduled_at` (datetime)
- `woke_at` (datetime, defaults to current UTC time)
- `reason` (Literal["scheduled", "sos", "manual"])
- `context_version` (Optional[integer])

## Core Functions
- [TimerTick](file:///C:/Users/user/Phenix/p35e-cli-timer-runner-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py#L12): Pydantic validation schema.
- [compute_sleep_seconds(now, next_scheduled, max_sleep_seconds)](file:///C:/Users/user/Phenix/p35e-cli-timer-runner-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py#L25): Computes delay duration.
- [make_timer_tick(...)](file:///C:/Users/user/Phenix/p35e-cli-timer-runner-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py#L34): Instantiates `TimerTick` objects.
- [should_stop(started_at, now, max_runtime_seconds, max_iterations, iteration_count)](file:///C:/Users/user/Phenix/p35e-cli-timer-runner-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py#L48): Determines if loop boundaries are exceeded.
- [run_bounded_timer_loop(...)](file:///C:/Users/user/Phenix/p35e-cli-timer-runner-secondary-20260709/tools/deepseek-terminal-agent/src/deepseek_terminal_agent/sessions/agent_timer_runner.py#L65): Executes the bounded loop.
