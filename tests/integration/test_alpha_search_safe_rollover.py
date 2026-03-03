import logging
import os

from apps.reference.domains.alpha_search import alpha_search_log_adapter as mod


def test_safe_rotating_handler_copytruncate_on_rename_permission_error(tmp_path):
    src = tmp_path / "domain_alpha_search.log"
    dst = tmp_path / "domain_alpha_search.log.1"

    h = mod.SafeRotatingFileHandler(
        str(src),
        maxBytes=1,
        backupCount=1,
        encoding="utf-8",
        delay=False,
    )
    try:
        # Ensure there is content to rotate.
        assert h.stream is not None
        h.stream.write("hello\n")
        h.stream.flush()

        orig_rename = mod.os.rename

        def _deny_rename(source: str, dest: str) -> None:
            raise PermissionError(32, "The process cannot access the file", source)

        mod.os.rename = _deny_rename
        try:
            h.rotate(str(src), str(dst))
        finally:
            mod.os.rename = orig_rename

        assert dst.exists()
        # Source must be truncated after copy.
        assert os.path.getsize(src) == 0
    finally:
        try:
            h.close()
        except Exception:
            pass
