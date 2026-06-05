from __future__ import annotations

import inspect
import logging
from typing import Any, Optional


LOG = logging.getLogger(__name__)
EMIT_COMPAT_MODE_ATTR = "_emit_compat_mode"
EMIT_COMPAT_MODE_MESSAGE = "message"
EMIT_COMPAT_MODE_OP_VERB_PAYLOAD_WHY = "op_verb_payload_why"
EMIT_COMPAT_MODE_OP_PAYLOAD_WHY = "op_payload_why"
_VALID_EMIT_COMPAT_MODES = {
    EMIT_COMPAT_MODE_MESSAGE,
    EMIT_COMPAT_MODE_OP_VERB_PAYLOAD_WHY,
    EMIT_COMPAT_MODE_OP_PAYLOAD_WHY,
}

try:
    from vfoundation.core.protocol import Message
except Exception:

    class Message:  # type: ignore
        def __init__(
            self,
            op: str,
            verb: str = "",
            src: str = "",
            dst: str = "",
            rid: Optional[str] = None,
            pld: Optional[dict[str, Any]] = None,
            why: str = "",
            data_ref: Optional[list[Any]] = None,
        ):
            self.op, self.verb = op, verb
            self.src, self.dst, self.rid = src, dst, rid
            self.pld, self.why = (pld or {}), why
            self.data_ref = list(data_ref or [])


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if hasattr(obj, name):
        try:
            return getattr(obj, name)
        except Exception:
            return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump().get(name, default)
        except Exception:
            return default
    if hasattr(obj, "dict"):
        try:
            return obj.dict().get(name, default)
        except Exception:
            return default
    return default


def _emit_logger(logger: Optional[Any]) -> Any:
    return logger if logger is not None else LOG


def _emit_mode_override_candidates(fsm: Any, emit: Any) -> list[Any]:
    emit_owner = getattr(emit, "__self__", None)
    candidates: list[Any] = [emit]
    if emit_owner is not None:
        candidates.append(emit_owner)
        candidates.append(type(emit_owner))
    if fsm is not None:
        candidates.append(fsm)
        candidates.append(type(fsm))
    return candidates


def _read_emit_mode_override(fsm: Any, emit: Any) -> Optional[str]:
    seen: set[int] = set()
    for candidate in _emit_mode_override_candidates(fsm, emit):
        candidate_id = id(candidate)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        mode = getattr(candidate, EMIT_COMPAT_MODE_ATTR, None)
        if mode is not None:
            return str(mode).strip()
    return None


def _classify_emit_signature(emit: Any) -> Optional[str]:
    try:
        sig = inspect.signature(emit)
    except (TypeError, ValueError):
        return None

    params = list(sig.parameters.values())
    if any(param.kind == inspect.Parameter.VAR_POSITIONAL for param in params):
        return None

    positional = [
        param
        for param in params
        if param.kind
        in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if not positional:
        return None
    if len(positional) == 1:
        return EMIT_COMPAT_MODE_MESSAGE

    param_names = [param.name.lower() for param in positional[:4]]
    if "verb" in param_names:
        return EMIT_COMPAT_MODE_OP_VERB_PAYLOAD_WHY
    if len(positional) >= 3:
        return EMIT_COMPAT_MODE_OP_PAYLOAD_WHY
    return None


def resolve_emit_compat_mode(
    fsm: Any,
    emit: Optional[Any] = None,
    logger: Optional[Any] = None,
) -> Optional[str]:
    emit_callable = emit if emit is not None else getattr(fsm, "emit", None)
    if emit_callable is None:
        _emit_logger(logger).error("FSM has no 'emit' method (fsm=%r)", fsm)
        return None

    explicit_mode = _read_emit_mode_override(fsm, emit_callable)
    if explicit_mode is not None:
        if explicit_mode in _VALID_EMIT_COMPAT_MODES:
            return explicit_mode
        _emit_logger(logger).error(
            "Unsupported %s=%r on emit owner %r",
            EMIT_COMPAT_MODE_ATTR,
            explicit_mode,
            fsm,
        )
        return None

    classified_mode = _classify_emit_signature(emit_callable)
    if classified_mode is not None:
        return classified_mode

    _emit_logger(logger).error(
        "emit_compat cannot resolve emit contract for %r; set %s explicitly",
        emit_callable,
        EMIT_COMPAT_MODE_ATTR,
    )
    return None


def _inject_emit_payload_meta(
    *,
    msg: Message,
    payload: Any,
) -> dict[str, Any]:
    verb = _get(msg, "verb", "")
    rid = _get(msg, "rid", None)
    src = _get(msg, "src", "")
    dst = _get(msg, "dst", "")
    pld = payload or {}

    if verb and "verb" not in pld:
        try:
            pld = dict(pld)
            pld["verb"] = verb
        except Exception:
            pld = {"verb": verb}
    if rid and "rid" not in pld:
        pld["rid"] = rid
    if src and "src" not in pld:
        pld["src"] = src
    if dst and "dst" not in pld:
        pld["dst"] = dst
    return pld


async def emit_compat(fsm: Any, msg: Message, logger: Optional[Any] = None) -> None:
    """
    Compatibility emission with an explicit call-shape contract.

    Resolution order:
    1. explicit `_emit_compat_mode` override on the callable or owner
    2. `inspect.signature(emit)` classification
    3. explicit fail-closed log when no contract can be resolved

    Real runtime exceptions from the chosen emit implementation are preserved.
    """
    emit = getattr(fsm, "emit", None)
    if emit is None:
        _emit_logger(logger).error("FSM has no 'emit' method (fsm=%r)", fsm)
        return

    op = _get(msg, "op", "")
    verb = _get(msg, "verb", "")
    why = _get(msg, "why", "")
    pld = _inject_emit_payload_meta(msg=msg, payload=_get(msg, "pld", {}) or {})

    mode = resolve_emit_compat_mode(fsm, emit=emit, logger=logger)
    if mode is None:
        return

    if mode == EMIT_COMPAT_MODE_MESSAGE:
        result = emit(msg)
    elif mode == EMIT_COMPAT_MODE_OP_VERB_PAYLOAD_WHY:
        result = emit(op, verb, pld, why)
    elif mode == EMIT_COMPAT_MODE_OP_PAYLOAD_WHY:
        result = emit(op, pld, why)
    else:
        _emit_logger(logger).error(
            "emit_compat resolved unsupported mode=%r for %r",
            mode,
            emit,
        )
        return

    if inspect.isawaitable(result):
        await result


__all__ = [
    "EMIT_COMPAT_MODE_ATTR",
    "EMIT_COMPAT_MODE_MESSAGE",
    "EMIT_COMPAT_MODE_OP_PAYLOAD_WHY",
    "EMIT_COMPAT_MODE_OP_VERB_PAYLOAD_WHY",
    "Message",
    "emit_compat",
    "resolve_emit_compat_mode",
]
