# AGENT IMPLEMENTATION PROMPT — vFoundation Phase 14 Full Execution

## IDENTITY & AUTHORITY

You are a **Staff Engineer** implementing `vFoundation Phase 14` for the Aurora algorithmic trading system. You operate at Senior+/Staff level — you reason from first principles, build causal chains, never guess, never copy blindly.

**Working directory:** `c:\Users\wekab\Music\Phenix`
**Active branch:** `backtest_1`
**Python:** 3.14.3 | **pytest:** 9.0.2

---

## MISSION

Execute **every step** of `docs/docs_vfoundation/IMPLEMENTATION_PLAN_PHASE14.md` in strict sequential order. After each completed step record progress in `docs/docs_vfoundation/PROGRESS_LOG.md`. Achieve **Definition of Done** (DoD) before finishing.

**Non-negotiable constraints:**
- TDD-first: tests written BEFORE implementation code for every new feature
- Green-always: `pytest tests/vfoundation/ -q` must pass after EVERY individual change
- Never break the existing 716 passing tests
- Never create a new verb without updating `apps/reference/dictionaries/verb_registry_v1.yaml` first
- Never delete a file without running `grep -rn "from.*<module>\|import.*<module>" .` first
- All new source files ≤ 500 LOC (Constitution §3)
- Navigate registry-first: always check `apps/reference/dictionaries/verb_registry_v1.yaml` before touching domain code

---

## BEFORE STARTING — MANDATORY BOOTSTRAP

Run these commands and record outputs in PROGRESS_LOG.md:

```bash
# 1. Confirm baseline
cd c:\Users\wekab\Music\Phenix
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
# Expected: 716 passed

# 2. Measure baseline coverage
python -m pytest tests/vfoundation/ --cov=vfoundation --cov-report=term-missing --tb=no -q 2>&1 | tail -20

# 3. Read key reference files
# ALWAYS read these before any changes:
# - apps/reference/dictionaries/verb_registry_v1.yaml
# - vfoundation/core/fsm_v2.py
# - vfoundation/obs/topology_auditor.py
# - vfoundation/core/protocol.py
# - vfoundation/security/signing_ed25519.py
```

---

## PROGRESS TRACKING

Create and maintain `docs/docs_vfoundation/PROGRESS_LOG.md` with this structure:

```markdown
# Phase 14 Implementation Progress Log

## Baseline
- Tests: 716 passed
- Coverage: <measured>
- Date: <today>

## Steps

### STEP 0.1 — bugfix signing_ed25519.py
Status: [ ] TODO | [x] DONE | [!] BLOCKED
Tests added: <list>
Tests result: <N passed>
Notes: <any observations>
```

**Update the log AFTER every sub-step.** Mark status with `[x]` when complete.

---

## STEP 0.1 — BUGFIX: signing_ed25519.py

**File:** `vfoundation/security/signing_ed25519.py`

**Problem:** `verify()` only catches `BadSignatureError`. PyNaCl raises `ValueError`/`TypeError` on malformed input (wrong length, empty bytes) → unhandled exception propagates out instead of returning `False`.

### Phase A — Write failing tests FIRST

Read `tests/vfoundation/security/test_signing_ed25519.py` completely.

Append these test cases to that file:

```python
def test_verify_short_signature_returns_false():
    """PyNaCl raises ValueError for wrong-length signature — must return False."""
    from vfoundation.security.signing_ed25519 import sign, verify
    payload = b"test payload"
    assert verify(payload, b"short") is False

def test_verify_empty_signature_returns_false():
    """Empty bytes signature must return False, not raise."""
    from vfoundation.security.signing_ed25519 import verify
    assert verify(b"payload", b"") is False

def test_verify_wrong_payload_returns_false():
    """Correct signature but wrong payload must return False."""
    from vfoundation.security.signing_ed25519 import sign, verify
    payload = b"original"
    sig = sign(payload)
    assert verify(b"tampered", sig) is False

def test_verify_correct_signature_returns_true():
    """Sign then verify with correct data must return True."""
    from vfoundation.security.signing_ed25519 import sign, verify
    payload = b"authentic message"
    sig = sign(payload)
    assert verify(payload, sig) is True
```

Run — MUST fail or error (confirm red phase):
```bash
python -m pytest tests/vfoundation/security/test_signing_ed25519.py -v --tb=short
```

### Phase B — Implement fix

Edit `vfoundation/security/signing_ed25519.py` line 33. Change ONLY:

```python
# BEFORE:
    except BadSignatureError:
        return False

# AFTER:
    except (BadSignatureError, ValueError, TypeError):
        return False
```

### Phase C — Verify green

```bash
python -m pytest tests/vfoundation/security/test_signing_ed25519.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
# Must show: 720 passed (or more)
```

### Phase D — Update PROGRESS_LOG.md

---

## STEP 0.2 — BUGFIX: protocol.py `truncate_why`

**File:** `vfoundation/core/protocol.py`

**Problem:** `truncate_why()` has broken docstring (missing closing `"""`) and unreachable `return` statement. The function is effectively dead code.

### Phase A — Write failing tests FIRST

Create NEW file `tests/vfoundation/core/test_protocol.py`:

