# Risks and Residuals

1. Production main composition lacks a canonical context/lifecycle projection and pure exposure-preview provider. Until supplied, the live handler remains unavailable.
2. Full Cockpit Express to FastAPI to main runtime to immutable review and version invalidation is unproven.
3. Request idempotency is bounded in-memory and resets with main runtime generation; callers must re-handshake after restart.
4. The existing command queue and request/reply client share a port but use independent short connections; sustained load behavior is not benchmarked.
5. P46-1G config currently has target `11.0` while one old test expects `10.0`; this unrelated baseline issue was not changed.

No side-effect boundary violation was observed.
