# Risks

## P0

- None introduced. No mainnet/live/raw exchange authority exists in this patch.

## P1

- The current branch does not contain Agent 2's uncommitted `config/p42_dual_agent_mvp.yaml` or runtime state producer. Until integrated, `/arena/runtime` truthfully reports `BLOCKED`.
- Registered control events are not proven consumed by the P42B runner; they are recorded/pending only.
- Private-LAN Cockpit inherits the existing authentication posture. Use only on a trusted private Wi-Fi and Private firewall profile.

## P2

- Browser rendering is not visually proven on primary Windows.
- Docker Compose interpolation/startup is not runtime-proven on this machine because Docker CLI is unavailable.
- Portfolio/open-order/position/reconciliation visibility depends on runtime producers supplying those fields; absent data remains unknown.

## Evidence safety

- Stub ACKs render `STUB`; shadow ACKs render `SHADOW`.
- A generic `exchange_ack` without explicit external verification renders `UNKNOWN`, never success.
- No real exchange ACK, reject, fill, cancellation, or cleanup is claimed.