```python
"""Tests for vfoundation.core.protocol module."""
import pytest
from vfoundation.core.protocol import truncate_why, Message


class TestTruncateWhy:
    def test_none_input_returns_none(self):
        assert truncate_why(None) is None

    def test_empty_string_returns_empty(self):
        assert truncate_why("") == ""

    def test_short_string_unchanged(self):
        assert truncate_why("hello") == "hello"

    def test_exactly_80_chars_unchanged(self):
        s = "x" * 80
        assert truncate_why(s) == s

    def test_81_chars_truncated_to_80(self):
        s = "x" * 81
        result = truncate_why(s)
        assert len(result) == 80

    def test_100_chars_truncated_to_80(self):
        s = "a" * 100
        assert len(truncate_why(s)) == 80

    def test_custom_max_len(self):
        assert truncate_why("hello world", max_len=5) == "hello"

    def test_custom_max_len_exact(self):
        assert truncate_why("hello", max_len=5) == "hello"


class TestMessageProtocol:
    def test_message_why_max_80_validation(self):
        with pytest.raises(Exception):
            Message(op="EVT", verb="TEST", src="a", dst="b", why="x" * 81)

    def test_message_why_exactly_80_accepted(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x" * 80)
        assert len(msg.why) == 80

    def test_message_defaults_are_correct(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="ok")
        assert msg.v == 1
        assert msg.mode == "live"
        assert msg.ttl_ms == 2000
        assert msg.pld == {}

    def test_message_ttl_out_of_range_rejected(self):
        with pytest.raises(Exception):
            Message(op="EVT", verb="TEST", src="a", dst="b", why="ok", ttl_ms=99999)

    def test_message_rid_unique_per_instance(self):
        m1 = Message(op="EVT", verb="TEST", src="a", dst="b", why="ok")
        m2 = Message(op="EVT", verb="TEST", src="a", dst="b", why="ok")
        assert m1.rid != m2.rid

    def test_message_is_expired_false_for_fresh_message(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="ok")
        assert msg.is_expired() is False

    def test_message_all_op_types_valid(self):
        for op in ("ASK", "DEC", "CMD", "EVT", "UPD", "ERR"):
            msg = Message(op=op, verb="TEST", src="a", dst="b", why="ok")
            assert msg.op == op
```

Run — MUST fail (red):
```bash
python -m pytest tests/vfoundation/core/test_protocol.py -v --tb=short
```

### Phase B — Fix truncate_why

Read `vfoundation/core/protocol.py` lines 11–21. Replace broken `truncate_why` with:

```python
def truncate_why(why_text: Optional[str], max_len: int = 80) -> Optional[str]:
    """Truncate why field to max_len to comply with Message validation.

    Usage in bridge: why = truncate_why(long_why_string)
    """
    if why_text is None:
        return None
    if len(why_text) <= max_len:
        return why_text
    return why_text[:max_len]
```

### Phase C — Verify green

```bash
python -m pytest tests/vfoundation/core/test_protocol.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
# Must show: 730+ passed
```

---

## STEP 1 — FSMv2 ENHANCEMENTS (Phase 14B)

**File:** `vfoundation/core/fsm_v2.py`
**Risk:** Low (additive only — no existing API changes)

Read `vfoundation/core/fsm_v2.py` completely before modifying anything.

### STEP 1.1 — `validate_reachability()`

Detects orphan states that can never be reached from initial_state (deadlock risk).

#### Phase A — Write failing tests

Create `tests/vfoundation/core/test_fsm_v2_enhancements.py`:

```python
"""Tests for FSMv2 Phase 14B enhancements: reachability, dot export, stats."""
import pytest
from vfoundation.core.fsm_v2 import FSMv2
from vfoundation.core.protocol import Message


def _msg(verb: str = "INIT") -> Message:
    return Message(op="EVT", verb=verb, src="test", dst="test", why="test")


class TestValidateReachability:
    def test_linear_chain_all_reachable(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_state("C", terminal=True)
        fsm.register_transition("A", "EVT:GO", "B")
        fsm.register_transition("B", "EVT:DONE", "C")

        result = fsm.validate_reachability()
        assert result["valid"] is True
        assert result["unreachable"] == set()
        assert {"A", "B", "C"} == result["reachable"]

    def test_orphan_state_detected(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_state("ORPHAN")
        fsm.register_transition("A", "EVT:GO", "B")

        result = fsm.validate_reachability()
        assert result["valid"] is False
        assert "ORPHAN" in result["unreachable"]
        assert "A" in result["reachable"]
        assert "B" in result["reachable"]

    def test_no_initial_state_returns_invalid(self):
        fsm = FSMv2("test")
        fsm.register_state("A")
        result = fsm.validate_reachability()
        assert result["valid"] is False

    def test_single_initial_terminal_state_valid(self):
        fsm = FSMv2("test")
        fsm.register_state("ONLY", initial=True, terminal=True)
        result = fsm.validate_reachability()
        assert result["valid"] is True

    def test_branching_all_reachable(self):
        fsm = FSMv2("test")
        fsm.register_state("START", initial=True)
        fsm.register_state("LEFT", terminal=True)
        fsm.register_state("RIGHT", terminal=True)
        fsm.register_transition("START", "EVT:LEFT", "LEFT")
        fsm.register_transition("START", "EVT:RIGHT", "RIGHT")
        result = fsm.validate_reachability()
        assert result["valid"] is True
        assert result["unreachable"] == set()

    def test_multi_orphan_all_detected(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_state("X")
        fsm.register_state("Y")
        fsm.register_transition("A", "EVT:GO", "B")
        result = fsm.validate_reachability()
        assert "X" in result["unreachable"]
        assert "Y" in result["unreachable"]


class TestToDot:
    def test_dot_contains_all_states(self):
        fsm = FSMv2("machine")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("RUNNING")
        fsm.register_state("STOPPED", terminal=True)
        fsm.register_transition("IDLE", "CMD:START", "RUNNING")
        fsm.register_transition("RUNNING", "CMD:STOP", "STOPPED")
        dot = fsm.to_dot()
        assert "IDLE" in dot
        assert "RUNNING" in dot
        assert "STOPPED" in dot

    def test_dot_contains_transition_label(self):
        fsm = FSMv2("machine")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_transition("A", "EVT:TRIGGER", "B")
        dot = fsm.to_dot()
        assert "EVT:TRIGGER" in dot

    def test_dot_terminal_has_doublecircle(self):
        fsm = FSMv2("machine")
        fsm.register_state("START", initial=True)
        fsm.register_state("DONE", terminal=True)
        fsm.register_transition("START", "EVT:FIN", "DONE")
        dot = fsm.to_dot()
        assert "doublecircle" in dot

    def test_dot_initial_has_bold(self):
        fsm = FSMv2("machine")
        fsm.register_state("INIT", initial=True)
        fsm.register_state("END", terminal=True)
        fsm.register_transition("INIT", "EVT:GO", "END")
        dot = fsm.to_dot()
        assert "bold" in dot

    def test_dot_is_valid_graphviz_structure(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B", terminal=True)
        fsm.register_transition("A", "EVT:X", "B")
        dot = fsm.to_dot()
        assert dot.strip().startswith("digraph")
        assert "{" in dot and "}" in dot
        assert "->" in dot

    def test_dot_arrow_connects_correct_states(self):
        fsm = FSMv2("machine")
        fsm.register_state("SRC", initial=True)
        fsm.register_state("DST", terminal=True)
        fsm.register_transition("SRC", "EVT:MOVE", "DST")
        dot = fsm.to_dot()
        assert "SRC -> DST" in dot


class TestGetStats:
    def test_stats_all_states_present_with_zero_counts(self):
        fsm = FSMv2("test")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("ACTIVE", terminal=True)
        stats = fsm.get_stats()
        assert "IDLE" in stats
        assert "ACTIVE" in stats

    def test_stats_initial_state_has_count_after_key_created(self):
        fsm = FSMv2("test")
        fsm.register_state("IDLE", initial=True)
        fsm.register_state("DONE", terminal=True)
        fsm.register_transition("IDLE", "EVT:FINISH", "DONE")

        # Create a key that stays in IDLE (invalid event)
        fsm.handle("key1", _msg("NOOP"))
        stats = fsm.get_stats()
        assert stats["IDLE"] == 1

    def test_stats_counts_after_transition(self):
        fsm = FSMv2("test")
        fsm.register_state("A", initial=True)
        fsm.register_state("B")
        fsm.register_state("C", terminal=True)
        fsm.register_transition("A", "EVT:STEP1", "B")
        fsm.register_transition("B", "EVT:STEP2", "C")

        fsm.handle("k1", _msg("STEP1"))  # k1: A→B
        fsm.handle("k2", _msg("NOOP"))   # k2: stays at A
        fsm.handle("k1", _msg("STEP2"))  # k1: B→C

        stats = fsm.get_stats()
        assert stats["A"] == 1  # k2
        assert stats["B"] == 0
        assert stats["C"] == 1  # k1
```

