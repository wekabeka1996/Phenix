"""DeepSeek API client — OpenAI-compatible Chat Completions.

Uses the official openai Python SDK with base_url pointing at DeepSeek's
OpenAI-compatible endpoint.  The API key is never written to logs.

Reasoning/thinking mode is passed via extra_body.  If the installed SDK version
or DeepSeek API version does not support the parameter, we fail fast with an
actionable message instead of silently ignoring the option.

To update the reasoning parameter name/structure, edit _reasoning_extra_body()
and the README section "Reasoning mode".
"""
from __future__ import annotations

import sys
from typing import Any, NoReturn, Optional

from .config import DeepSeekConfig
from .sessions.models import ModelProfile


class DeepSeekAPIError(RuntimeError):
    """Structured upstream API failure safe to surface in CLI and dashboard."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class DeepSeekTimeoutError(DeepSeekAPIError):
    """Raised when the upstream DeepSeek request exceeds the configured timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=504)


def _build_openai_client(cfg: DeepSeekConfig):
    try:
        from openai import OpenAI
    except ImportError as exc:
        print(
            "[ERROR] 'openai' package is not installed.\n"
            "  Run: pip install openai",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)


def legacy_profile_from_config(cfg: DeepSeekConfig) -> ModelProfile:
    """Map legacy CLI config to the richer per-turn ModelProfile contract."""
    return ModelProfile(
        profile_id="legacy-default",
        name="Legacy Default",
        model_id=cfg.model,
        thinking_type="enabled" if cfg.reasoning_enabled else "disabled",
        reasoning_effort=cfg.reasoning_effort,
        temperature=cfg.temperature,
        top_p=cfg.top_p,
        max_tokens=cfg.max_tokens,
        response_format="text",
        stream=False,
        tool_mode="auto",
        max_iterations=20,
        command_timeout_sec=120,
        max_command_output_chars=20000,
        context_budget_chars=800000,
        memory_atom_budget=8,
        recent_turns_budget=12,
        tool_output_budget_chars=60000,
    )


def build_chat_payload(
    *,
    messages: list[dict[str, Any]],
    model_profile: ModelProfile,
    tools: Optional[list[dict[str, Any]]] = None,
    stream: Optional[bool] = None,
) -> dict[str, Any]:
    """Build a DeepSeek chat payload with explicit thinking/tool semantics."""
    if not model_profile.model_id:
        raise ValueError("model_profile.model_id must be non-empty")

    payload: dict[str, Any] = {
        "model": model_profile.model_id,
        "messages": messages,
        "max_tokens": model_profile.max_tokens,
        "stream": model_profile.stream if stream is None else bool(stream),
    }

    extra_body: dict[str, Any] = {
        "thinking": {"type": model_profile.thinking_type},
    }

    if model_profile.thinking_type == "enabled":
        extra_body["reasoning_effort"] = model_profile.reasoning_effort
    else:
        payload["temperature"] = model_profile.temperature
        payload["top_p"] = model_profile.top_p

    if model_profile.response_format == "json_object":
        payload["response_format"] = {"type": "json_object"}

    if model_profile.tool_mode == "none":
        tools = None
    elif model_profile.tool_mode == "required":
        if not tools:
            raise ValueError("tool_mode='required' requires at least one tool")
        payload["tools"] = tools
        payload["tool_choice"] = "required"
    elif tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    payload["extra_body"] = extra_body
    return payload


class DeepSeekClient:
    """Thin wrapper around OpenAI SDK targeting the DeepSeek endpoint."""

    def __init__(self, cfg: DeepSeekConfig) -> None:
        self.cfg = cfg
        self._client = _build_openai_client(cfg)

    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        model_profile: Optional[ModelProfile] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        stream: Optional[bool] = None,
    ):
        """Call Chat Completions and return the response object.

        Raises SystemExit on unrecoverable errors (bad key, model not found,
        unsupported reasoning param) with a human-readable message.
        """
        profile = model_profile or legacy_profile_from_config(self.cfg)
        kwargs = build_chat_payload(
            messages=messages,
            model_profile=profile,
            tools=tools,
            stream=stream,
        )
        kwargs["timeout"] = self.cfg.request_timeout_sec

        try:
            return self._client.chat.completions.create(**kwargs)

        except TypeError as exc:
            msg = str(exc)
            if "extra_body" in msg or "reasoning" in msg.lower():
                raise DeepSeekAPIError(
                    "Reasoning parameters are unsupported by the installed openai SDK "
                    "version or this DeepSeek API endpoint. Set DEEPSEEK_REASONING_ENABLED=false, "
                    "upgrade openai, or update the DeepSeek reasoning parameter contract."
                ) from exc
            if "timeout" in msg.lower():
                raise DeepSeekAPIError(
                    "Request timeout is unsupported by the installed openai SDK version. "
                    "Upgrade openai to a version that supports per-request timeouts."
                ) from exc
            raise

        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            _handle_api_error(
                exc,
                profile.model_id,
                timeout_sec=self.cfg.request_timeout_sec,
            )

    def list_models(self) -> list[dict[str, Any]]:
        """Return the current DeepSeek model inventory from GET /models."""
        try:
            response = self._client.models.list()
        except Exception as exc:  # noqa: BLE001
            _handle_api_error(exc, self.cfg.model)

        raw_items = getattr(response, "data", response)
        normalized: list[dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                model_id = item.get("id")
                normalized.append(dict(item))
            else:
                model_id = getattr(item, "id", None)
                normalized.append(
                    {
                        "id": model_id,
                        "object": getattr(item, "object", None),
                        "created": getattr(item, "created", None),
                        "owned_by": getattr(item, "owned_by", None),
                    }
                )
            if not model_id:
                normalized.pop()
        return normalized


def _handle_api_error(exc: Exception, model: str, *, timeout_sec: int) -> NoReturn:
    """Normalize upstream API failures into typed runtime exceptions."""
    msg = str(exc)
    lowered = msg.lower()
    class_name = exc.__class__.__name__.lower()
    code = getattr(getattr(exc, "response", None), "status_code", None) or ""

    if "timeout" in class_name or "readtimeout" in class_name or "timed out" in lowered:
        raise DeepSeekTimeoutError(
            f"DeepSeek API request timed out after {timeout_sec}s while calling model '{model}'."
        ) from exc

    if "401" in msg or str(code) == "401" or "invalid_api_key" in msg.lower():
        raise DeepSeekAPIError(
            "DeepSeek API rejected the request with 401 Unauthorized. "
            "Check the configured DEEPSEEK_API_KEY."
        ) from exc

    if "404" in msg or str(code) == "404" or (
        "model" in msg.lower() and "not found" in msg.lower()
    ):
        raise DeepSeekAPIError(
            f"DeepSeek model '{model}' was not found. Check the configured model id."
        ) from exc

    if "429" in msg or str(code) == "429":
        raise DeepSeekAPIError(
            "DeepSeek API rate limited the request. Retry shortly.",
            status_code=503,
        ) from exc

    raise DeepSeekAPIError(
        f"Unexpected DeepSeek API error while calling model '{model}': {exc}"
    ) from exc
