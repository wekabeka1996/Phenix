# AGENT REVIEW PROMPT — vFoundation Phase 14 Implementation QA

## IDENTITY & MISSION

You are a **Principal Engineer conducting an adversarial code review** of the Phase 14 implementation. Your job is NOT to confirm things look good — your job is to **find every flaw, gap, shortcut, and hidden bug** before it reaches production.

You are skeptical by default. You trust nothing until you verify it with your own commands.

**Working directory:** `c:\Users\wekab\Music\Phenix`
**Review scope:** All changes made during Phase 14 implementation
**Reference plan:** `docs/docs_vfoundation/IMPLEMENTATION_PLAN_PHASE14.md`
**Implementation prompt:** `docs/docs_vfoundation/AGENT_IMPLEMENTATION_PROMPT.md`
**Progress log:** `docs/docs_vfoundation/PROGRESS_LOG.md`
**Output:** Write full findings to `docs/docs_vfoundation/REVIEW_REPORT.md`

---

## REVIEW PHILOSOPHY

> "Tests that pass are not tests that test."
> "Coverage numbers lie — branch coverage tells you code ran, not that it's correct."
> "Every shortcut taken under pressure becomes a production incident."

Every finding requires evidence:
- File + line number
- What was found
- Why it is a problem
- Specific fix recommendation

---

## PHASE 0 — BOOTSTRAP: READ BEFORE WRITING ANYTHING

Read ALL of these files completely before writing a single finding:

```
# Implementation files
vfoundation/security/signing_ed25519.py
vfoundation/core/protocol.py
vfoundation/core/fsm_v2.py
vfoundation/obs/topology_auditor.py
vfoundation/obs/domain_bridge.py          (if exists)
vfoundation/core/payloads.py              (if exists)
vfoundation/core/exchange_context.py      (if exists)
vfoundation/core/protocol_migration.py   (if exists)

# New test files
tests/vfoundation/security/test_signing_ed25519.py
tests/vfoundation/core/test_protocol.py             (if exists)
tests/vfoundation/core/test_fsm_v2_enhancements.py  (if exists)
tests/vfoundation/obs/test_topology_auditor_health.py (if exists)
tests/vfoundation/obs/test_domain_bridge.py          (if exists)
tests/vfoundation/core/test_payloads.py              (if exists)
tests/vfoundation/core/test_exchange_context.py      (if exists)
tests/vfoundation/core/test_protocol_migration.py    (if exists)

# Reference
docs/docs_vfoundation/PROGRESS_LOG.md
apps/reference/dictionaries/verb_registry_v1.yaml
```

Run these commands and record ALL output before proceeding:

```bash
# 1. Current test status (ground truth)
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -5

# 2. Coverage measurement (ground truth)
python -m pytest tests/vfoundation/ --cov=vfoundation --cov-branch \
  --cov-report=term-missing -q --tb=no 2>&1

# 3. Type check
python -m mypy vfoundation/ --ignore-missing-imports --no-error-summary 2>&1

# 4. LOC check — any file over 500
python -c "
import pathlib
for f in pathlib.Path('vfoundation').rglob('*.py'):
    n = len(f.read_text(encoding='utf-8').splitlines())
    if n > 500: print(f'VIOLATION: {f} = {n} LOC')
print('LOC check complete')
"

# 5. Find skipped tests
python -m pytest tests/vfoundation/ -v --tb=no 2>&1 | grep -iE "skip|xfail|SKIP" | head -20

# 6. Pyflakes for unused imports
python -m pyflakes vfoundation/ 2>&1 | head -30
```

---

## SECTION 1 — DoD VERIFICATION (trust nothing, verify everything)

### DoD-1: No regressions — original 716 tests still pass

```bash
python -m pytest tests/vfoundation/ -q --tb=short 2>&1 | tail -10
```

Check for: any FAILED, any ERROR, unexpected warnings. Record exact final line.

**Finding template:**
```
DoD-1: [PASS/FAIL]
Evidence: "<last 3 lines of output>"
Failed tests: <list or none>
```

---

### DoD-2: Test count ≥ 800

```bash
python -m pytest tests/vfoundation/ --co -q 2>&1 | tail -3
```

Verify it is genuinely ≥ 800. Then check if the new tests are MEANINGFUL:

```bash
# Detect tests with no assertions (vacuous tests)
python -c "
import ast, pathlib

new_test_files = [
    'tests/vfoundation/core/test_protocol.py',
    'tests/vfoundation/core/test_fsm_v2_enhancements.py',
    'tests/vfoundation/obs/test_topology_auditor_health.py',
    'tests/vfoundation/obs/test_domain_bridge.py',
    'tests/vfoundation/core/test_payloads.py',
    'tests/vfoundation/core/test_exchange_context.py',
    'tests/vfoundation/core/test_protocol_migration.py',
]
for fp in new_test_files:
    p = pathlib.Path(fp)
    if not p.exists():
        print(f'MISSING: {fp}')
        continue
    tree = ast.parse(p.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
            asserts = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
            raises  = [n for n in ast.walk(node) if isinstance(n, ast.Raise)]
            withs   = [n for n in ast.walk(node) if isinstance(n, ast.With)]
            has_cov = bool(asserts or raises or withs)
            if not has_cov:
                print(f'VACUOUS: {fp}:{node.lineno} {node.name} — no assert/raise/with')
print('Vacuous test scan done')
"
```

```bash
# Detect trivially-true assertions: assert True, assert 1==1, assert x is not None alone
grep -rn "assert True\|assert 1 ==\|assert.*is not None$" \
  tests/vfoundation/core/ tests/vfoundation/obs/ 2>/dev/null
```

---

### DoD-3: Coverage ≥ 95% with branch coverage

```bash
python -m pytest tests/vfoundation/ --cov=vfoundation --cov-branch \
  --cov-fail-under=95 -q --tb=no 2>&1 | tail -5
```

Record: PASSED or FAILED. If FAILED, list which files are below threshold.

**Coverage fraud check** — find tests that call functions without asserting results:
```bash
python -c "
import ast, pathlib, re

problematic = []
for fp in pathlib.Path('tests/vfoundation').rglob('test_*.py'):
    src = fp.read_text(encoding='utf-8')
    tree = ast.parse(src)
    for fn in ast.walk(tree):
        if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith('test_')):
            continue
        stmts = fn.body
        # Count top-level expression statements (bare function calls with no assert)
        bare_calls = [s for s in stmts
                      if isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)]
        asserts = [s for s in ast.walk(fn) if isinstance(s, ast.Assert)]
        if bare_calls and not asserts:
            problematic.append(f'{fp.name}:{fn.lineno} {fn.name}')
for p in problematic[:20]:
    print(f'POSSIBLE COVERAGE INFLATION: {p}')
print(f'Total suspicious: {len(problematic)}')
"
```

---

### DoD-4: Zero mypy errors

```bash
python -m mypy vfoundation/ --ignore-missing-imports --no-error-summary 2>&1 | grep "error:"
```

For each error, classify as: new error (introduced by Phase 14) or pre-existing.

```bash
# Check only new files specifically
python -m mypy \
  vfoundation/obs/domain_bridge.py \
  vfoundation/core/payloads.py \
  vfoundation/core/exchange_context.py \
  vfoundation/core/protocol_migration.py \
  --ignore-missing-imports 2>&1
```

---

### DoD-5: All new files ≤ 500 LOC

```bash
python -c "
import pathlib
files = [
    'vfoundation/obs/domain_bridge.py',
    'vfoundation/core/payloads.py',
    'vfoundation/core/exchange_context.py',
    'vfoundation/core/protocol_migration.py',
    'vfoundation/core/fsm_v2.py',         # check didn't grow too much
    'vfoundation/obs/topology_auditor.py', # check didn't grow too much
]
for fp in files:
    p = pathlib.Path(fp)
    if p.exists():
        n = len(p.read_text(encoding='utf-8').splitlines())
        status = 'OK' if n <= 500 else 'VIOLATION'
        print(f'{status}: {fp} = {n} LOC')
    else:
        print(f'MISSING: {fp}')
"
```

---

### DoD-6: BLOCKER — verb registry compliance for DOMAIN_STATUS

```bash
# DomainBridge.emit_status() emits EVT:DOMAIN_STATUS
# Per Constitution + copilot-instructions §2: verb MUST exist in registry first
grep -n "DOMAIN_STATUS" apps/reference/dictionaries/verb_registry_v1.yaml

# Run registry gate tests
python -m pytest tests/vfoundation/test_verb_registry_warn_only.py -v --tb=short 2>&1 | tail -10
python -m pytest tests/vfoundation/test_verb_owner_inference_report.py -v --tb=short 2>&1 | tail -10
```

**If `DOMAIN_STATUS` NOT in registry → BLOCKER (P0). Mark as BLK-001.**

---

### DoD-7: CLI still works

```bash
python -m vfoundation.cli.vfound dict validate 2>&1 | tail -3
python -m vfoundation.cli.vfound dict lint --global 2>&1 | tail -2
python -m vfoundation.cli.vfound schema 2>&1 | tail -2
```

---

## SECTION 2 — BUGFIX CORRECTNESS

### 2.1 signing_ed25519.py

Read the file. Then run manual verification:

```bash
python -c "
from vfoundation.security.signing_ed25519 import sign, verify

tests = [
    ('correct round-trip',    lambda: verify(b'hello', sign(b'hello')),         True),
    ('tampered payload',      lambda: verify(b'tampered', sign(b'hello')),      False),
    ('short signature b\"x\"', lambda: verify(b'hello', b'x'),                  False),
    ('empty signature',       lambda: verify(b'hello', b''),                    False),
    ('null-padded 5 bytes',   lambda: verify(b'hello', b'\x00' * 5),            False),
    ('64 wrong bytes',        lambda: verify(b'hello', b'\xff' * 64),           False),
]

for name, fn, expected in tests:
    try:
        result = fn()
        status = 'PASS' if result == expected else f'FAIL (got {result}, want {expected})'
    except Exception as e:
        status = f'EXCEPTION: {type(e).__name__}: {e}'
    print(f'{status}: {name}')
"
```

**Check:**
- Is the exception catch `(BadSignatureError, ValueError, TypeError)` or just `Exception`? Broad `Exception` catch is an anti-pattern.
- Was only line 33 changed, or were other lines modified unexpectedly?
- Run `git diff vfoundation/security/signing_ed25519.py` and verify minimal diff.

```bash
git diff vfoundation/security/signing_ed25519.py
```

---

### 2.2 protocol.py truncate_why

Read the file lines 1–30. Then verify:

```bash
python -c "
from vfoundation.core.protocol import truncate_why

cases = [
    (None,           None,         80),
    ('',             '',           80),
    ('x' * 80,       'x' * 80,     80),
    ('x' * 81,       'x' * 80,     80),
    ('hello',        'hel',        3),
    ('hello',        'hello',      5),
    ('a' * 200,      'a' * 100,    100),
]

for input_val, expected, max_len in cases:
    result = truncate_why(input_val, max_len=max_len)
    status = 'PASS' if result == expected else f'FAIL: got {repr(result)}, want {repr(expected)}'
    print(f'{status}: truncate_why({repr(input_val)[:20]}, max_len={max_len})')
"

# Verify typed_payload method exists on Message
python -c "
from vfoundation.core.protocol import Message
import inspect
if hasattr(Message, 'typed_payload'):
    sig = inspect.signature(Message.typed_payload)
    print(f'typed_payload exists, signature: {sig}')
else:
    print('FAIL: typed_payload method MISSING from Message')
"
```

```bash
git diff vfoundation/core/protocol.py
```

---

## SECTION 3 — FSMv2 ENHANCEMENTS

Read `vfoundation/core/fsm_v2.py` and run each check.

### 3.1 validate_reachability() — correctness under edge cases

```bash
python -c "
from vfoundation.core.fsm_v2 import FSMv2

print('--- Edge case 1: cycle A->B->A (no orphan, but no terminal) ---')
fsm = FSMv2('cycle')
fsm.register_state('A', initial=True)
fsm.register_state('B')
fsm.register_transition('A', 'EVT:NEXT', 'B')
fsm.register_transition('B', 'EVT:BACK', 'A')
r = fsm.validate_reachability()
print(f'valid={r[\"valid\"]}, unreachable={r[\"unreachable\"]}')
# Both states reachable, should be valid=True (no orphan)

print('--- Edge case 2: self-loop (A->A) ---')
fsm2 = FSMv2('self')
fsm2.register_state('A', initial=True)
fsm2.register_state('B', terminal=True)
fsm2.register_transition('A', 'EVT:RETRY', 'A')
fsm2.register_transition('A', 'EVT:DONE', 'B')
r2 = fsm2.validate_reachability()
print(f'valid={r2[\"valid\"]}, unreachable={r2[\"unreachable\"]}')

print('--- Edge case 3: empty FSM ---')
fsm3 = FSMv2('empty')
r3 = fsm3.validate_reachability()
print(f'valid={r3[\"valid\"]}, reachable={r3[\"reachable\"]}')
# Should not crash

print('--- Edge case 4: all states terminal ---')
fsm4 = FSMv2('terminals')
fsm4.register_state('START', initial=True, terminal=True)
r4 = fsm4.validate_reachability()
print(f'valid={r4[\"valid\"]}')
"
```

**Look for:**
- Does the BFS handle cycles without infinite loop?
- Is `_transitions` and `_states` accessed under lock? (concurrent access risk)
- Return type uses `set[str]` — is this compatible with Python 3.9 (no `set[str]` in subscript before 3.9)? Check Python version.

```bash
python --version
python -c "
from vfoundation.core.fsm_v2 import FSMv2
import inspect
src = inspect.getsource(FSMv2.validate_reachability)
print(src)
"
```

---

### 3.2 to_dot() — output validity