Run — MUST fail:
```bash
python -m pytest tests/vfoundation/core/test_fsm_v2_enhancements.py -v --tb=short
```

#### Phase B — Add methods to FSMv2

Read `vfoundation/core/fsm_v2.py`. Add the following methods inside class `FSMv2`, after the `restore()` method:

**`validate_reachability()`:**
```python
def validate_reachability(self) -> Dict[str, Any]:
    """
    Validate all states are reachable from initial_state via BFS.

    Returns:
        {"valid": bool, "reachable": set[str], "unreachable": set[str]}
    """
    if self._initial_state is None:
        return {
            "valid": False,
            "reachable": set(),
            "unreachable": set(self._states.keys()),
        }
    visited: set[str] = set()
    queue: List[str] = [self._initial_state]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for rule in self._transitions:
            if rule.from_state == current and rule.to_state not in visited:
                queue.append(rule.to_state)
    all_states = set(self._states.keys())
    unreachable = all_states - visited
    return {"valid": len(unreachable) == 0, "reachable": visited, "unreachable": unreachable}
```

**`to_dot()`:**
```python
def to_dot(self) -> str:
    """Export FSM as Graphviz DOT format string."""
    lines: List[str] = [f"digraph {self.name} {{", "  rankdir=LR;"]
    for state_name, info in self._states.items():
        attrs: List[str] = []
        attrs.append("shape=doublecircle" if info.terminal else "shape=circle")
        if state_name == self._initial_state:
            attrs.append("style=bold")
        lines.append(f'  {state_name} [{", ".join(attrs)}];')
    for rule in self._transitions:
        guard_tag = " [G]" if rule.guard is not None else ""
        lines.append(
            f'  {rule.from_state} -> {rule.to_state} [label="{rule.event}{guard_tag}"];'
        )
    lines.append("}")
    return "\n".join(lines)
```

**`get_stats()`:**
```python
def get_stats(self) -> Dict[str, Any]:
    """Return per-state count of tracked keys."""
    with self._lock:
        counts: Dict[str, int] = {name: 0 for name in self._states}
        for state in self._state_store.values():
            if state in counts:
                counts[state] += 1
    return counts
```

#### Phase C — Verify

```bash
python -m pytest tests/vfoundation/core/test_fsm_v2_enhancements.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
# Must show: 745+ passed
```

#### Phase D — fsm_emit_compat.py check

```bash
grep -rn "fsm_emit_compat" . --include="*.py" | grep -v "__pycache__"
```
If zero results: delete the file and run tests again. If results: note in log.

---

## STEP 2.1 — TOPOLOGY AUDITOR: Health Monitoring

**File:** `vfoundation/obs/topology_auditor.py`

Read the file completely first.

#### Phase A — Write failing tests

Create `tests/vfoundation/obs/test_topology_auditor_health.py`:

