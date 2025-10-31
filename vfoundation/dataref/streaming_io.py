from __future__ import annotations
from typing import Iterator


def read_chunks(path: str, size: int = 8192) -> Iterator[bytes]:
    with open(path, "rb") as f:
        while True:
            chunk = f.read(size)
            if not chunk:
                break
            yield chunk