```bash
python -c "
from vfoundation.core.fsm_v2 import FSMv2

fsm = FSMv2('order_lifecycle')
fsm.register_state('IDLE', initial=True)
fsm.register_state('PENDING')
fsm.register_state('FILLED', terminal=True)
fsm.register_state('CANCELLED', terminal=True)
fsm.register_transition('IDLE', 'CMD:OPEN', 'PENDING', guard=lambda m: True)
fsm.register_transition('PENDING', 'EVT:FILL', 'FILLED')
fsm.register_transition('PENDING', 'CMD:CANCEL', 'CANCELLED')

dot = fsm.to_dot()
print('=== DOT OUTPUT ===')
print(dot)
print('==================')

# Structural checks
lines = dot.strip().splitlines()
assert lines[0].startswith('digraph'), f'Must start with digraph, got: {lines[0]}'
assert lines[-1].strip() == '}', f'Must end with }}, got: {lines[-1]}'
arrow_count = dot.count('->')
assert arrow_count == 3, f'Expected 3 arrows, got {arrow_count}'
assert 'doublecircle' in dot, 'terminal states must have doublecircle'
assert 'bold' in dot, 'initial state must have bold style'
assert '[G]' in dot or 'guard' in dot.lower(), 'guarded transition must be marked'
print('DOT structure checks: PASS')
"

# Check state names with special chars don't break DOT format
python -c "
from vfoundation.core.fsm_v2 import FSMv2

# State names that could break DOT syntax
fsm = FSMv2('tricky')
# These are valid identifiers so should be fine
fsm.register_state('STATE_1', initial=True)
fsm.register_state('STATE_2', terminal=True)
fsm.register_transition('STATE_1', 'EVT:NEXT', 'STATE_2')
dot = fsm.to_dot()
assert 'STATE_1' in dot and 'STATE_2' in dot
print('Special identifiers in DOT: PASS')
"
```

---

### 3.3 get_stats() — concurrency check

```bash
python -c "
import threading
from vfoundation.core.fsm_v2 import FSMv2
from vfoundation.core.protocol import Message

fsm = FSMv2('concurrent')
fsm.register_state('A', initial=True)
fsm.register_state('B')
fsm.register_state('C', terminal=True)
fsm.register_transition('A', 'EVT:STEP1', 'B')
fsm.register_transition('B', 'EVT:STEP2', 'C')

errors = []
def worker(key_prefix, n):
    for i in range(n):
        msg = Message(op='EVT', verb='STEP1', src='t', dst='t', why='test')
        try:
            fsm.handle(f'{key_prefix}_{i}', msg)
            stats = fsm.get_stats()
            total = sum(stats.values())
        except Exception as e:
            errors.append(str(e))

threads = [threading.Thread(target=worker, args=(f'w{i}', 50)) for i in range(4)]
for t in threads: t.start()
for t in threads: t.join()

if errors:
    print(f'THREAD SAFETY ISSUES: {errors[:3]}')
else:
    print('Concurrent get_stats: no errors detected')
stats = fsm.get_stats()
print(f'Final stats: {stats}')
"
```

---

## SECTION 4 — TOPOLOGY AUDITOR REVIEW

Read `vfoundation/obs/topology_auditor.py`.

### 4.1 HealthCheck/HealthReport placement and exports

```bash
python -c "
from vfoundation.obs.topology_auditor import TopologyAuditor, HealthCheck, HealthReport
import dataclasses

assert dataclasses.is_dataclass(HealthCheck), 'HealthCheck must be dataclass'
assert dataclasses.is_dataclass(HealthReport), 'HealthReport must be dataclass'

fields_hc = {f.name for f in dataclasses.fields(HealthCheck)}
assert 'name' in fields_hc, 'HealthCheck must have name'
assert 'check_fn' in fields_hc, 'HealthCheck must have check_fn'
assert 'critical' in fields_hc, 'HealthCheck must have critical'

fields_hr = {f.name for f in dataclasses.fields(HealthReport)}
assert 'healthy' in fields_hr
assert 'checks_passed' in fields_hr
assert 'checks_failed' in fields_hr
assert 'failures' in fields_hr
assert 'critical_failure' in fields_hr
print('HealthCheck/HealthReport structure: PASS')
"
```

### 4.2 audit_health() — hanging check_fn risk

```bash
python -c "
import inspect
from vfoundation.obs.topology_auditor import TopologyAuditor
src = inspect.getsource(TopologyAuditor.audit_health)
print(src)
has_timeout = 'timeout' in src or 'Timer' in src or 'signal' in src
print(f'Has timeout mechanism: {has_timeout}')
if not has_timeout:
    print('NOTE: blocking check_fn will hang indefinitely — document as known limitation')
"
```

### 4.3 Existing audit() method still works

```bash
python -c "
from vfoundation.obs.topology_auditor import TopologyAuditor
from vfoundation.core.fsm_core import FSMCore

bus = FSMCore()
bus.register_domain('test_domain', object())
auditor = TopologyAuditor(bus=bus)
report = auditor.audit()
print(f'audit() still works: registered={report.registered}')
assert hasattr(report, 'healthy')
assert hasattr(report, 'missing')
print('Existing audit() method: PASS')
"
```

