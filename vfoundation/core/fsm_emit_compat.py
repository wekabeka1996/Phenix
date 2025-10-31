from __future__ import annotations
from typing import Any, Optional

try:
    from vfoundation.core.protocol import Message  # ваш контракт
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
        ):
            self.op, self.verb = op, verb
            self.src, self.dst, self.rid = src, dst, rid
            self.pld, self.why = (pld or {}), why


def _get(obj: Any, name: str, default: Any = None) -> Any:
    # Безпечне читання атрибутів/ключів (Pydantic v1/v2, dict)
    if hasattr(obj, name):
        try:
            return getattr(obj, name)
        except Exception:
            return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump().get(name, default)
        except Exception:
            return default
    # Pydantic v1
    if hasattr(obj, "dict"):
        try:
            return obj.dict().get(name, default)
        except Exception:
            return default
    return default


async def emit_compat(fsm: Any, msg: Message, logger: Optional[Any] = None) -> None:
    """
    Сумісна емісія:
      1) emit(msg)
      2) emit(op, verb, payload, why)
      3) emit(op, payload, why)
    Meta ('verb','rid','src','dst') інжектимо в payload лише якщо їх немає.
    """
    emit = getattr(fsm, "emit", None)
    if emit is None:
        if logger:
            logger.error("FSM has no 'emit' method (fsm=%r)", fsm)
        return

    op = _get(msg, "op", "")
    verb = _get(msg, "verb", "")
    why = _get(msg, "why", "")
    rid = _get(msg, "rid", None)
    src = _get(msg, "src", "")
    dst = _get(msg, "dst", "")
    pld = _get(msg, "pld", {}) or {}

    # 1) Спробувати emit(msg)
    try:
        res = emit(msg)
        if hasattr(res, "__await__"):
            await res
        return
    except TypeError:
        pass
    except Exception as e:
        # Якщо реалізація не підтримує Message-API — спробуємо інші варіанти
        if logger:
            logger.debug("emit(Message) failed, fallback: %r", e)

    # Інжектимо мету у payload, якщо її там немає
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

    # 2) emit(op, verb, payload, why)
    try:
        res = emit(op, verb, pld, why)
        if hasattr(res, "__await__"):
            await res
        return
    except TypeError:
        pass
    except Exception as e:
        if logger:
            logger.debug("emit(op,verb,payload,why) failed, fallback: %r", e)

    # 3) emit(op, payload, why)
    try:
        res = emit(op, pld, why)
        if hasattr(res, "__await__"):
            await res
        return
    except Exception as e:
        if logger:
            logger.exception("emit_compat failed: %r", e)


__all__ = ["emit_compat", "Message"]