```python
"""Tests for TopologyAuditor.audit_health() — Phase 14D infrastructure health."""
import pytest
from vfoundation.obs.topology_auditor import TopologyAuditor, HealthCheck, HealthReport


class TestHealthCheckDataclass:
    def test_fields_and_defaults(self):
        hc = HealthCheck(name="redis", check_fn=lambda: True)
        assert hc.name == "redis"
        assert hc.critical is True

    def test_non_critical_flag(self):
        hc = HealthCheck(name="metrics", check_fn=lambda: False, critical=False)
        assert hc.critical is False


class TestHealthReportDataclass:
    def test_all_pass_report(self):
        r = HealthReport(healthy=True, checks_passed=3, checks_failed=0,
                         failures=[], critical_failure=False)
        assert r.healthy is True
        assert r.critical_failure is False


class TestAuditHealth:
    def test_all_checks_pass(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("a", lambda: True),
            HealthCheck("b", lambda: True),
        ])
        assert report.healthy is True
        assert report.checks_passed == 2
        assert report.checks_failed == 0
        assert report.critical_failure is False
        assert report.failures == []

    def test_non_critical_fail_healthy_false_not_critical_fail(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("ok", lambda: True),
            HealthCheck("optional", lambda: False, critical=False),
        ])
        assert report.healthy is False
        assert report.checks_failed == 1
        assert report.critical_failure is False
        assert any("optional" in f for f in report.failures)

    def test_critical_check_fail_sets_critical_failure(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("redis", lambda: False, critical=True),
        ])
        assert report.healthy is False
        assert report.critical_failure is True

    def test_empty_checks_returns_healthy(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([])
        assert report.healthy is True
        assert report.checks_passed == 0
        assert report.checks_failed == 0

    def test_exception_in_check_treated_as_failure_no_crash(self):
        auditor = TopologyAuditor()
        def explode() -> bool:
            raise RuntimeError("connection refused")
        report = auditor.audit_health([HealthCheck("broken", explode, critical=False)])
        assert report.checks_failed == 1
        assert any("broken" in f for f in report.failures)

    def test_exception_in_critical_check_sets_critical_flag(self):
        auditor = TopologyAuditor()
        def crash() -> bool:
            raise OSError("disk full")
        report = auditor.audit_health([HealthCheck("db", crash, critical=True)])
        assert report.critical_failure is True

    def test_mixed_pass_fail_counts_correct(self):
        auditor = TopologyAuditor()
        report = auditor.audit_health([
            HealthCheck("a", lambda: True),
            HealthCheck("b", lambda: True),
            HealthCheck("c", lambda: False, critical=False),
        ])
        assert report.checks_passed == 2
        assert report.checks_failed == 1
        assert report.healthy is False
        assert report.critical_failure is False
```

Run — MUST fail.

#### Phase B — Implement

Add dataclasses after `DriftReport` in `topology_auditor.py`:

```python
@dataclass
class HealthCheck:
    """A single infrastructure health check."""
    name: str
    check_fn: Callable[[], bool]
    critical: bool = True


@dataclass
class HealthReport:
    """Composite result of infrastructure health audit."""
    healthy: bool
    checks_passed: int
    checks_failed: int
    failures: List[str]
    critical_failure: bool
```

Add import at top (merge with existing): `from typing import Callable, List`

Add method to `TopologyAuditor` class:

```python
def audit_health(self, checks: "List[HealthCheck]") -> "HealthReport":
    """
    Execute health checks and return composite report.

    Exceptions in check_fn are caught — never crash the auditor.
    Constitution §10: health checks must be fail-safe.
    """
    passed = 0
    failed = 0
    failures: List[str] = []
    critical_failure = False

    for check in checks:
        try:
            ok = check.check_fn()
        except Exception as exc:
            ok = False
            LOG.warning("HealthCheck '%s' raised: %s", check.name, exc)

        if ok:
            passed += 1
        else:
            failed += 1
            failures.append(f"{check.name}: FAIL")
            if check.critical:
                critical_failure = True

    return HealthReport(
        healthy=(failed == 0),
        checks_passed=passed,
        checks_failed=failed,
        failures=failures,
        critical_failure=critical_failure,
    )
```

#### Phase C — Verify

```bash
python -m pytest tests/vfoundation/obs/test_topology_auditor_health.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
```

---

## STEP 2.2 — DOMAIN BRIDGE

**New file:** `vfoundation/obs/domain_bridge.py`

Read `vfoundation/core/protocol.py` and `vfoundation/obs/topology_auditor.py` first.

#### Phase A — Write failing tests

Create `tests/vfoundation/obs/test_domain_bridge.py`:

```python
"""Tests for DomainBridge — FSM bridge for orphan domains (Phase 14D)."""
import pytest
from unittest.mock import MagicMock
from vfoundation.obs.domain_bridge import DomainBridge


class TestDomainBridgeHealth:
    def test_no_health_fn_defaults_to_healthy(self):
        assert DomainBridge("neocortex").is_healthy() is True

    def test_healthy_fn_returns_true(self):
        b = DomainBridge("alpha")
        b.register_health_fn(lambda: True)
        assert b.is_healthy() is True

    def test_unhealthy_fn_returns_false(self):
        b = DomainBridge("alpha")
        b.register_health_fn(lambda: False)
        assert b.is_healthy() is False

    def test_exception_in_fn_returns_false_no_raise(self):
        b = DomainBridge("broken")
        def bad(): raise RuntimeError("crash")
        b.register_health_fn(bad)
        assert b.is_healthy() is False

    def test_last_registered_fn_wins(self):
        b = DomainBridge("test")
        b.register_health_fn(lambda: False)
        b.register_health_fn(lambda: True)
        assert b.is_healthy() is True

    def test_domain_name_stored(self):
        b = DomainBridge("my_domain")
        assert b.domain_name == "my_domain"


class TestDomainBridgeEmit:
    def test_emit_no_bus_no_crash(self):
        DomainBridge("neocortex").emit_status()

    def test_emit_with_bus_calls_emit(self):
        bus = MagicMock()
        DomainBridge("neocortex", bus=bus).emit_status()
        bus.emit.assert_called_once()

    def test_emit_event_name_contains_domain_status(self):
        bus = MagicMock()
        DomainBridge("neocortex", bus=bus).emit_status()
        event_name = bus.emit.call_args[0][0]
        assert "DOMAIN_STATUS" in event_name

    def test_emit_payload_has_domain_name(self):
        bus = MagicMock()
        DomainBridge("alpha_search", bus=bus).emit_status()
        payload = bus.emit.call_args[0][1]
        assert payload.get("domain") == "alpha_search"

    def test_emit_payload_has_healthy_flag(self):
        bus = MagicMock()
        b = DomainBridge("alpha_search", bus=bus)
        b.register_health_fn(lambda: True)
        b.emit_status()
        assert bus.emit.call_args[0][1]["healthy"] is True

    def test_emit_unhealthy_reflected_in_payload(self):
        bus = MagicMock()
        b = DomainBridge("alpha_search", bus=bus)
        b.register_health_fn(lambda: False)
        b.emit_status()
        assert bus.emit.call_args[0][1]["healthy"] is False


class TestDomainBridgeIsolation:
    def test_multiple_bridges_are_independent(self):
        b1 = DomainBridge("d1")
        b2 = DomainBridge("d2")
        b1.register_health_fn(lambda: False)
        b2.register_health_fn(lambda: True)
        assert b1.is_healthy() is False
        assert b2.is_healthy() is True
```

