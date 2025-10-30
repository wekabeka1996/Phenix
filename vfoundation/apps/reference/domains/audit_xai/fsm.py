from __future__ import annotations
from vfoundation.core.fsm import FSM
from vfoundation.core.protocol import Message
from vfoundation.dr import wal

fsm = FSM("audit_xai")


@fsm.on("UPD", "WHY_APPEND")
def on_why(msg: Message) -> Message:
    wal.append({"rid": msg.rid, "op": msg.op, "verb": msg.verb, "src": "audit_xai"})
    return Message(
        op="EVT", verb="AUDIT_LOGGED", src="audit_xai", dst="any", rid=msg.rid, why="logged"
    )
