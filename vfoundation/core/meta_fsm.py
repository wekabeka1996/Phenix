from __future__ import annotations
from .protocol import Message


class MetaFSM:
    def __init__(self) -> None:
        self.mode = "normal"

    def decide(self, entropy_spike: bool) -> Message:
        if entropy_spike:
            self.mode = "low_risk"
            return Message(
                op="DEC",
                verb="SWITCH_TO_LOW_RISK_MODE",
                src="meta",
                dst="risk_strategy",
                why="entropy spike",
            )
        return Message(op="EVT", verb="OK", src="meta", dst="any", why="stable")
