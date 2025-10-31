from __future__ import annotations
from typing import Dict, Callable, Optional
from .protocol import Message


class FSM:
    def __init__(self, name: str) -> None:
        self.name = name
        self.state: Dict[str, str] = {}  # key -> state
        self.transitions: Dict[tuple[str, str], Callable[[Message], Optional[Message]]] = {}

    def on(
        self, op: str, verb: str
    ) -> Callable[[Callable[[Message], Optional[Message]]], Callable[[Message], Optional[Message]]]:
        def deco(
            fn: Callable[[Message], Optional[Message]],
        ) -> Callable[[Message], Optional[Message]]:
            self.transitions[(op, verb)] = fn
            return fn

        return deco

    def handle(self, msg: Message) -> Optional[Message]:
        fn = self.transitions.get((msg.op, msg.verb))
        if not fn:
            return Message(
                op="ERR",
                verb="NO_TRANSITION",
                src=self.name,
                dst=msg.src,
                rid=msg.rid,
                why="no transition",
            )
        return fn(msg)
