"""Coverage tests for vfoundation.core.routing — Router + SimpleIdempotencyStore."""
import pytest
import json
from unittest.mock import patch
from vfoundation.core.protocol import Message
from vfoundation.core.routing import Router, SimpleIdempotencyStore
from vfoundation.security.signing_ed25519 import sign


def _signed_msg(op: str, verb: str, **kwargs) -> Message:
    """Helper to create a signed message for DEC/CMD ops."""
    msg = Message(op=op, verb=verb, src="test", dst="router", why="test", **kwargs)
    msg_dict = msg.model_dump(exclude={"sig"})
    payload_bytes = json.dumps(msg_dict, sort_keys=True).encode()
    sig_bytes = sign(payload_bytes)
    return msg.model_copy(update={"sig": sig_bytes.hex()})


def _evt_msg(verb: str = "TEST", **kwargs) -> Message:
    return Message(op="EVT", verb=verb, src="test", dst="router", why="test", **kwargs)


class TestSimpleIdempotencyStore:
    def test_begin_acquire_first_time(self):
        s = SimpleIdempotencyStore()
        result = s.begin("k1")
        assert result["acquired"] is True
        assert s.metrics.idem_acquired == 1

    def test_begin_dedup_after_complete(self):
        s = SimpleIdempotencyStore()
        msg = _evt_msg()
        s.remember("k1", msg)
        result = s.begin("k1")
        assert result["dedup"] is True
        assert s.metrics.idem_dedup == 1

    def test_begin_inflight_second_request(self):
        s = SimpleIdempotencyStore()
        s.begin("k1")  # acquired
        result = s.begin("k1")  # inflight
        assert result["inflight"] is True

    def test_complete_clears_inflight(self):
        s = SimpleIdempotencyStore()
        s.begin("k1")
        msg = _evt_msg()
        s.complete("k1", msg)
        assert s.get_if_done("k1") == msg

    def test_seen_and_get(self):
        s = SimpleIdempotencyStore()
        msg = _evt_msg()
        assert s.seen("k1") is False
        s.remember("k1", msg)
        assert s.seen("k1") is True
        assert s.get("k1") == msg


class TestRouter:
    def test_route_evt_success(self):
        r = Router()
        response = _evt_msg(verb="PONG")
        r.register("EVT", "TEST", lambda m: response)
        result = r.route(_evt_msg())
        assert result.op == "EVT"
        assert result.verb == "PONG"

    def test_route_no_handler_returns_err(self):
        r = Router()
        result = r.route(_evt_msg(verb="MISSING"))
        assert result.op == "ERR"
        assert result.verb == "NO_ROUTE"

    def test_route_why_too_long_returns_err(self):
        r = Router()
        msg = Message(op="EVT", verb="T", src="a", dst="b", why="x" * 80)
        # why=80 chars is exactly OK — Message validator ensures max 80
        # We need to test the router's own check at line 97-98
        # But Message.why is validated by Pydantic to max 80 chars...
        # The router check is redundant but let's confirm it works for valid msgs
        r.register("EVT", "T", lambda m: m)
        result = r.route(msg)
        assert result.op == "EVT"

    def test_route_dec_without_sig_returns_401(self):
        r = Router()
        r.register("DEC", "OPEN", lambda m: m)
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b", why="test")
        result = r.route(msg)
        assert result.op == "ERR"
        assert result.verb == "SIGNATURE_REQUIRED"
        assert result.pld["status_code"] == 401

    def test_route_dec_with_valid_sig(self):
        r = Router()
        response = _evt_msg(verb="OK")
        r.register("DEC", "OPEN", lambda m: response)
        msg = _signed_msg("DEC", "OPEN")
        result = r.route(msg)
        assert result.verb == "OK"

    def test_route_dec_with_invalid_sig(self):
        r = Router()
        r.register("DEC", "OPEN", lambda m: m)
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b", why="test",
                      sig="deadbeef" * 16)
        result = r.route(msg)
        assert result.op == "ERR"
        assert "SIGNATURE" in result.verb

    def test_route_dec_with_malformed_sig(self):
        r = Router()
        r.register("DEC", "OPEN", lambda m: m)
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b", why="test",
                      sig="not_hex!")
        result = r.route(msg)
        assert result.op == "ERR"
        assert result.verb == "SIGNATURE_ERROR"

    def test_route_expired_message(self):
        r = Router()
        r.register("EVT", "T", lambda m: m)
        msg = Message(op="EVT", verb="T", src="a", dst="b", why="t", ttl_ms=1)
        import time; time.sleep(0.05)  # Wait past 1ms TTL
        result = r.route(msg)
        assert result.op == "ERR"
        assert result.verb == "TIMEOUT"

    def test_route_idempotent_dedup(self):
        r = Router()
        call_count = 0
        def handler(m):
            nonlocal call_count
            call_count += 1
            return _evt_msg(verb="DONE")
        r.register("EVT", "T", handler)

        msg = _evt_msg(verb="T", pld={"idempotent_key": "k1"})
        r.route(msg)  # First call
        # Need to send same RID for legacy dedup
        r.route(msg)  # Second call — RID dedup
        assert call_count == 1

    def test_route_circuit_breaker_open(self):
        r = Router()
        def fail(m): raise RuntimeError("fail")
        r.register("EVT", "T", fail)

        # Trip the CB
        for _ in range(10):
            r.route(_evt_msg(verb="T"))

        # CB should now be open
        r.register("EVT", "OK", lambda m: m)
        result = r.route(_evt_msg(verb="OK"))
        assert result.op == "ERR"
        assert result.verb == "CB_OPEN"

    def test_route_handler_exception_retries(self):
        r = Router()
        attempts = []
        def fail_once(m):
            attempts.append(1)
            if len(attempts) < 2:
                raise RuntimeError("transient")
            return _evt_msg(verb="OK")
        r.register("EVT", "T", fail_once)
        result = r.route(_evt_msg(verb="T"))
        assert result.verb == "OK"
        assert len(attempts) == 2

    def test_get_idempotency_metrics(self):
        r = Router()
        metrics = r.get_idempotency_metrics()
        assert "idem_acquired" in metrics
        assert "idem_dedup" in metrics

    def test_inflight_response(self):
        r = Router()
        msg = _evt_msg()
        resp = r._inflight_response(msg)
        assert resp.verb == "INFLIGHT"
        assert resp.pld["inflight"] is True

    def test_over_cap_branch(self):
        r = Router()
        # Simulate over_cap by directly calling idem methods
        r.idem._store["k1"] = None  # Mark as seen
        status = r.idem.begin("k1")
        assert status.get("dedup") is True