Run — MUST fail.

#### Phase B — Implement

Create `vfoundation/obs/domain_bridge.py`:

```python
"""
DomainBridge — Phase 14D FSM bridge for orphan domains.

Allows non-FSM domains (neocortex, alpha_search, inflight_reconcile)
to register health functions and participate in MetaFSM topology auditing.

Constitution v2.2 §7: all domains must be auditable by TopologyAuditor.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

LOG = logging.getLogger(__name__)


class DomainBridge:
    """
    Bridge for non-FSM domains to expose health to TopologyAuditor.

    Args:
        domain_name: Must match owner field in verb_registry_v1.yaml
        bus: Optional FSMCore instance for emitting EVT:DOMAIN_STATUS
    """

    def __init__(self, domain_name: str, bus: Optional[Any] = None) -> None:
        self.domain_name = domain_name
        self._bus = bus
        self._health_fn: Optional[Callable[[], bool]] = None

    def register_health_fn(self, fn: Callable[[], bool]) -> None:
        """Register zero-argument health check. Replaces previous if called again."""
        self._health_fn = fn

    def is_healthy(self) -> bool:
        """
        Evaluate domain health. Returns True if no fn registered (optimistic).
        Returns False if fn returns False or raises.
        """
        if self._health_fn is None:
            return True
        try:
            return bool(self._health_fn())
        except Exception as exc:
            LOG.warning("DomainBridge[%s] health_fn raised: %s", self.domain_name, exc)
            return False

    def emit_status(self) -> None:
        """
        Emit EVT:DOMAIN_STATUS to bus. No-op if no bus configured.
        Never raises — all errors are logged.
        """
        if self._bus is None:
            return
        healthy = self.is_healthy()
        payload = {"domain": self.domain_name, "healthy": healthy}
        why = f"domain status: {'ok' if healthy else 'degraded'}"
        try:
            self._bus.emit("EVT:DOMAIN_STATUS", payload, why=why)
        except Exception as exc:
            LOG.warning("DomainBridge[%s] emit failed: %s", self.domain_name, exc)
```

#### Phase C — Verify

```bash
python -m pytest tests/vfoundation/obs/test_domain_bridge.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
# Must show: 770+ passed
```

---

## STEP 3.1 — TYPED PAYLOAD SCHEMAS (Phase 14C)

Before creating payloads, read `apps/reference/dictionaries/verb_registry_v1.yaml` to identify the top verbs used in the system. Build schemas for verbs actually registered.

#### Phase A — Write failing tests

Create `tests/vfoundation/core/test_payloads.py`:

```python
"""Tests for vfoundation.core.payloads — typed schemas (Phase 14C)."""
import pytest
from pydantic import ValidationError
from vfoundation.core.payloads import (
    OpenPayload, ClosePayload, FillPayload,
    CancelPayload, RejectPayload, ReconcilePayload,
)
from vfoundation.core.protocol import Message


class TestOpenPayload:
    def test_valid_buy(self):
        p = OpenPayload(symbol="BTCUSDT", side="BUY", qty=0.01)
        assert p.symbol == "BTCUSDT"
        assert p.price is None

    def test_valid_with_price(self):
        p = OpenPayload(symbol="ETHUSDT", side="SELL", qty=1.0, price=3000.0)
        assert p.price == 3000.0

    def test_invalid_side_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(symbol="BTC", side="LONG", qty=0.01)

    def test_missing_symbol_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(side="BUY", qty=0.01)

    def test_zero_qty_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(symbol="BTC", side="BUY", qty=0.0)

    def test_negative_qty_rejected(self):
        with pytest.raises(ValidationError):
            OpenPayload(symbol="BTC", side="BUY", qty=-1.0)

    def test_round_trip(self):
        p = OpenPayload(symbol="BTCUSDT", side="BUY", qty=0.5)
        assert OpenPayload(**p.model_dump()) == p


class TestClosePayload:
    def test_valid(self):
        p = ClosePayload(symbol="BTCUSDT", reason="tp_hit")
        assert p.symbol == "BTCUSDT"

    def test_missing_reason_rejected(self):
        with pytest.raises(ValidationError):
            ClosePayload(symbol="BTC")

    def test_reduce_only_default_true(self):
        p = ClosePayload(symbol="BTC", reason="sl")
        assert p.reduce_only is True


class TestFillPayload:
    def test_valid(self):
        p = FillPayload(order_id="abc", symbol="BTC", qty=0.01,
                        price=50000.0, ts_fill=1700000000000)
        assert p.order_id == "abc"

    def test_missing_order_id_rejected(self):
        with pytest.raises(ValidationError):
            FillPayload(symbol="BTC", qty=0.01, price=50000.0, ts_fill=1700000000000)


class TestCancelPayload:
    def test_valid(self):
        p = CancelPayload(order_id="x", symbol="ETH", reason="timeout")
        assert p.order_id == "x"

    def test_default_reason(self):
        p = CancelPayload(order_id="x", symbol="ETH")
        assert p.reason == "user_request"


class TestRejectPayload:
    def test_valid(self):
        p = RejectPayload(reason_code="NRR-011", message="Exposure limit exceeded")
        assert p.reason_code == "NRR-011"

    def test_optional_symbol(self):
        p = RejectPayload(reason_code="NRR-012", message="rate limit", symbol="BTC")
        assert p.symbol == "BTC"


class TestMessageTypedPayload:
    def test_typed_payload_open(self):
        msg = Message(
            op="DEC", verb="OPEN", src="decision_making",
            dst="execution_position", why="signal",
            pld={"symbol": "BTCUSDT", "side": "BUY", "qty": 0.01}
        )
        payload = msg.typed_payload(OpenPayload)
        assert isinstance(payload, OpenPayload)
        assert payload.symbol == "BTCUSDT"

    def test_typed_payload_wrong_data_raises(self):
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b", why="x",
                      pld={"symbol": "BTC"})  # missing side, qty
        with pytest.raises(ValidationError):
            msg.typed_payload(OpenPayload)

    def test_typed_payload_empty_pld_raises(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        with pytest.raises(ValidationError):
            msg.typed_payload(OpenPayload)

    def test_typed_payload_close(self):
        msg = Message(op="CMD", verb="CLOSE", src="a", dst="b", why="x",
                      pld={"symbol": "ETH", "reason": "manual"})
        payload = msg.typed_payload(ClosePayload)
        assert payload.symbol == "ETH"
```