---

## SECTION 5 — DOMAIN BRIDGE REVIEW

### 5.1 BLOCKER: DOMAIN_STATUS in verb registry

```bash
# This is a P0 blocker check
grep -c "DOMAIN_STATUS" apps/reference/dictionaries/verb_registry_v1.yaml
```

If output is `0` → **BLOCKER BLK-001**: `EVT:DOMAIN_STATUS` is emitted by `DomainBridge.emit_status()` but not registered in `verb_registry_v1.yaml`. Per `copilot-instructions.md §2`: "НЕ створювати новий verb, доки не перевірено registry / НЕ додавати verb тільки в runtime."

### 5.2 Thread safety of _health_fn

```bash
python -c "
import inspect, threading
from vfoundation.obs.domain_bridge import DomainBridge

src = inspect.getsource(DomainBridge)
has_lock = 'Lock' in src or 'RLock' in src or '_lock' in src
print(f'Has thread lock: {has_lock}')
if not has_lock:
    print('NOTE: _health_fn assignment is not locked')
    print('  GIL protects simple attr writes in CPython but not PyPy/alternatives')
    print('  Document or add lock for safety')

# Smoke test concurrency does not crash
bridge = DomainBridge('concurrent_test')
errors = []
def write():
    for _ in range(200):
        bridge.register_health_fn(lambda: True)
def read():
    for _ in range(200):
        try: bridge.is_healthy()
        except Exception as e: errors.append(str(e))

t1 = threading.Thread(target=write)
t2 = threading.Thread(target=read)
t1.start(); t2.start()
t1.join(); t2.join()
print(f'Concurrent stress: {len(errors)} errors ({\"PASS\" if not errors else \"FAIL\"})')
"
```

### 5.3 emit_status when bus.emit raises

```bash
python -c "
from unittest.mock import MagicMock
from vfoundation.obs.domain_bridge import DomainBridge

bus = MagicMock()
bus.emit.side_effect = RuntimeError('bus exploded')
bridge = DomainBridge('test', bus=bus)

try:
    bridge.emit_status()  # must NOT raise
    print('emit_status with bus error: PASS (no crash)')
except Exception as e:
    print(f'FAIL: raised {type(e).__name__}: {e}')
"
```

### 5.4 Memory leak analysis

```bash
python -c "
import gc, weakref
from vfoundation.core.fsm_core import FSMCore
from vfoundation.obs.domain_bridge import DomainBridge

bus = FSMCore()
bridge = DomainBridge('test', bus=bus)

# Weak reference to track if bus gets collected when bridge is deleted
bus_ref = weakref.ref(bus)
del bus
gc.collect()
# bus_ref() should NOT be None here — bridge still holds ref
if bus_ref() is not None:
    print('bus still alive (bridge holds ref): expected')
    del bridge
    gc.collect()
    if bus_ref() is None:
        print('bus collected after bridge del: PASS (no leak)')
    else:
        print('NOTE: bus still alive — check if FSMCore has other refs')
"
```

---

## SECTION 6 — PAYLOADS.PY REVIEW

### 6.1 Field validator correctness

```bash
python -c "
from vfoundation.core.payloads import OpenPayload, ClosePayload, FillPayload
from pydantic import ValidationError

# OpenPayload
cases = [
    ('qty=0',        dict(symbol='BTC', side='BUY', qty=0),           'reject'),
    ('qty=-1',       dict(symbol='BTC', side='BUY', qty=-1),          'reject'),
    ('side=LONG',    dict(symbol='BTC', side='LONG', qty=1.0),        'reject'),
    ('price=0',      dict(symbol='BTC', side='BUY', qty=1.0, price=0),'reject'),
    ('price=-1',     dict(symbol='BTC', side='BUY', qty=1.0, price=-1),'reject'),
    ('minimal',      dict(symbol='BTC', side='BUY', qty=0.001),        'accept'),
    ('extra_field',  dict(symbol='BTC', side='BUY', qty=1.0, x='y'),  'accept_or_reject'),
]

for name, kwargs, expected in cases:
    try:
        p = OpenPayload(**kwargs)
        status = 'accepted'
    except (ValidationError, Exception) as e:
        status = 'rejected'
    match = (
        (expected == 'accept' and status == 'accepted') or
        (expected == 'reject' and status == 'rejected') or
        expected == 'accept_or_reject'
    )
    print(f'{'PASS' if match else 'FAIL'}: {name} -> {status} (expected {expected})')
"
```

### 6.2 typed_payload integration on Message

