# CLI Trading Mode Contract

The CLI adapter speaks only `p43b-trading-json-v1` over stdin/stdout. A turn request contains identity and a bounded context; the response must be one JSON object containing a `response_id`, matching `turn_id`, and a validated `TradingResponse`.

Preflight blocks:

- missing `cli_command`;
- missing approved paths or working directory;
- working directory outside approved paths;
- missing approved paths;
- shell executables (`cmd`, PowerShell, bash, sh, git);
- shell metacharacters and command flags such as `-c`/`--command`;
- absolute script paths outside approved paths, except the explicit interpreter binary used to launch an approved script.

The child receives no repository tools, no shell API, no git command, and an environment with API key/secret/password/token variables removed. Stderr is discarded from the trading response path. Timeout terminates the process; shutdown sends a protocol shutdown frame and then terminates/kills if needed.

The canonical P42 YAML intentionally has `cli_command: null`; a real installed/configured CLI smoke is therefore blocked until an operator supplies an approved command and paths.

