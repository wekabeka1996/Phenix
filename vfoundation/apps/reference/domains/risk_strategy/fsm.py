from __future__ import annotations
from vfoundation.core.fsm import FSM
from vfoundation.core.protocol import Message
from vfoundation.dr import wal

fsm = FSM("risk_strategy")

@fsm.on("ASK","EVAL")
def handle_eval(msg: Message) -> Message:
    wal.append({"rid": msg.rid, "op": msg.op, "verb": msg.verb, "src": "risk_strategy"})
    # naive decision
    dec = Message(op="DEC", verb="EVAL", src="risk_strategy", dst="execution_position", rid=msg.rid, why="risk ok")
    wal.append(dec.model_dump())
    return dec
