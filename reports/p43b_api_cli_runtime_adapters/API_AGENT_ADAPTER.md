# API Agent Adapter

`OpenAICompatibleTradingAgentRuntime` consumes `AgentRuntimeConfig.provider/model/retry_count/response_timeout_sec` and `DeepSeekConfig.api_key/base_url`. The configured model is passed unchanged; no fallback model is selected.

Behavior:

- async OpenAI-compatible `chat.completions.create` call;
- deadline enforced by `response_timeout_sec`;
- exactly `retry_count + 1` attempts;
- task cancellation propagates as `CancelledError` and records cancellation health;
- usage maps to `prompt_tokens`, `completion_tokens`, `total_tokens`;
- content must be one JSON object;
- at most one tool call is accepted, and only registered trading tools are accepted;
- provider errors become sanitized `PROVIDER_FAILURE` responses; response bodies and credentials are not logged;
- stale collective version, stale instruction version, wrong symbol, identity mismatch, malformed JSON, and unauthorized tool are rejected.

Live API smoke was not run because no local API credential was present.

