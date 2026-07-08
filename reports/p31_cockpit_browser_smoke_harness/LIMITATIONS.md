# Limitations

- Browser click automation is not active because Python Playwright and Selenium are not installed in this environment.
- The harness performs an HTTP-equivalent session creation smoke rather than clicking `#new-session-btn`.
- The harness starts a real local FastAPI dashboard process, but it does not test Docker compose startup.
- The temporary `.agent_memory` directory is cleaned up by the OS temp-directory context after the test.
- The harness verifies session creation only; it does not send messages, inspect model calls, or test LLM/provider behavior.

## Browser Upgrade Path

If Python Playwright or Selenium becomes available, add a second test path that:

- opens `/chat`
- waits for `#new-session-btn`
- clicks it
- observes the `POST /chat/sessions` network result
- verifies the same temp `.agent_memory/sessions/<id>/session.dsstate.json`

Keep the HTTP fallback as the default safe path.
