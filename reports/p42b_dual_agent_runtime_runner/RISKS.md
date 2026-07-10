# System and Gating Risks

This document highlights technical risks and caveats of the P42 Dual-Agent Runner.

---

## 1. Divergences in Execution Speeds
* **Risk**: The API agent and CLI agent run on separate cadences and asynchronous loop schedules. Staggering ensures they start cleanly, but execution speed differences could lead to overlapping/competing order requests if FSM latencies spike.
* **Mitigation**: The runner rate limits the execution loops based on maximum pending commands and minimum seconds between orders.

---

## 2. Event Congestion on Wakeups
* **Risk**: Listening to the FSM emit stream hooks into a central bottleneck. If the FSM emits a burst of `ORDER_RESULT` or `POSITION_UPDATE` events during high volatility, the supervisor could receive concurrent wakeups, causing high CPU/event usage.
* **Mitigation**: Events wakeups use non-blocking `asyncio.Event` flag setting which is idempotent (calling `set()` multiple times on a set flag has no extra cost).

---

## 3. Crash Recovery and State Consistency
* **Risk**: The runner avoids restarting agents automatically when they crash, preventing duplicate command issues. However, if the supervisor itself restarts, there is a risk of losing the current session context if the state files are corrupted during crash writes.
* **Mitigation**: The runner implements atomic JSON writing for persisting session/process health states to `.agent_memory/`.