Run — MUST fail.

#### Phase B — Create payloads.py

Create `vfoundation/core/payloads.py`:

```python
"""
Typed payload schemas — Phase 14C.

Pydantic models for opt-in type-safe access to Message.pld.
Does NOT change Message.pld (Dict[str, Any]) — backward compatible.

Usage:
    payload = msg.typed_payload(OpenPayload)
    assert payload.symbol == "BTCUSDT"

Registry-first: every verb here must exist in verb_registry_v1.yaml.
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class OpenPayload(BaseModel):
    """DEC:OPEN / CMD:OPEN — initiate a new position."""
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: float = Field(gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    reduce_only: bool = False
    model_config = {"extra": "ignore"}


class ClosePayload(BaseModel):
    """DEC:CLOSE / CMD:CLOSE — close an existing position."""
    symbol: str
    reason: str
    reduce_only: bool = True
    model_config = {"extra": "ignore"}


class FillPayload(BaseModel):
    """EVT:FILL — exchange fill notification."""
    order_id: str
    symbol: str
    qty: float = Field(gt=0)
    price: float = Field(gt=0)
    ts_fill: int
    side: Optional[Literal["BUY", "SELL"]] = None
    model_config = {"extra": "ignore"}


class CancelPayload(BaseModel):
    """CMD:CANCEL — cancel a pending order."""
    order_id: str
    symbol: str
    reason: str = "user_request"
    model_config = {"extra": "ignore"}


class RejectPayload(BaseModel):
    """ERR:REJECT — decision or execution rejection."""
    reason_code: str
    message: str
    symbol: Optional[str] = None
    model_config = {"extra": "ignore"}


class ReconcilePayload(BaseModel):
    """EVT:RECONCILE — position reconciliation result."""
    symbol: str
    internal_qty: Optional[float] = None
    external_qty: Optional[float] = None
    status: Literal["MATCH", "DIVERGED", "MISSING_LOCAL", "MISSING_EXTERNAL"]
    model_config = {"extra": "ignore"}
```

##### Add `typed_payload()` to Message

Read `vfoundation/core/protocol.py`. Add this method to class `Message` (after `is_expired`):

```python
def typed_payload(self, schema_cls: type) -> Any:
    """
    Parse pld as typed Pydantic schema.

    Args:
        schema_cls: Pydantic BaseModel subclass from vfoundation.core.payloads

    Returns:
        Validated schema_cls instance.

    Raises:
        pydantic.ValidationError: if pld doesn't match schema.
    """
    return schema_cls(**self.pld)
```

Add `from typing import Any` to imports if not present.

#### Phase C — Verify

```bash
python -m pytest tests/vfoundation/core/test_payloads.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
```

---

## STEP 3.2 — ExchangeContext

Create `tests/vfoundation/core/test_exchange_context.py`:

```python
"""Tests for ExchangeContext — Phase 14C shared exchange schema."""
import pytest
from pydantic import ValidationError
from vfoundation.core.exchange_context import ExchangeContext


class TestExchangeContext:
    def test_defaults(self):
        ctx = ExchangeContext(account_id="a1", session_id="s1")
        assert ctx.exchange == "binance"
        assert ctx.leverage == 1
        assert ctx.hedge_mode is False

    def test_custom_values(self):
        ctx = ExchangeContext(account_id="a", session_id="s",
                              exchange="okx", leverage=10, hedge_mode=True)
        assert ctx.leverage == 10
        assert ctx.hedge_mode is True

    def test_missing_account_id_raises(self):
        with pytest.raises(ValidationError):
            ExchangeContext(session_id="s")

    def test_missing_session_id_raises(self):
        with pytest.raises(ValidationError):
            ExchangeContext(account_id="a")

    def test_leverage_zero_raises(self):
        with pytest.raises(ValidationError):
            ExchangeContext(account_id="a", session_id="s", leverage=0)

    def test_leverage_exceeds_125_raises(self):
        with pytest.raises(ValidationError):
            ExchangeContext(account_id="a", session_id="s", leverage=126)

    def test_round_trip(self):
        ctx = ExchangeContext(account_id="x", session_id="y", leverage=5)
        assert ExchangeContext(**ctx.model_dump()) == ctx

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            ExchangeContext(account_id="a", session_id="s", unknown_field="x")
```

