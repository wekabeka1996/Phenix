# Existing IPC Inventory

| Surface | Owner | Direction | Before | After |
|---|---|---|---|---|
| `JsonlTcpServer` | main process | edge to main | JSONL receive only | optional one-line typed reply |
| `JsonlTcpQueueClient` | FastAPI edge | edge to main | asynchronous commands | unchanged |
| `JsonlTcpRequestReplyClient` | FastAPI edge | edge to main and reply | absent | bounded one request/one reply |
| `LLMIntentIngressBridge` | main process | semantic dispatch | command envelopes | query branch before command accounting |

FACT: Query and command traffic reuse `tcp://127.0.0.1:7102`. No second listener or generic RPC framework was introduced.

FACT: Queries never enter V2 processing, command mapping, FSM dispatch, or adapter code.
