from __future__ import annotations
from typing import List


def append_why(chain: List[str], why: str) -> List[str]:
    if why:
        chain = chain + [why]
    return chain