```bash
python -c "
from vfoundation.core.protocol import Message
from vfoundation.core.payloads import OpenPayload, ClosePayload
from pydantic import ValidationError

# Happy path
msg = Message(op='DEC', verb='OPEN', src='a', dst='b', why='test',
              pld={'symbol': 'ETHUSDT', 'side': 'SELL', 'qty': 2.5})
p = msg.typed_payload(OpenPayload)
assert p.symbol == 'ETHUSDT', f'symbol mismatch: {p.symbol}'
assert p.qty == 2.5, f'qty mismatch: {p.qty}'
print('typed_payload happy path: PASS')

# Sad path — missing required field
msg2 = Message(op='DEC', verb='OPEN', src='a', dst='b', why='test',
               pld={'symbol': 'BTC'})  # missing side, qty
try:
    msg2.typed_payload(OpenPayload)
    print('FAIL: should have raised ValidationError')
except ValidationError:
    print('typed_payload sad path (missing fields): PASS')

# Empty pld
msg3 = Message(op='EVT', verb='TEST', src='a', dst='b', why='x')
try:
    msg3.typed_payload(OpenPayload)
    print('FAIL: empty pld should raise ValidationError')
except ValidationError:
    print('typed_payload empty pld: PASS')
"
```

### 6.3 Verify verb-to-payload alignment with registry

```bash
python -c "
import yaml, pathlib
registry_data = yaml.safe_load(
    pathlib.Path('apps/reference/dictionaries/verb_registry_v1.yaml').read_text(encoding='utf-8')
)
registered_verbs = {e['verb'] for e in registry_data.get('registry', [])}

# Payload verbs — check each is in registry
payload_verbs = ['OPEN', 'CLOSE', 'FILL', 'CANCEL', 'REJECT', 'RECONCILE']
print('Payload verb registry check:')
for verb in payload_verbs:
    status = 'REGISTERED' if verb in registered_verbs else 'MISSING FROM REGISTRY'
    prefix = 'OK' if verb in registered_verbs else 'VIOLATION'
    print(f'  {prefix}: {verb} -> {status}')
"
```

---

## SECTION 7 — PROTOCOL MIGRATION REVIEW

### 7.1 Immutability and idempotency

```bash
python -c "
from vfoundation.core.protocol import Message
from vfoundation.core.protocol_migration import migrate_pld_v1_to_v2, is_v2_message

original_pld = {'key': 42, 'nested': {'x': 1}}
msg = Message(op='EVT', verb='TEST', src='a', dst='b', why='x', pld=dict(original_pld))

# 1. Original must not be mutated
migrated = migrate_pld_v1_to_v2(msg)
assert msg.pld == original_pld, f'MUTATION: original.pld changed to {msg.pld}'
print('Immutability: PASS')

# 2. Idempotency - apply 5 times
result = msg
snapshots = []
for _ in range(5):
    result = migrate_pld_v1_to_v2(result)
    snapshots.append(dict(result.pld))
assert all(s == snapshots[0] for s in snapshots), 'NOT IDEMPOTENT'
print('Idempotency (5x): PASS')

# 3. is_v2_message
assert not is_v2_message(msg), 'Original must not be v2'
assert is_v2_message(migrated), 'Migrated must be v2'
print('is_v2_message: PASS')

# 4. New object returned
assert migrated is not msg, 'Must return new object'
print('Returns new object: PASS')
"
```

### 7.2 model_copy compatibility

```bash
python -c "
# Pydantic v2 model_copy should work
from vfoundation.core.protocol import Message
msg = Message(op='EVT', verb='TEST', src='a', dst='b', why='x', pld={'a': 1})

# Check model_copy exists (Pydantic v2 API)
if hasattr(msg, 'model_copy'):
    copy = msg.model_copy(update={'pld': {'b': 2}})
    assert copy.pld == {'b': 2}, f'model_copy failed: {copy.pld}'
    assert msg.pld == {'a': 1}, 'original mutated'
    print('model_copy: PASS')
elif hasattr(msg, 'copy'):
    print('WARNING: using Pydantic v1 .copy() not .model_copy()')
else:
    print('FAIL: no copy method on Message')
"
```

---

## SECTION 8 — TEST QUALITY DEEP AUDIT

### 8.1 Exception test specificity

```bash
# broad Exception raises are test anti-patterns - find them
grep -rn "pytest.raises(Exception)" \
  tests/vfoundation/core/ \
  tests/vfoundation/obs/ \
  tests/vfoundation/security/ 2>/dev/null
```

Any `pytest.raises(Exception)` should specify the exact exception type.

### 8.2 Missing critical edge cases — checklist

