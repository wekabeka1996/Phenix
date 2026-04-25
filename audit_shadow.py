from apps.reference.telemetry.shadow_journal import _coerce_text, _is_placeholder_text


def is_placeholder_value(value):
    return _is_placeholder_text(value)


def is_useful_value(value):
    return _coerce_text(value) is not None


__all__ = ["is_placeholder_value", "is_useful_value"]