Create `vfoundation/core/exchange_context.py`:

```python
"""ExchangeContext — shared exchange session schema (Phase 14C)."""
from __future__ import annotations
from pydantic import BaseModel, Field


class ExchangeContext(BaseModel):
    """Shared context for all exchange-bound messages."""
    exchange: str = "binance"
    account_id: str
    session_id: str
    leverage: int = Field(default=1, ge=1, le=125)
    hedge_mode: bool = False
    model_config = {"extra": "forbid"}
```

Verify:
```bash
python -m pytest tests/vfoundation/core/test_exchange_context.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
```

---

## STEP 3.3 — PROTOCOL MIGRATION HELPER

Create `tests/vfoundation/core/test_protocol_migration.py`:

```python
"""Tests for protocol_migration helpers — Phase 14C."""
import pytest
from vfoundation.core.protocol import Message
from vfoundation.core.protocol_migration import migrate_pld_v1_to_v2, is_v2_message


class TestMigrate:
    def test_adds_v2_marker(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        migrated = migrate_pld_v1_to_v2(msg)
        assert migrated.pld.get("_v2") is True

    def test_original_message_not_mutated(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x",
                      pld={"key": "value"})
        migrate_pld_v1_to_v2(msg)
        assert "_v2" not in msg.pld

    def test_idempotent(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        once = migrate_pld_v1_to_v2(msg)
        twice = migrate_pld_v1_to_v2(once)
        assert once.pld == twice.pld

    def test_pld_fields_preserved(self):
        msg = Message(op="DEC", verb="OPEN", src="a", dst="b", why="x",
                      pld={"symbol": "BTC", "qty": 1.0})
        migrated = migrate_pld_v1_to_v2(msg)
        assert migrated.pld["symbol"] == "BTC"
        assert migrated.pld["qty"] == 1.0

    def test_mode_copied_to_pld(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x",
                      mode="backtest")
        migrated = migrate_pld_v1_to_v2(msg)
        assert migrated.pld.get("_mode") == "backtest"

    def test_returns_message_instance(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        assert isinstance(migrate_pld_v1_to_v2(msg), Message)

    def test_returns_new_object(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        assert migrate_pld_v1_to_v2(msg) is not msg


class TestIsV2:
    def test_v2_flag_true(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x",
                      pld={"_v2": True})
        assert is_v2_message(msg) is True

    def test_no_flag_false(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        assert is_v2_message(msg) is False

    def test_after_migration_returns_true(self):
        msg = Message(op="EVT", verb="TEST", src="a", dst="b", why="x")
        migrated = migrate_pld_v1_to_v2(msg)
        assert is_v2_message(migrated) is True
```

Create `vfoundation/core/protocol_migration.py`:

```python
"""Protocol migration helpers — Phase 14C backward-compatible v1→v2 migration."""
from __future__ import annotations
from typing import Any, Dict
from .protocol import Message


def migrate_pld_v1_to_v2(msg: Message) -> Message:
    """
    Return NEW Message with v2 pld conventions. Idempotent. Does not mutate input.
    """
    if msg.pld.get("_v2"):
        return msg
    new_pld: Dict[str, Any] = dict(msg.pld)
    new_pld["_v2"] = True
    if msg.mode and "_mode" not in new_pld:
        new_pld["_mode"] = msg.mode
    return msg.model_copy(update={"pld": new_pld})


def is_v2_message(msg: Message) -> bool:
    """Return True if message has been migrated to v2 pld conventions."""
    return bool(msg.pld.get("_v2"))
```

Verify:
```bash
python -m pytest tests/vfoundation/core/test_protocol_migration.py -v
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
# Must show: 800+ passed
```

---

## STEP 4 — MONOLITH DECOMPOSITION (Phase 14A)

**HIGHEST RISK. Execute last. Proceed step by step.**

### Pre-flight

```bash
# Establish canary baseline
python -m pytest tests/ -q --tb=no -k "decision_making" 2>&1 | tail -3
python -m pytest tests/ -q --tb=no -k "execution_position" 2>&1 | tail -3
```
Record counts. These are your canaries.

### 4.1 Audit decision_making.py

```bash
python -c "
lines = open('apps/reference/domains/decision_making/decision_making.py', encoding='utf-8').readlines()
print(f'Total lines: {len(lines)}')
"
grep -n "^def \|^class " apps/reference/domains/decision_making/decision_making.py | head -40
grep -rn "from.*decision_making.decision_making\|from.*decision_making import" . \
  --include="*.py" | grep -v __pycache__ | grep -v "decision_making.py"
```

If the file is already ≤500 LOC: skip Step 4.2 decomposition, note in log.

### 4.2 Strangler Fig — Incremental extraction

**For each module to extract** (identify natural boundaries from function list):

```
RULE: Extract ONE logical group at a time.
      Run full tests after EACH extraction.
      If tests break: git checkout apps/reference/domains/decision_making/decision_making.py
```

Extraction template:
1. Create `apps/reference/domains/decision_making/_<name>.py`
2. Move selected functions there
3. Add to `decision_making.py`: `from ._<name> import <function_names>`
4. Run: `python -m pytest tests/ -q --tb=no -k "decision_making" 2>&1 | tail -3`
5. All green → proceed to next extraction

### 4.3 execution_position/fsm.py check

```bash
ls apps/reference/domains/execution_position/fsm*.py
head -30 apps/reference/domains/execution_position/fsm.py
```