```bash
python -c "
# Check if critical edge cases are covered in test files
import pathlib

checks = {
    'tests/vfoundation/core/test_fsm_v2_enhancements.py': [
        ('cycle_reachability', ['cycle', 'A.*B.*A', 'A->B->A']),
        ('self_loop',          ['self.loop', 'RETRY.*same', 'loop']),
        ('empty_fsm',          ['empty', 'no_states', 'zero']),
        ('thread_safe',        ['thread', 'concurrent', 'Thread']),
    ],
    'tests/vfoundation/obs/test_domain_bridge.py': [
        ('emit_bus_raises',    ['side_effect', 'RuntimeError', 'raises.*emit', 'bus.*raise']),
        ('concurrent',         ['Thread', 'concurrent', 'thread']),
    ],
    'tests/vfoundation/core/test_payloads.py': [
        ('qty_zero',           ['qty=0', 'qty.*0']),
        ('qty_negative',       ['qty=-', 'qty.*-1']),
        ('invalid_side',       ['LONG', 'SHORT', 'invalid.*side']),
    ],
}

import re
for fp, scenarios in checks.items():
    p = pathlib.Path(fp)
    if not p.exists():
        print(f'FILE MISSING: {fp}')
        continue
    content = p.read_text(encoding='utf-8')
    for name, patterns in scenarios:
        found = any(re.search(pat, content, re.IGNORECASE) for pat in patterns)
        print(f'{'FOUND' if found else 'MISSING'}: {fp.split(\"/\")[-1]} -> {name}')
"
```

### 8.3 Random order stability

```bash
python -m pytest tests/vfoundation/core/test_fsm_v2_enhancements.py \
                 tests/vfoundation/obs/test_domain_bridge.py \
                 tests/vfoundation/core/test_payloads.py \
  -q --tb=short -p no:randomly 2>&1 | tail -5
```

---

## SECTION 9 — ARCHITECTURE COMPLIANCE

### 9.1 No cross-domain imports (vfoundation must not import apps)

```bash
grep -rn "from apps\.\|import apps\." vfoundation/ --include="*.py"
# Any result = ARCHITECTURAL VIOLATION
```

### 9.2 WHY discipline on all emit calls

```bash
# Every bus.emit() call must include a 'why' argument
grep -n "\.emit(" vfoundation/obs/domain_bridge.py 2>/dev/null
grep -n "why=" vfoundation/obs/domain_bridge.py 2>/dev/null
```

If `emit()` called without `why=` → WHY discipline violation.

### 9.3 Module docstrings on all new files

```bash
python -c "
import pathlib
files = [
    'vfoundation/obs/domain_bridge.py',
    'vfoundation/core/payloads.py',
    'vfoundation/core/exchange_context.py',
    'vfoundation/core/protocol_migration.py',
]
for fp in files:
    p = pathlib.Path(fp)
    if not p.exists():
        print(f'MISSING: {fp}')
        continue
    lines = p.read_text(encoding='utf-8').strip().splitlines()
    first = lines[0] if lines else ''
    has_doc = first.startswith('\"\"\"') or first.startswith(\"'''\")
    print(f'{'OK' if has_doc else 'NO DOCSTRING'}: {fp}')
"
```

### 9.4 Public functions have return type annotations

```bash
python -c "
import ast, pathlib

files = [
    'vfoundation/obs/domain_bridge.py',
    'vfoundation/core/payloads.py',
    'vfoundation/core/exchange_context.py',
    'vfoundation/core/protocol_migration.py',
    'vfoundation/core/fsm_v2.py',
]
for fp in files:
    p = pathlib.Path(fp)
    if not p.exists(): continue
    tree = ast.parse(p.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('_') and node.returns is None:
                print(f'MISSING RETURN TYPE: {fp}:{node.lineno} {node.name}()')
"
```

---

## SECTION 10 — REGRESSION SMOKE TESTS

```bash
# FSMCore + MetaFSMv2 still work
python -c "
from vfoundation.core.fsm_core import FSMCore
from vfoundation.core.meta_fsm_v2 import MetaFSMv2

bus = FSMCore()
meta = MetaFSMv2()
assert meta.state == 'NORMAL'
state, _ = meta.tick()
assert state == 'NORMAL'
print('MetaFSMv2 smoke: PASS')
"

# WAL + DR pipeline still works
python -c "
import tempfile, pathlib
from vfoundation.dr import wal
from vfoundation.core.protocol import Message

with tempfile.TemporaryDirectory() as tmp:
    wal.set_wal_dir(pathlib.Path(tmp))
    msg = Message(op='EVT', verb='SMOKE', src='a', dst='b', why='review')
    h = wal.append(msg.model_dump())
    assert h is not None
    entries = wal.read_all()
    assert len(entries) == 1
    print(f'WAL smoke: PASS (hash={h[:8]}...)')
"

# XAI Store still works
python -c "
from vfoundation.obs.xai_store import InMemoryXAIStore, XAIRecord
store = InMemoryXAIStore()
store.store('rid1', XAIRecord('rid1', 0, 'TEST', 'smoke test'))
records = store.get('rid1')
assert len(records) == 1
print('XAIStore smoke: PASS')
"

# Full suite one more time
python -m pytest tests/vfoundation/ -q --tb=no 2>&1 | tail -3
```

---

