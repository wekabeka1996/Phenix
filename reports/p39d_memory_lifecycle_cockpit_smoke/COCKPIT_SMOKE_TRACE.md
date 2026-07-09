# Cockpit Smoke Trace

FACTS:
- Command: `python -m pytest tools/deepseek-terminal-agent/tests/test_agent_trading_memory.py tools/deepseek-terminal-agent/tests/test_memory_lifecycle_cockpit_smoke.py`
- Result: `6 passed in 0.62s`.
- Command: `python -m pytest tools/deepseek-terminal-agent/tests/test_agent_event_api.py tools/deepseek-terminal-agent/tests/test_dashboard_chat_app.py`
- Result: `14 passed in 0.56s`.

Smoke path covered:
- Session create.
- Agent identity attach.
- Instruction ACK append.
- Agent rationale event write.
- Memory append/read.
- FSM decision review append.
- Compact summary generation.
- Next-session carryover markdown generation.
- Subagent manager status read.
- No exchange submission from Cockpit route responses.

INFERENCES:
- Cockpit runtime surfaces needed for P39D are callable without exchange access.

ASSUMPTIONS:
- FastAPI TestClient route exercise is sufficient Cockpit runtime smoke for this task.

UNKNOWNS:
- Browser UI click proof was not collected.
