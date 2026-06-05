from __future__ import annotations
import hashlib
from typing import List


def merkle_root(hashes: List[str]) -> str:
    if not hashes:
        return hashlib.sha256(b"").hexdigest()
    nodes = [bytes.fromhex(h) for h in hashes]
    while len(nodes) > 1:
        nxt = []
        for i in range(0, len(nodes), 2):
            a = nodes[i]
            b = nodes[i + 1] if i + 1 < len(nodes) else a
            nxt.append(hashlib.sha256(a + b).digest())
        nodes = nxt
    return nodes[0].hex()