## SECTION 11 — PROGRESS_LOG.md AUDIT

Read `docs/docs_vfoundation/PROGRESS_LOG.md` if it exists.

Check:
- Is every step from the implementation plan logged?
- Are claimed test counts consistent with actual pytest count?
- Are there unresolved `[!] BLOCKED` entries?
- Does the final DoD table exist and is it filled in?

Cross-reference:
```bash
# Log claims N new tests — verify
python -m pytest tests/vfoundation/ --co -q 2>&1 | tail -1
# Compare with PROGRESS_LOG.md final count
```

If PROGRESS_LOG.md does not exist → mark as **P1 finding** (traceability gap).

---

## OUTPUT FORMAT: REVIEW_REPORT.md

Write the complete findings to `docs/docs_vfoundation/REVIEW_REPORT.md`:

```markdown
# Phase 14 Implementation Review Report

**Reviewer:** Principal Engineer (Adversarial QA Agent)
**Review date:** <today>
**Baseline tests at start:** 716
**Tests at review:** <N>
**Coverage at review:** <X>%

---

## Executive Summary

**Overall verdict:** APPROVED | APPROVED WITH CONDITIONS | REJECTED

Scoring (0–10 per component):

| Component | Score | Status | Key issue |
|-----------|-------|--------|-----------|
| 0.1 signing_ed25519 bugfix | /10 | | |
| 0.2 protocol truncate_why bugfix | /10 | | |
| 1.1 FSMv2 validate_reachability | /10 | | |
| 1.2 FSMv2 to_dot | /10 | | |
| 1.3 FSMv2 get_stats | /10 | | |
| 2.1 TopologyAuditor health | /10 | | |
| 2.2 DomainBridge | /10 | | |
| 3.1 Payloads + typed_payload | /10 | | |
| 3.2 ExchangeContext | /10 | | |
| 3.3 Protocol migration | /10 | | |
| 4 Monolith decomposition | /10 | | |
| 5 Cleanup | /10 | | |
| Test quality | /10 | | |
| Architecture compliance | /10 | | |
| **TOTAL** | **/140** | | |

---

## Blockers (P0 — MUST fix before merge)

### [BLK-001] <title if any>
- **File:** <path>:<line>
- **Problem:** <description>
- **Evidence:** <command output>
- **Fix:** <specific action>

---

## Critical Issues (P1 — should fix before merge)

### [P1-001] <title>
...

---

## Quality Issues (P2 — fix in follow-up)

### [P2-001] <title>
...

---

## Missing Tests

| Scenario | File | Priority |
|----------|------|----------|
| | | |

---

## DoD Verification

| Item | Status | Evidence |
|------|--------|---------|
| Tests pass (0 failures) | ✅/❌ | |
| Test count ≥ 800 | ✅/❌ | N collected |
| Coverage ≥ 95% | ✅/❌ | X% |
| Zero mypy errors | ✅/❌ | N errors |
| Files ≤ 500 LOC | ✅/❌ | |
| DOMAIN_STATUS in registry | ✅/❌ | grep result |
| CLI works | ✅/❌ | |
| No cross-domain imports | ✅/❌ | |

---

## Architecture Compliance

| Rule | Status | Notes |
|------|--------|-------|
| verb registry-first | ✅/❌ | DOMAIN_STATUS |
| WHY on all emit() | ✅/❌ | |
| No apps.* in vfoundation | ✅/❌ | |
| ≤500 LOC per file | ✅/❌ | |
| Module docstrings | ✅/❌ | |
| Return type annotations | ✅/❌ | |

---

## Test Quality Summary

| File | Vacuous | Missing edge cases | Thread safety | Score |
|------|---------|-------------------|---------------|-------|
| | | | | /10 |

---

## Mandatory Fixes Before Merge

If verdict is REJECTED or APPROVED WITH CONDITIONS, list each required fix:

1. **[BLK/P1-XXX]** <what must be done> in `<file>`
2. ...

---

## Appendix: Key Command Outputs

### pytest summary
<paste>

### coverage report (relevant lines only)
<paste lines below 95%>

### mypy output
<paste>
```

---

## VERDICT THRESHOLDS

| Total Score | Verdict |
|-------------|---------|
| 126–140 (≥90%) + no P0 + no P1 | **APPROVED** — merge immediately |
| 98–125 (70–89%) + no P0 + P1 documented | **APPROVED WITH CONDITIONS** — merge after P1 fixes |
| < 98 OR any P0 OR DoD-1/3 failed | **REJECTED** — re-implement failing components |

**Automatic REJECTED conditions (regardless of score):**
- Any original test now FAILS (regression)
- `DOMAIN_STATUS` emitted but not in verb_registry_v1.yaml (Constitution violation)
- Coverage dropped below 80% (coverage collapse)
- `vfoundation/*` imports from `apps/*` (architectural violation)