Verify `fsm.py` is a re-export wrapper if sub-files exist. If not: convert.

---

## STEP 5 — CLEANUP

```bash
# 5.1 Remove Windows nul artifact
python -c "
import pathlib
for p in pathlib.Path('.').rglob('nul'):
    if p.is_file():
        print(f'Deleting: {p}')
        p.unlink()
"

# 5.2 fsm_emit_compat check
grep -rn "fsm_emit_compat" . --include="*.py" | grep -v __pycache__
# If empty → delete vfoundation/core/fsm_emit_compat.py

# 5.3 Unused imports
python -m pyflakes vfoundation/ 2>&1 | grep "imported but unused"

# 5.4 TODO/FIXME scan
grep -rn "TODO\|FIXME\|HACK" vfoundation/ --include="*.py"

# 5.5 Type check
python -m mypy vfoundation/ --ignore-missing-imports --no-error-summary 2>&1 | grep "error:"
```

Fix ALL type errors before proceeding to Step 6.

Run full suite:
```bash
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
```

---

## STEP 6 — 100% COVERAGE AUDIT & GAP FILL

```bash
# 6.1 Full coverage measurement
python -m pytest tests/vfoundation/ \
  --cov=vfoundation \
  --cov-branch \
  --cov-report=term-missing \
  -q --tb=no 2>&1 | tee coverage_report.txt

# 6.2 Show only files below 95%
python -m pytest tests/vfoundation/ \
  --cov=vfoundation \
  --cov-branch \
  --cov-report=term-missing \
  -q --tb=no 2>&1 | grep -E "^\S.*%$" | awk -F'%' '{if ($1+0 < 95) print}'
```

For each file below 95%:
1. Read the source file to understand the missing lines/branches
2. Write a test that specifically exercises that path
3. Name it: `test_<function>_when_<scenario>`
4. Run after each addition to confirm coverage increases

### Critical 100% target files

These must reach 100% line AND branch coverage. Write tests until achieved:
- `vfoundation/core/protocol.py`
- `vfoundation/core/reconcile.py`
- `vfoundation/obs/xai_store.py`
- `vfoundation/obs/alert_manager.py`
- `vfoundation/obs/domain_bridge.py`
- `vfoundation/core/payloads.py`
- `vfoundation/core/exchange_context.py`
- `vfoundation/core/protocol_migration.py`

### Final coverage gate

```bash
python -m pytest tests/vfoundation/ --cov=vfoundation --cov-branch --cov-fail-under=95 -q
# MUST exit with code 0
```

---

## DEFINITION OF DONE — FINAL GATE

Run ALL commands. Record results in PROGRESS_LOG.md. Every check MUST PASS.

```bash
# DoD-1: No regressions
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
# MUST: 0 failed, 0 error

# DoD-2: New test count (must be significantly more than 716)
python -m pytest tests/vfoundation/ --co -q 2>&1 | tail -3
# MUST: 800+ collected

# DoD-3: Coverage gate
python -m pytest tests/vfoundation/ --cov=vfoundation --cov-fail-under=95 -q --tb=no 2>&1 | tail -3
# MUST: passed

# DoD-4: Zero type errors
python -m mypy vfoundation/ --ignore-missing-imports --no-error-summary 2>&1 | grep -c "error:" || echo 0
# MUST: 0

# DoD-5: No LOC violations
python -c "
import pathlib
violations = []
for f in pathlib.Path('vfoundation').rglob('*.py'):
    lines = len(f.read_text(encoding='utf-8').splitlines())
    if lines > 500:
        violations.append(f'{f}: {lines} LOC')
if violations:
    print('VIOLATIONS:')
    for v in violations: print(v)
else:
    print('OK: all files <= 500 LOC')
"

# DoD-6: CLI still works
python -m vfoundation.cli.vfound dict lint --global 2>&1 | tail -2
# MUST: dictionary: OK

# DoD-7: Verb registry gates pass
python -m pytest tests/vfoundation/test_verb_registry_warn_only.py -q --tb=short 2>&1 | tail -3
python -m pytest tests/vfoundation/test_verb_owner_inference_report.py -q --tb=short 2>&1 | tail -3
```

---

## FINAL PROGRESS_LOG.md ENTRY

```markdown
## FINAL STATUS — Phase 14 Complete

| Step | Status | Tests Added | Notes |
|------|--------|-------------|-------|
| 0.1 signing_ed25519 bugfix | ✅ | +4 | ValueError/TypeError now caught |
| 0.2 protocol truncate_why fix | ✅ | +9 | Syntax fixed, function now works |
| 1.1 FSMv2 validate_reachability | ✅ | +6 | BFS detects orphan states |
| 1.2 FSMv2 to_dot | ✅ | +6 | Graphviz DOT export |
| 1.3 FSMv2 get_stats | ✅ | +3 | Per-state key counts |
| 1.4 fsm_emit_compat cleanup | ✅ | - | Deleted (no references) |
| 2.1 TopologyAuditor health | ✅ | +8 | HealthCheck/HealthReport added |
| 2.2 DomainBridge | ✅ | +11 | New file, orphan domain support |
| 3.1 Payloads + typed_payload() | ✅ | +14 | 6 schemas, Message.typed_payload() |
| 3.2 ExchangeContext | ✅ | +7 | Shared exchange session schema |
| 3.3 protocol_migration | ✅ | +8 | migrate_pld_v1_to_v2(), is_v2_message() |
| 4 Monolith decomposition | ✅ | +N | Strangler Fig applied |
| 5 Cleanup | ✅ | - | nul deleted, dead imports removed |
| 6 Coverage gaps filled | ✅ | +M | All targets ≥ 95% |

## DoD: ALL PASSED ✅

- Final test count: <N> passed
- vfoundation coverage: <X>%
- Type errors: 0
- LOC violations: 0
- CLI: OK
```
