from __future__ import annotations

class DegradationPolicy:
    def __init__(self) -> None:
        self.reduce_only = False
        self.drop_low_priority = True  # e.g., INQUIRY intents
