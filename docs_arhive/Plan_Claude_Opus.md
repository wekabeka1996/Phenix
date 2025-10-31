                                                          #                           Aurora     vFoundation FSM Federation

##                          : `docs/PLAN_AURORA_TO_VFOUNDATION.md`

```markdown
# PLAN: Aurora Core Migration to vFoundation FSM Federation
**Plan ID:** AURORA_VFOUND_MIGRATION_v1  
**Created:** 2024-01-15T10:00:00Z  
**Target:** Production-ready FSM-based trading system  
**Machine Protocol:** v1.0.0

## Executive Summary
Systematic migration of Aurora trading logic to vFoundation FSM architecture with LLM-first documentation protocol.

## Phase Map
| Phase | ID | Title | Duration | Gate Threshold |
|-------|-----|-------|----------|----------------|
| A | PH-AUDIT | Source Audit & Gap Analysis | 2d | 100% inventory |
| B | PH-SSOT | Protocol & Schema Definition | 3d | Schema validation |
| C | PH-INFRA | Quality Infrastructure | 2d | Tools configured |
| D | PH-SKELETON | Walking Skeleton | 3d | E2E pass |
| E | PH-LAYERS | Layer-wise Aurora Port | 10d | Per-layer gates |
| F | PH-CONNECTORS | Adapters & Connectors | 3d | Stress tests pass |
| G | PH-ORCHESTRATION | Config & Runner | 2d | CLI functional |
| H | PH-RESILIENCE | Load & Chaos Testing | 3d | SLO met |
| I | PH-PRODUCTION | Final Integration | 2d | All gates pass |

---

## PHASE A: Source Audit & Gap Analysis

### A1. Doctrine Analysis
**Input:** `docs/` directory  
**Output:** `reports/doctrine_matrix.json`  
**Machine Steps:**
```json
{
  "step": "A1",
  "actions": [
    "parse: docs/*.md     extract principles",
    "categorize: {fsm_rules, aurora_logic, vfound_patterns}",
    "index: create searchable doctrine DB"
  ]
}
```

### A2. Code Inventory
**Input:** `vfoundation/`, `apps/`, `aurora/`  
**Output:** `reports/code_inventory.json`  
```json
{
  "modules": {
    "vfoundation": ["core", "router", "ttl", "idempotency", "obs", "security"],
    "apps/reference": ["domains/*", "config_loader", "main"],
    "aurora": ["risk/*", "strategy/*", "execution/*"]
  }
}
```

### A3. Gap Mapping
**Output:** `reports/gaps_schema.json`  
```json
{
  "missing_from_vfound": [
    {"component": "regime_detector", "source": "aurora/regime/", "priority": "P1"},
    {"component": "advanced_risk", "source": "aurora/risk/portfolio.py", "priority": "P1"},
    {"component": "tca_engine", "source": "aurora/execution/tca.py", "priority": "P2"}
  ]
}
```

### A4. Gate: Audit Complete
**Criteria:** 100% files indexed, gaps documented  
**Artifact:** `PH_AUDIT_GATE_REPORT.md`

---

## PHASE B: SSOT Protocol Definition

### B1. Domain Schemas
**Output:** `schemas/domains/*.schema.json`
- risk_domain.schema.json
- execution_domain.schema.json  
- strategy_domain.schema.json
- observability_domain.schema.json

### B2. FSM Contract
**Output:** `docs/FSM_PROTOCOL.md` + `schemas/fsm_protocol.schema.json`
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "fsm_protocol_v1",
  "type": "object",
  "required": ["op", "rid", "ttl", "why", "payload"],
  "properties": {
    "op": {"enum": ["DEC", "CMD", "QRY", "EVT", "ACK", "ERR"]},
    "rid": {"type": "string", "pattern": "^[A-Z0-9]{8}-[A-Z0-9]{4}$"},
    "ttl": {"type": "integer", "minimum": 0, "maximum": 60000},
    "why": {"type": "string", "maxLength": 80}
  }
}
```

### B3. Porting Interfaces
**Output:** `docs/AURORA_PORTING_IFACE.md`
```markdown
| Aurora Component | vFound Interface | DTO Schema | Error Codes |
|-----------------|------------------|------------|-------------|
| RiskEngine | IRiskAssessor | risk_assessment.json | RISK_* |
| OrderManager | IExecutionAdapter | order_intent.json | EXEC_* |
```

### B4. Gate: Protocols Defined
**Criteria:** All schemas validate, interfaces documented  
**Artifact:** `PH_SSOT_GATE_REPORT.md`

---

## PHASE C: Quality Infrastructure

### C1. Tooling Setup
**Actions:**
```bash
# .pre-commit-config.yaml
- mypy --strict --ignore-missing-imports
- ruff check --fix
- pytest --cov-min=90
```

### C2. Quality Metrics
**Output:** `ops/quality_metrics.yaml`
```yaml
gates:
  coverage: 90
  latency_p95_ms: 50
  why_ratio: 0.98
  timeout_rate_pct: 1
  idempotency: enforced
```

### C3. LLM Tracking
**Initialize:**
- `ops/LLM_LOG.jsonl` 
- `ops/PROGRESS_TRACKER.md`
- `reports/index.json`

### C4. Gate: Infrastructure Ready
**Criteria:** All tools pass smoke tests  
**Artifact:** `PH_INFRA_GATE_REPORT.md`

---

## PHASE D: Walking Skeleton

### D1. Minimal Flow Selection
**Path:** market_tick     risk_check     mock_order     log
**Components:** 
- MarketDataDomain (existing)
- RiskGateDomain (stub)
- MockExecutionDomain (new)
- ObservabilityDomain (extend)

### D2. Skeleton Implementation
**Output:** `apps/reference/skeleton/`
```python
# skeleton_flow.py
async def minimal_trading_flow(tick: MarketTick) -> TradeResult:
    risk = await risk_gate.check(tick)  # stub
    if risk.approved:
        order = await mock_exec.place(tick)  # stub
        await obs.log_trade(order)
    return TradeResult(order_id=order.id if risk.approved else None)
```

### D3. E2E Test Suite
**Output:** `tests/e2e/test_skeleton.py`
**Coverage Target:** 100% of skeleton path

### D4. Gate: Skeleton Functional
**Criteria:** E2E tests pass, latency < 25ms  
**Artifact:** `PH_SKELETON_GATE_REPORT.md`

---

## PHASE E: Layer-wise Aurora Porting

### E1. Risk Layer
**Source:** risk  
**Target:** `vfoundation/domains/risk/`
**Components:**
- CVaR calculator
- Dynamic position limits
- Kelly sizing
- Portfolio risk aggregator

**Gate:** Unit tests 95%, integration pass

### E2. Execution Layer  
**Source:** `aurora/execution/`  
**Target:** `vfoundation/domains/execution/`
**Components:**
- Order lifecycle FSM
- Idempotency ledger
- Rate limiter with backoff
- OCO/reduceOnly logic

**Gate:** Idempotency proven, latency p95 < 50ms

### E3. Strategy Layer
**Source:** `aurora/strategy/`  
**Target:** `vfoundation/domains/strategy/`
**Components:**
- Signal generators (lightweight)
- Parameter store
- Strategy state machine

**Gate:** Signals validated, state transitions correct

### E4. Observability Layer
**Target:** `vfoundation/obs/`
**Components:**
- JSONL structured logger
- Metrics collector
- WHY chain tracker
- Panic bundle generator

**Gate:** WHY ratio > 0.98, logs valid

### E5. Security Layer
**Target:** `vfoundation/security/`
**Components:**
- Ed25519 signer/verifier
- RBAC middleware
- Secret manager interface
- Audit trail writer

**Gate:** Signatures verify, RBAC blocks unauthorized

### E6. Per-Layer Gates
**Artifact Template:** `PH_LAYERS_{LAYER}_GATE_REPORT.md`

---

## PHASE F: Connectors & Adapters

### F1. Standardized Contracts
**Output:** `vfoundation/adapters/base.py`
```python
@dataclass
class AdapterResponse:
    success: bool
    data: Optional[Any]
    error_code: Optional[str]
    retry_after: Optional[int]
```

### F2. Optional Dependencies
**Output:** `vfoundation/core/guards.py`
```python
class OptionalImportGuard:
    def __init__(self, module: str, fallback: Any):
        try:
            self.impl = importlib.import_module(module)
        except ImportError:
            self.impl = fallback
```

### F3. Stress Testing
**Tests:** Throttling, disconnects, timeouts  
**Gate:** 99% requests recover within 3 retries

---

## PHASE G: Orchestration & Config

### G1. Runner Implementation
**Output:** `apps/runner.py`
```python
class AuroraRunner:
    async def preflight_checks(self) -> bool
    async def start_trading(self, config: Config) -> None
    async def shutdown_graceful(self, timeout: int = 30) -> None
```

### G2. Config System
**Output:** `configs/` with JSON Schema validation
- `configs/trading.yaml`
- `configs/risk_limits.yaml`
- `schemas/config.schema.json`

### G3. CLI Tool
**Output:** `tools/auroractl.py`
```bash
auroractl validate-config configs/trading.yaml
auroractl start --mode=paper
auroractl health-check
```

---

## PHASE H: Resilience Testing

### H1. Performance Benchmarks
**Target Metrics:**
- Pretrade: p95 < 25ms, p99 < 50ms
- Execution: p95 < 50ms, p99 < 100ms  
- Observability: < 1ms overhead

### H2. Chaos Engineering
**Tests:**
- Network: 10% packet loss, 100ms latency spikes
- Clock:   500ms drift simulation
- Resources: CPU throttle to 50%

### H3. Fail-Closed Verification
**Scenarios:**
- Risk gate timeout     reject trade
- Idempotency violation     halt and alert
- WHY chain broken     pause and diagnose

---

## PHASE I: Production Readiness

### I1. Full E2E Suite
**Coverage:** All trading scenarios, edge cases

### I2. Production Readiness Assessment
**Output:** `PRODUCTION_READINESS_PLAN.md`
**Final Gate Runner:** All checks aggregated

### I3. Release Artifacts
**Outputs:**
- `release/aurora-vfound-v1.0.0.tar.gz`
- `release/SBOM.json`
- `release/requirements.lock`

### I4. Executive Summary
**Output:** `EXECUTIVE_SUMMARY.md`

### I5. GO/NO-GO Decision
**Criteria:** All gates PASS, SLOs defined and achievable
```

---

##                Gate/Freeze

### `templates/GATE_REPORT_TEMPLATE.md`

```markdown
# PH{N} GATE REPORT
**Phase:** {phase_name}  
**Date:** {UTC ISO8601}  
**Commit:** {sha}  
**Build:** {id}  

## Test Results
- **Passed:** {N}/{M}
- **Coverage:** {%} (critical_paths: {list})
- **Failed:** {list or "none"}

## Performance
- **pretrade_p95_ms:** {value}
- **exec_p95_ms:** {value}
- **obs_overhead_ms:** {value}

## Reliability
- **timeout_rate:** {%}
- **idempotency_verified:** {true/false}
- **retry_success_rate:** {%}

## Risk Controls
- **cvar_gate:** {pass/fail}
- **kelly_caps:** {pass/fail}
- **max_drawdown_check:** {pass/fail}

## WHY Traceability
- **why_ratio:** {value}
- **missing_why_count:** {N}

## Security
- **ed25519_verification:** {pass/fail}
- **rbac_smoke:** {pass/fail}
- **secrets_policy:** {compliant/violation}

## Observability
- **logs_valid:** {true/false}
- **health_endpoint:** {up/down}
- **metrics_exported:** {true/false}

## Verdict
**PASS** / **FAIL**  
**Reasons:** {if fail, list blockers}

## Artifacts
- {path_to_test_results}
- {path_to_coverage_report}
- {path_to_perf_traces}

## Next Steps
{if PASS: proceed to next phase}  
{if FAIL: create PH{N}_REWORK.md}
```

### `templates/FREEZE_NOTE_TEMPLATE.md`

```markdown
# PH{N} FREEZE NOTE
**Phase:** {phase_name}  
**Frozen At:** {UTC ISO8601}  
**Freeze ID:** {UUID}  

## Frozen State
- **Git Commit:** {sha}
- **Schema Versions:**
  - fsm_protocol: {version}
  - domain_schemas: {versions}
- **Config Hash:** {sha256}

## Log Checksums
- **LLM_LOG.jsonl:** {lines: N, sha256: hash, last_entry: timestamp}
- **audit.log:** {lines: N, sha256: hash}

## Dependency Snapshot
```
# requirements.freeze.txt
{package}=={version} # sha256:{hash}
```

## Database State
- **Migration Version:** {N}
- **State Backup:** {path_to_backup}

## Metrics Snapshot
- **Total Transactions:** {N}
- **Error Rate:** {%}
- **Uptime:** {duration}

## Certification
This freeze represents a stable, tested state.
Rollback point established.

**Signed:** {automation_signature}
```

---

##                                   

### `schemas/gaps_schema.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "gaps_analysis_v1",
  "type": "object",
  "properties": {
    "timestamp": {"type": "string", "format": "date-time"},
    "missing_from_vfound": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["component", "source", "priority"],
        "properties": {
          "component": {"type": "string"},
          "source": {"type": "string"},
          "priority": {"enum": ["P0", "P1", "P2", "P3"]},
          "complexity": {"enum": ["low", "medium", "high"]},
          "dependencies": {"type": "array", "items": {"type": "string"}}
        }
      }
    },
    "coverage_analysis": {
      "type": "object",
      "properties": {
        "fsm_compliance": {"type": "number", "minimum": 0, "maximum": 100},
        "aurora_features_ported": {"type": "number", "minimum": 0, "maximum": 100},
        "test_coverage": {"type": "number", "minimum": 0, "maximum": 100}
      }
    }
  }
}
```

### `ops/LLM_LOG.jsonl` (                             )

```jsonl
{"step_id":"A1","title":"Doctrine Analysis","reason":"Map principles to code","input_refs":["docs/"],"outputs":["reports/doctrine_matrix.json"],"checks":["all_docs_parsed"],"next":"A2","timestamp":"2024-01-15T10:00:00Z"}
{"step_id":"A2","title":"Code Inventory","reason":"Catalog existing components","input_refs":["vfoundation/","apps/"],"outputs":["reports/code_inventory.json"],"checks":["modules_counted","deps_listed"],"next":"A3","timestamp":"2024-01-15T12:00:00Z"}
{"step_id":"D2","title":"Skeleton Implementation","reason":"Prove E2E flow","input_refs":["apps/reference/"],"outputs":["apps/reference/skeleton/"],"checks":["compilation_ok","imports_resolved"],"next":"D3","timestamp":"2024-01-18T14:30:00Z"}
```

---

## Gap Report

### `reports/gaps_schema.json`

```json
{
  "timestamp": "2024-01-15T10:00:00Z",
  "missing_from_vfound": [
    {
      "component": "regime_detector",
      "source": "aurora/regime/detectors.py",
      "priority": "P1",
      "complexity": "medium",
      "dependencies": ["market_data", "feature_engineering"]
    },
    {
      "component": "portfolio_risk_aggregator",
      "source": "aurora/risk/portfolio.py",
      "priority": "P1",
      "complexity": "high",
      "dependencies": ["position_tracking", "risk_management"]
    },
    {
      "component": "tca_engine",
      "source": "aurora/execution/tca.py",
      "priority": "P2",
      "complexity": "medium",
      "dependencies": ["execution_adapter", "market_data"]
    },
    {
      "component": "drift_monitor",
      "source": "aurora/ml/drift.py",
      "priority": "P2",
      "complexity": "high",
      "dependencies": ["feature_engineering", "observability"]
    },
    {
      "component": "hawkes_process",
      "source": "aurora/models/hawkes.py",
      "priority": "P3",
      "complexity": "high",
      "dependencies": ["market_data"]
    }
  ],
  "coverage_analysis": {
    "fsm_compliance": 78,
    "aurora_features_ported": 45,
    "test_coverage": 78
  },
  "action_items": [
    "Port P1 components first (regime_detector, portfolio_risk)",
    "Establish adapter interfaces for aurora components",
    "Create migration test suite for each component"
  ]
}
```

---

## Final Gate Runner

### `tools/final_gate_runner.py`

```python
#!/usr/bin/env python3
"""
Final Gate Runner - Production Readiness Checker
Machine-executable validation for Aurora-vFoundation migration
"""

import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any
import subprocess
import hashlib

@dataclass
class GateCheck:
    name: str
    category: str
    command: str
    threshold: Any
    actual: Any = None
    passed: bool = False
    
class FinalGateRunner:
    """Aggregated production readiness checks"""
    
    def __init__(self):
        self.checks: List[GateCheck] = []
        self.results: Dict[str, Any] = {}
        
    def register_checks(self):
        """Define all gate checks"""
        
        # Testing Gates
        self.checks.extend([
            GateCheck(
                name="unit_tests",
                category="testing",
                command="pytest tests/unit/ --json-report",
                threshold={"pass_rate": 100, "coverage": 90}
            ),
            GateCheck(
                name="integration_tests", 
                category="testing",
                command="pytest tests/integration/ --json-report",
                threshold={"pass_rate": 100, "coverage": 85}
            ),
            GateCheck(
                name="e2e_tests",
                category="testing",
                command="pytest tests/e2e/ --json-report",
                threshold={"pass_rate": 100}
            ),
        ])
        
        # Code Quality Gates
        self.checks.extend([
            GateCheck(
                name="mypy_strict",
                category="quality",
                command="mypy --strict vfoundation/ apps/",
                threshold={"errors": 0}
            ),
            GateCheck(
                name="ruff_check",
                category="quality",
                command="ruff check vfoundation/ apps/",
                threshold={"violations": 0}
            ),
        ])
        
        # Performance Gates
        self.checks.extend([
            GateCheck(
                name="pretrade_latency",
                category="performance",
                command="python benchmarks/pretrade_bench.py",
                threshold={"p95_ms": 25, "p99_ms": 50}
            ),
            GateCheck(
                name="execution_latency",
                category="performance",
                command="python benchmarks/execution_bench.py",
                threshold={"p95_ms": 50, "p99_ms": 100}
            ),
        ])
        
        # Reliability Gates
        self.checks.extend([
            GateCheck(
                name="idempotency_test",
                category="reliability",
                command="pytest tests/properties/test_idempotency.py",
                threshold={"all_idempotent": True}
            ),
            GateCheck(
                name="timeout_handling",
                category="reliability",
                command="python tests/chaos/timeout_test.py",
                threshold={"timeout_rate": 1.0}  # max 1%
            ),
        ])
        
        # Risk Gates
        self.checks.extend([
            GateCheck(
                name="cvar_validation",
                category="risk",
                command="python tests/risk/test_cvar_gates.py",
                threshold={"gates_functional": True}
            ),
            GateCheck(
                name="kelly_caps",
                category="risk",
                command="python tests/risk/test_kelly_sizing.py",
                threshold={"caps_enforced": True}
            ),
        ])
        
        # Security Gates
        self.checks.extend([
            GateCheck(
                name="ed25519_signatures",
                category="security",
                command="python tests/security/test_signatures.py",
                threshold={"verify_ok": True}
            ),
            GateCheck(
                name="rbac_enforcement",
                category="security",
                command="python tests/security/test_rbac.py",
                threshold={"unauthorized_blocked": True}
            ),
            GateCheck(
                name="secrets_scan",
                category="security",
                command="gitleaks detect --no-git",
                threshold={"leaks": 0}
            ),
        ])
        
        # Observability Gates
        self.checks.extend([
            GateCheck(
                name="structured_logging",
                category="observability",
                command="python tests/obs/test_logging.py",
                threshold={"format_valid": True}
            ),
            GateCheck(
                name="why_chain",
                category="observability",
                command="python tests/obs/test_why_chain.py",
                threshold={"why_ratio": 0.98}
            ),
            GateCheck(
                name="health_endpoint",
                category="observability",
                command="curl -f http://localhost:8000/health",
                threshold={"status": "healthy"}
            ),
        ])
        
    def run_check(self, check: GateCheck) -> bool:
        """Execute a single gate check"""
        # TODO: Implement actual command execution
        # This is a skeleton - actual implementation needed
        print(f"Running {check.category}/{check.name}...")
        
        # Placeholder logic
        try:
            # result = subprocess.run(check.command, shell=True, capture_output=True)
            # Parse result and compare with threshold
            check.actual = check.threshold  # TODO: Get actual values
            check.passed = True  # TODO: Real comparison
            return check.passed
        except Exception as e:
            print(f"Check failed: {e}")
            check.passed = False
            return False
            
    def run_all(self) -> bool:
        """Execute all gate checks"""
        self.register_checks()
        
        all_passed = True
        results_by_category: Dict[str, List[GateCheck]] = {}
        
        for check in self.checks:
            passed = self.run_check(check)
            all_passed = all_passed and passed
            
            if check.category not in results_by_category:
                results_by_category[check.category] = []
            results_by_category[check.category].append(check)
            
        # Generate report
        self.generate_report(results_by_category, all_passed)
        
        return all_passed
        
    def generate_report(self, results: Dict[str, List[GateCheck]], all_passed: bool):
        """Generate final gate report"""
        
        report = {
            "timestamp": "2024-01-15T10:00:00Z",  # TODO: Real timestamp
            "verdict": "PASS" if all_passed else "FAIL",
            "categories": []
        }
        
        for category, checks in results.items():
            passed_count = sum(1 for c in checks if c.passed)
            report["categories"].append({
                "passed": passed_count,
                "total": len(checks),
                "checks": [
                    {
                        "name": c.name,
                        "passed": c.passed,
                        "threshold": c.threshold,
                        "actual": c.actual
                    }
                    for c in checks
                ]
            })
            
        # Write report
        report_path = Path("reports/FINAL_GATE_REPORT.json")
        report_path.parent.mkdir(exist_ok=True)
        
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
            
        # Also create markdown summary
        self.generate_markdown_summary(report)
        
    def generate_markdown_summary(self, report: dict):
        """Create human-readable summary"""
        
        md_lines = [
            "# FINAL GATE REPORT",
            f"**Verdict:** {report['verdict']}",
            f"**Timestamp:** {report['timestamp']}",
            "",
            "## Results by Category",
            ""
        ]
        
        for category, data in report["categories"].items():
            status = "   " if data["passed"] == data["total"] else "   "
            md_lines.append(f"### {status} {category.title()}: {data['passed']}/{data['total']}")
            
            for check in data["checks"]:
                check_status = "   " if check["passed"] else "   "
                md_lines.append(f"- {check_status} {check['name']}")
            md_lines.append("")
            
        if report["verdict"] == "FAIL":
            md_lines.extend([
                "## Required Actions",
                "1. Fix failing checks above",
                "2. Re-run gate validation",
                "3. Create rework plan for persistent failures",
            ])
        else:
            md_lines.extend([
                "## Production Ready    ",
                "All gates passed. System ready for production deployment.",
                "",
                "### Next Steps",
                "1. Tag release",
                "2. Generate SBOM",
                "3. Deploy to staging",
                "4. Execute production cutover plan",
            ])
            
        with open("reports/FINAL_GATE_REPORT.md", "w") as f:
            f.write("\n".join(md_lines))
            
    def verify_artifacts(self) -> bool:
        """Verify all required artifacts exist"""
        
        required_artifacts = [
            "docs/PLAN_AURORA_TO_VFOUNDATION.md",
            "docs/FSM_PROTOCOL.md", 
            "schemas/fsm_protocol.schema.json",
            "reports/gaps_schema.json",
            "ops/LLM_LOG.jsonl",
            "configs/trading.yaml",
        ]
        
        missing = []
        for artifact in required_artifacts:
            if not Path(artifact).exists():
                missing.append(artifact)
                
        if missing:
            print(f"Missing artifacts: {missing}")
            return False
            
        return True

def main():
    runner = FinalGateRunner()
    
    print("     Aurora-vFoundation Final Gate Runner")
    print("=" * 50)
    
    # First verify artifacts
    if not runner.verify_artifacts():
        print("    Missing required artifacts. Cannot proceed.")
        sys.exit(1)
        
    # Run all checks
    if runner.run_all():
        print("\n    ALL GATES PASSED - PRODUCTION READY")
        sys.exit(0)
    else:
        print("\n    SOME GATES FAILED - SEE REPORT")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## Machine Progress Tracker

### `ops/PROGRESS_TRACKER.md`

```markdown
# Aurora Migration Progress Tracker
**Format:** Machine-readable progress log  
**Updated:** Auto-generated

## Phase Status
| Phase | Status | Started | Completed | Gate | 
|-------|--------|---------|-----------|------|
| PH-AUDIT |     COMPLETE | 2024-01-15 | 2024-01-16 | PASS |
| PH-SSOT |      IN_PROGRESS | 2024-01-17 | - | - |
| PH-INFRA |        PENDING | - | - | - |
| PH-SKELETON |        PENDING | - | - | - |
| PH-LAYERS |        PENDING | - | - | - |
| PH-CONNECTORS |        PENDING | - | - | - |
| PH-ORCHESTRATION |        PENDING | - | - | - |
| PH-RESILIENCE |        PENDING | - | - | - |
| PH-PRODUCTION |        PENDING | - | - | - |

## Metrics Summary
- **Overall Progress:** 11% (1/9 phases)
- **Code Coverage:** 78%
- **Aurora Features Ported:** 45%
- **Tests Passing:** 31/32
- **Critical Issues:** 0
- **Blockers:** 0

## Recent Actions
- [2024-01-16 14:30] Completed gap analysis
- [2024-01-17 09:00] Started schema definitions
- [2024-01-17 11:45] FSM protocol draft created

## Next Milestone
**Target:** Complete PH-SSOT by 2024-01-19  
**Blockers:** None  
**Dependencies:** Review of FSM protocol spec
```

---

## Artifact Index

### `reports/index.json`

```json
{
  "version": "1.0.0",
  "generated": "2024-01-15T10:00:00Z",
  "artifacts": [
    {
      "path": "docs/PLAN_AURORA_TO_VFOUNDATION.md",
      "type": "plan",
      "sha256": "abc123...",
      "size": 15234,
      "modified": "2024-01-15T10:00:00Z"
    },
    {
      "path": "schemas/fsm_protocol.schema.json",
      "type": "schema",
      "sha256": "def456...",
      "size": 3456,
      "modified": "2024-01-15T11:00:00Z"
    },
    {
      "path": "reports/gaps_schema.json",
      "type": "report",
      "sha256": "ghi789...",
      "size": 2345,
      "modified": "2024-01-15T12:00:00Z"
    },
    {
      "path": "ops/LLM_LOG.jsonl",
      "type": "log",
      "sha256": "jkl012...",
      "size": 4567,
      "lines": 42,
      "modified": "2024-01-15T14:00:00Z"
    }
  ],
  "checksums": {
    "total_files": 4,
    "total_size": 25602,
    "manifest_sha256": "mno345..."
  }
}
```

---

                                                           :
1. **                                      ** -                              JSON/YAML                  
2. **                              ** -         -       LLM                                          -                   
3. **                        ** -                                           LLM_LOG.jsonl
4. **            ** -                                                     
5. **              ** -                                                                     


##                                                       :

### 1. **                                                                             Binance API**    
-                                                   **                                         **      WebSocket      REST API
-                                                 **                            **                                                       
-                                        **rate limits**                                    API

### 2. **                                         execution_engine**      
-    `core/aurora/`                                  `execution/`                                         
-                                                                            ,                               
-                                         "read-only"                                       

### 3. **                                  WHY-chain tracing**    
-                                             ,                                                                          
-                         debugging                                FSM
-                                                                                            WHY                   

### 4. **                                                                                    **    
-                                                                               
-                                                "dry run"                                               
-                                                                                                  

### 5. **                        disaster recovery**    
-                                                                                             
-            checkpoint/restore                   FSM
-                                                    '                                           

### 6. **                                                           **    
-            Prometheus/Grafana                     
-                  performance                (latency, throughput)
-                               health check endpoint

### 7. **                      backtesting framework**    
-                                                                                                 
-                                       replay                                
-                                                    live vs backtest                       

##                                                                              :

### **         0: API Validation & Connection Health** (          )
*                    : 2-3       *

- **T01**:                  `ConnectionHealthCheck`                                                         '              
- **T02**:                                                 reconnect    exponential backoff
- **T03**:              rate limit monitoring      throttling

### **         1: Foundation Freeze** (                )
*                                               :*

- **T05**:                        WHY-chain collector                                         
- **T06**:                  health check endpoints (`/health`, `/ready`)
- **T07**:              Prometheus                                  

### **         2: Total Awareness** (                )
*            :*

- **T05**:                    `execution_engine`    core/aurora
- **T06**:                        dry-run                                                            
- **T07**:                  backtesting framework    replay                     

### **         3.5: Resilience & Recovery** (          )
*                    : 1               *

- **T01**:                        checkpoint/restore        FSM           
- **T02**:              circuit breaker                                                              
- **T03**:                  disaster recovery playbook                                

### **         4: Production Deployment** (          )
*                    : 1               *

- **T01**: Docker                                   multi-stage build
- **T02**: Kubernetes manifests        orchestration
- **T03**: CI/CD pipeline                                             
- **T04**: Blue-green deployment                   

##                                           ,                                                    :

1. **                                  Binance API             ** -                                                           
2. **                                     **: observation-only      full trading capability?
3. **                          deployment**: local, cloud,      hybrid?

---
---
# PHASE J: Data Ingestion & Metrics Foundation
**Intent:** To establish a robust, observable, and testable pipeline for ingesting market data from Binance and computing essential metrics, addressing the gaps identified previously. This phase runs in parallel with core migration and provides the foundational data layer for all trading domains.

## J1. Binance Metrics Catalog
**Objective:** Create a definitive, machine-readable catalog of all required metrics from Binance APIs.
**Artifacts:** `docs/METRICS_CATALOG.md`, `schemas/metrics_catalog.json`, `samples/binance_api/`

### J1.1. Market Data: Provided (Spot & USD   -M Futures)
| metric_key | market | source | endpoint_or_stream | fields | units | intervals | history_window | rate_limits | auth_required |
|---|---|---|---|---|---|---|---|---|---|
| klines | spot, um | REST | `/api/v3/klines`, `/fapi/v1/klines` | `open,high,low,close,volume` | quote | 1m, 5m, 1h, 1d | 1000 candles | by IP/UID | No |
| depth | spot, um | WS | `<symbol>@depth<levels>@<speed>` | `bids:[price,qty], asks:[price,qty]` | base, quote | 100ms, 500ms | N/A | by connection | No |
| aggTrade | spot, um | WS | `<symbol>@aggTrade` | `p,q,T,m` | quote, base | real-time | N/A | by connection | No |
| bookTicker | spot, um | WS | `<symbol>@bookTicker` | `b,B,a,A` | quote | real-time | N/A | by connection | No |
| markPrice | um | WS | `<symbol>@markPrice@1s` | `p,r` | quote, % | 1s, 3s | N/A | by connection | No |
| fundingRate | um | REST | `/fapi/v1/fundingRate` | `fundingTime, fundingRate` | % | 4h, 8h | 1000 records | by IP | No |
| openInterest | um | REST | `/fapi/v1/openInterest` | `openInterest` | quote | N/A | 1 record | by IP | No |
| taker_vol | um | REST | `/futures/data/takerlongshortRatio` | `buySellRatio,buyVol,sellVol` | quote | 5m, 15m, ... | 500 records | by IP | No |
| liquidation | um | WS | `!forceOrder@arr` | `s,S,o,p,q,T` | quote, base | real-time | N/A | by connection | No |

### J1.2. Market Data: Computed
| metric_key | market | provided_keys | formula_or_ref |
|---|---|---|---|
| ema | spot, um | `klines.close` | `EMA_t = (Close_t * (2/(N+1))) + EMA_{t-1} * (1 - (2/(N+1)))` |
| rsi | spot, um | `klines.close` | `100 - (100 / (1 + (avg_gain / avg_loss)))` |
| obv | spot, um | `klines.close`, `klines.volume` | `OBV_t = OBV_{t-1} + (sign(Close_t - Close_{t-1}) * Volume_t)` |
| vwap | spot, um | `klines.high`, `klines.low`, `klines.close`, `klines.volume` | `sum(TypicalPrice * Volume) / sum(Volume)` over a period |
| book_imbalance | spot, um | `depth.bids`, `depth.asks` | `(sum(bid_qty) - sum(ask_qty)) / (sum(bid_qty) + sum(ask_qty))` |

**DoD (J1):**
- [ ] `METRICS_CATALOG.md` and `metrics_catalog.json` are created and populated for at least 5 `Provided` and 3 `Computed` metrics.
- [ ] `samples/binance_api/` contains at least one valid JSON response for each covered endpoint.
- [ ] All schemas are validated.

## J2. Data Ingestion & Compute Pipeline
**Objective:** Implement the system to fetch, process, and store data defined in the catalog.

### J2.1. Sub-system Design
1.  **Connectors:** Python classes using `aiohttp` for REST and `websockets` for WS. Implements exponential backoff and jitter on failures.
2.  **Rate-Limit Guard:** A central async manager using a token bucket algorithm to govern all outgoing requests, respecting weights from `/api/v3/exchangeInfo`.
3.  **Schema Layer:** Pydantic models for every API response. Timestamps are converted to UTC `datetime` objects.
4.  **Persistence:** Raw data (bronze) stored in a time-series DB (e.g., InfluxDB) or partitioned Parquet files on disk (e.g., `data/bronze/spot/klines/BTCUSDT/2024/10/16.parquet`).
5.  **Compute:** A dedicated FSM Domain `DATA_COMPUTE`. Receives `EVT:RAW_DATA_INGESTED`, calculates indicators, and emits `EVT:METRIC_COMPUTED`.
6.  **Caching:** Redis-based caching for frequently requested semi-static data like `/fapi/v1/exchangeInfo`.

**DoD (J2):**
- [ ] `Connector` for Spot/UM klines and depth is implemented.
- [ ] `Rate-Limit Guard` is functional and tested.
- [ ] Pydantic schemas for klines and depth are created.
- [ ] Data is successfully persisted to the chosen storage.

## J3. Testing Strategy
**Objective:** Ensure the data pipeline is reliable and correct.

1.  **Unit Tests:** Test `Computed` metric formulas with known inputs/outputs.
2.  **Property-Based Tests:** For indicators, verify invariants (e.g., RSI is always between 0 and 100).
3.  **Integration Tests:** Use recorded API responses (`vcrpy` or similar) to test the full flow from connector to persistence without hitting the live API.
4.  **E2E Smoke Tests:** A test that runs against Binance testnet, fetches live data for 1 minute, and verifies it's stored correctly.
5.  **Load/Chaos Tests:** Simulate high volume WebSocket messages and random disconnects to test connector resilience.

**DoD (J3):**
- [ ] Unit test coverage for compute functions     95%.
- [ ] Integration test for klines ingestion flow passes.
- [ ] E2E smoke test against testnet passes.

## J4. Observability & Operations
**Objective:** Make the pipeline transparent and manageable.

1.  **SLOs:**
    *   `data_ingestion_latency_p95`: < 500ms (from exchange timestamp to DB write).
    *   `data_completeness_1h`: > 99.9% (for 1m klines).
    *   `api_error_rate`: < 0.1%.
2.  **Alerts (via Alertmanager/Pushover):**
    *   `HighApiErrorRate`: API error rate > 1% for 5 minutes.
    *   `RateLimitNear`: Using > 90% of request quota.
    *   `DataGapDetected`: Missing klines for a symbol for > 3 intervals.
    *   `PipelineBacklog`: Ingestion queue size > 1000.
3.  **Endpoints:**
    *   `/health`: Returns `{"status": "ok"}`.
    *   `/metrics`: Exposes Prometheus metrics (`ingestion_latency`, `ws_messages_total`, etc.).

**DoD (J4):**
- [ ] Prometheus metrics for latency and message count are implemented.
- [ ] `/health` endpoint is active.
- [ ] At least one alert (`HighApiErrorRate`) is configured and tested.

## J5. Performance & Security
**Objective:** Ensure the pipeline is efficient and secure.

1.  **Performance Budgets:**
    *   p95 REST API call (e.g., `/fapi/v1/klines`):     200ms.
    *   p99 WS message processing latency:     10ms.
    *   CPU usage of ingestion service: < 50% of 1 core.
2.  **Security:**
    *   Binance API keys are loaded exclusively from environment variables or a secret manager (e.g., HashiCorp Vault).
    *   Code is scanned to ensure no keys are hardcoded.
    *   Sensitive data in logs is masked.

**DoD (J5):**
- [ ] A benchmark test for klines fetching is created.
- [ ] Secret loading mechanism is implemented and verified.

## J6. Milestones & Gates for Phase J
| Gate | Title | DoD & Acceptance Criteria | Verdict |
|---|---|---|---|
| **M1** | **Connector & Schema Foundation** | DoD for J1 and J2 are met. Basic klines/depth ingestion works. | PASS/FAIL |
| **M2** | **Full Provided Metrics & Testing** | Full `Provided` metrics catalog implemented. Integration and E2E tests (J3) are passing. | PASS/FAIL |
| **M3** | **Compute Layer & Observability** | `Computed` metrics are implemented. Observability (J4) is functional with live metrics. | PASS/FAIL |
| **M4** | **Resilience & Finalization** | Load/Chaos tests pass. Security checks (J5) pass. All documentation is complete. | PASS/FAIL |

## J7. Risk Analysis & Mitigation
| Risk | Mitigation Strategy |
|---|---|
| Binance API changes (schema drift) | Implement contract testing against golden samples. Alert on schema validation failures. |
| Rate limit exhaustion | Implement a centralized `Rate-Limit Guard` with priority queues. Use WebSocket streams over REST where possible. |
| WebSocket message drop/reorder | Use `gap` detection on sequence numbers (if available) or timestamps. Implement a reconciliation mechanism via REST. |
| Timezone / timestamp corruption | Standardize on UTC for all internal processing. Validate exchange timestamps (`E`) against event timestamps (`T`). |
| Testnet/Mainnet divergence | Maintain separate configuration files. Run a subset of E2E tests on both environments continuously. |

## J8. Standard Operating Procedures (SOP)
1.  **Starting/Stopping Service:** `auroractl data-ingest start/stop`.
2.  **API Key Rotation:** Update environment variables and perform a rolling restart of the connector service.
3.  **Data Backfill:** A CLI command `auroractl data-backfill --symbol <S> --start <T1> --end <T2>` to fetch historical data via REST.
4.  **DR Scenario (Data Loss):** Trigger the backfill procedure to restore missing data from the exchange.

---
# PHASE K: LLM Agent Task Specification
**Intent:** To define a standardized, machine-readable format for all tasks assigned to LLM agents, ensuring clarity, testability, and autonomous execution.

## K1. YAML TaskSpec Template
**Objective:** Create a template that encapsulates all necessary information for an LLM agent to perform a development task.
**Artifact:** `templates/TASK_SPEC_TEMPLATE.yaml`

```yaml
# templates/TASK_SPEC_TEMPLATE.yaml
spec_version: 1.0
task_id: # Unique ID, e.g., "MD-001"
title: # Human-readable title, e.g., "Implement EMA-12/26 Computed Metric"
intent: # High-level goal of the task. WHY is it needed?
context: # Brief description of where this task fits in the larger system.
inputs:
  - type: # e.g., 'file', 'schema', 'doc'
    path: # Path to the input artifact
    description: # What is this input?
outputs:
  - type: # e.g., 'file', 'test_report', 'artifact'
    path: # Path to the expected output artifact
    description: # What should this output contain?
steps:
  - step_id: 1
    description: # Atomic, verifiable action. E.g., "Read the klines schema from schemas/..."
    command: # Optional: A shell command to execute
    checks: # A list of post-conditions to verify
      - "File X is created"
      - "Function Y returns expected value for input Z"
acceptance_criteria: # Definition of Done (DoD) for the entire task
  - "All steps are completed successfully."
  - "Unit tests for the new module pass with >95% coverage."
  - "The output artifacts are created and match the specified format."
checks_and_gates: # Reference to a higher-level gate, e.g., "M1"	
telemetry:
  metrics_to_emit: # Metrics the agent should report upon completion
    - name: "task_completion_time_ms"
      value: "{execution_time}"
    - name: "code_lines_changed"
      value: "{loc_delta}"
budgets:
  time_ms: 300000 # Max execution time for the agent
  cpu_cores: 0.5 # Max CPU allocation
failure_modes_and_recovery:
  - mode: "Test failure"
    recovery: "Analyze pytest report, identify failing test, and attempt to fix the code. Retry up to 3 times."
  - mode: "Schema validation error"
    recovery: "Review the generated code against the Pydantic model and correct the fields. Retry."
anti_patterns: # Things the agent should NOT do
  - "Do not hardcode API keys or any secrets."
  - "Do not introduce new dependencies without updating 'requirements.txt'."
  - "Do not write code without corresponding unit tests."
```

## K2. Example Task Definition
**Objective:** Provide a concrete example of a task specified using the template.
**Artifact:** `tasks/MD-001_Implement_EMA_Metric.yaml`

```yaml
# tasks/MD-001_Implement_EMA_Metric.yaml
spec_version: 1.0
task_id: "MD-001"
title: "Implement EMA-12/26 Computed Metric"
intent: "To provide Exponential Moving Average indicators, which are fundamental for many trading strategies."
context: "This task is part of the 'Compute' layer in the Data Ingestion pipeline. It will create a new function within the 'DATA_COMPUTE' domain that calculates EMA from raw kline data."
inputs:
  - type: 'file'
    path: 'vfoundation/domains/data_compute/schemas.py'
    description: 'Pydantic schema for incoming Kline data.'
  - type: 'doc'
    path: 'docs/METRICS_CATALOG.md'
    description: 'Reference for the EMA formula.'
outputs:
  - type: 'file'
    path: 'vfoundation/domains/data_compute/indicators/moving_averages.py'
    description: 'New Python module containing the EMA calculation logic.'
  - type: 'file'
    path: 'tests/domains/data_compute/indicators/test_moving_averages.py'
    description: 'Unit tests for the new EMA implementation.'
steps:
  - step_id: 1
    description: "Create the output file 'vfoundation/domains/data_compute/indicators/moving_averages.py'."
    checks: ["File exists."]
  - step_id: 2
    description: "Implement a Python function 'calculate_ema(prices: list[float], period: int) -> list[float]' inside the new file."
    checks: ["Function exists and has the correct signature."]
  - step_id: 3
    description: "Create the test file 'tests/domains/data_compute/indicators/test_moving_averages.py'."
    checks: ["Test file exists."]
  - step_id: 4
    description: "Write at least two unit tests for 'calculate_ema': one with a known public reference value, and one for an edge case (e.g., empty price list)."
    checks: ["'pytest' command passes for this test file."]
acceptance_criteria:
  - "The 'moving_averages.py' module is created and contains a correct EMA implementation."
  - "The 'test_moving_averages.py' file is created and its tests pass successfully."
  - "Test coverage for the new module is at least 95%."
checks_and_gates: "M3"	au
telemetry:
  metrics_to_emit:
    - name: "task_completion_time_ms"
      value: "{execution_time}"
    - name: "test_coverage_pct"
      value: "{coverage}"
budgets:
  time_ms: 600000
  cpu_cores: 0.5
failure_modes_and_recovery:
  - mode: "Test failure"
    recovery: "Analyze pytest report, compare logic against the formula in METRICS_CATALOG.md, and fix the implementation. Retry up to 2 times."
anti_patterns:
  - "Do not use third-party libraries for the calculation (e.g., pandas, numpy) unless specified in project dependencies."
  - "Do not modify files outside of the specified output paths."
```
---
# PHASE L: Architecture Validation & Implementation Specification
**Intent:** To synchronize the plan with the actual project state, formalize the specifications for all FSM domains based on core architectural documents, and detail the implementation of cross-cutting concerns like CI/CD, DR, and security. This phase ensures that all future development by LLM agents is strictly aligned with the `Constitution` and has non-ambiguous, measurable goals.

## L1. FSM Domain Specifications
**Objective:** Define the precise contract (states, transitions, events) for each FSM domain identified in `apps/reference/domains` and `GEMINI.md`, based on `CENTRAL_FSM_SPEC.md`.
**Artifact:** `docs/FSM_DOMAIN_SPECIFICATIONS.md`

### L1.1. `market_data` FSM
*   **Purpose:** Ingests raw data from exchange connectors.
*   **States:** `DISCONNECTED`, `CONNECTING`, `CONNECTED`, `DEGRADED`
*   **Events (In):** `CMD:CONNECT`, `CMD:DISCONNECT`
*   **Events (Out):** `EVT:MARKET_TICK_RECEIVED`, `EVT:CONNECTION_STATUS_CHANGED`
*   **Final Goal:** Provide a stable, real-time stream of market data with < 100ms latency from exchange to FSM bus. `completeness > 99.9%` for 1s intervals.

### L1.2. `feature_engineering` FSM
*   **Purpose:** Calculates technical indicators from raw market data.
*   **States:** `IDLE`, `CALCULATING`
*   **Events (In):** `EVT:MARKET_TICK_RECEIVED`
*   **Events (Out):** `EVT:FEATURES_CALCULATED`
*   **Final Goal:** Calculate a standard set of 5 indicators (OBI, TFI, Absorption, EMA, RSI) for each tick within the performance budget (p99 < 20ms). Output must be deterministic.

### L1.3. `risk_management` FSM
*   **Purpose:** Assesses risk for potential trades.
*   **States:** `IDLE`, `ASSESSING`
*   **Events (In):** `EVT:FEATURES_CALCULATED`
*   **Events (Out):** `EVT:RISK_ASSESSMENT_COMPLETED`
*   **Final Goal:** Provide a risk assessment (Kelly fraction, CVaR, limits) for each feature set. The assessment logic must pass all property-based tests defined in `tests/properties/test_risk_invariants.py`.

### L1.4. `position_tracking` FSM
*   **Purpose:** Maintains the current state of the portfolio.
*   **States:** `EMPTY`, `POSITION_OPEN`
*   **Events (In):** `EVT:TRADE_EXECUTED` (from `account_observer`)
*   **Events (Out):** `EVT:PORTFOLIO_STATE_UPDATED`
*   **Final Goal:** Maintain an accurate, real-time representation of the portfolio state. State drift between this FSM and the exchange account must be `< 0.01%` over a 24h period, verified by a reconciliation job.

### L1.5. `decision_making` FSM
*   **Purpose:** Aggregates all data to propose trades.
*   **States:** `AWAITING_DATA`, `AGGREGATING`, `DECIDED`
*   **Events (In):** `EVT:FEATURES_CALCULATED`, `EVT:RISK_ASSESSMENT_COMPLETED`, `EVT:PORTFOLIO_STATE_UPDATED`
*   **Events (Out):** `EVT:TRADE_INTENT_PROPOSED`
*   **Final Goal:** Produce valid, schema-compliant trade intents without proposing trades that violate risk parameters. `why_chain` coverage for all decisions must be 100%.

### L1.6. `account_observer` FSM
*   **Purpose:** Observes the real account on the exchange for fills and updates.
*   **States:** `POLLING`, `IDLE`
*   **Events (In):** `CMD:START_POLLING`
*   **Events (Out):** `EVT:TRADE_EXECUTED`
*   **Final Goal:** Detect and emit all trade executions from the exchange within `5 seconds` of their occurrence.

## L2. Integration & End-to-End Testing Strategy
**Objective:** Define a clear strategy for testing the interaction between FSM domains.
**Artifact:** `tests/integration/README.md`, `tests/e2e/` scenarios.

*   **Strategy:** Integration tests will use a live `FSMCore` but with mocked external interfaces (Binance API). E2E tests will run against the Binance Testnet.
*   **Scenario 1 (Happy Path):**
    1.  Inject `EVT:MARKET_TICK_RECEIVED`.
    2.  Assert `EVT:FEATURES_CALCULATED` is emitted.
    3.  Assert `EVT:RISK_ASSESSMENT_COMPLETED` is emitted with `is_trading_allowed: true`.
    4.  Assert `EVT:PORTFOLIO_STATE_UPDATED` is emitted.
    5.  Assert `EVT:TRADE_INTENT_PROPOSED` is emitted with a valid trade proposal.
*   **Scenario 2 (Risk Rejection):**
    1.  Inject `EVT:MARKET_TICK_RECEIVED` that leads to high-risk features.
    2.  Assert `EVT:RISK_ASSESSMENT_COMPLETED` is emitted with `is_trading_allowed: false`.
    3.  Assert that **NO** `EVT:TRADE_INTENT_PROPOSED` is emitted within a 1-second window.
*   **Freeze Criteria:** A freeze point is reached when all defined integration scenarios pass, and the E2E test successfully completes a full trade cycle (propose -> execute -> observe fill) on the testnet.

## L3. CI/CD & Deployment Pipeline
**Objective:** Automate quality checks, artifact generation, and deployment.
**Artifact:** `.github/workflows/ci.yml`

1.  **On Pull Request:**
    *   `vfound dict lint`: Check domain dictionaries for errors.
    *   `vfound schema gen`: Generate schemas from dictionaries.
    *   `ruff check .`: Run linter.
    *   `mypy --strict .`: Run static type checker.
    *   `pytest -q --cov --cov-min=90`: Run all tests and enforce 90% coverage.
2.  **On Merge to `main`:**
    *   All PR checks pass.
    *   Build Docker container with a version tag.
    *   Push container to a registry (e.g., Docker Hub, GHCR).
    *   (Manual Trigger) Deploy to a staging/production environment.
*   **Final Goal:** No code can be merged without passing all automated quality gates. The deployment process is fully automated after a merge.

## L4. Disaster Recovery (DR) & Replay Protocol
**Objective:** Detail the exact mechanism for state reconstruction, as required by `Constitution_FSM.md`.
**Artifact:** `docs/DR_PLAYBOOK.md`

*   **Mechanism:**
    1.  **State Snapshots:** Every 5 minutes, each critical FSM (`position_tracking`) serializes its full state to a versioned file (`<domain>_<timestamp>.json`) and uploads it to a WORM-compliant store (e.g., S3 with Object Lock).
    2.  **Write-Ahead Log (WAL):** All incoming events (`Message` objects) are logged to a per-day file (`wal_<date>.jsonl`) in the same WORM store before processing.
    3.  **Recovery Process:**
        a. On startup, the system fetches the latest snapshot for the `position_tracking` FSM.
        b. It loads the state from the snapshot.
        c. It fetches the WAL file(s) from the snapshot's timestamp forward.
        d. It replays all `EVT:TRADE_EXECUTED` messages from the WAL into the `position_tracking` FSM to reconstruct the final state.
*   **Freeze Criteria:** The DR mechanism is considered complete when a chaos test (deleting the local state and restarting the service) results in a successful state reconstruction with `< 0.01%` state drift compared to a control instance.

## L5. Security Implementation Protocol
**Objective:** Define concrete steps for implementing the security requirements.
**Artifact:** `docs/SECURITY_IMPLEMENTATION.md`

1.  **Ed25519 Signatures:**
    *   A `vfoundation.security.Signer` class will be created, initialized with a private key from the environment (`TRADING_SIGNING_KEY`).
    *   The `OrchestratorFSM` will be responsible for signing all outgoing `CMD:OPEN` and `CMD:CLOSE` messages.
    *   The `execution_position` domain will have a corresponding `Verifier` that rejects any unsigned or invalidly signed commands.
2.  **RBAC (Role-Based Access Control):**
    *   The FastAPI server providing debug endpoints (`/debug/{rid}`, `/replay/{rid}`) will implement a dependency that checks for a bearer token in the `Authorization` header.
    *   A config file (`configs/rbac.yaml`) will map tokens to roles (e.g., `admin`, `viewer`).
    *   Endpoints that modify state (e.g., `/replay`) will require the `admin` role.
*   **Final Goal:** All critical commands are cryptographically signed. All sensitive endpoints are protected by role-based access control.

## L6. Contract Versioning & Governance Protocol
**Objective:** Enforce the `additive-only` principle to prevent breaking changes.

*   **Protocol:**
    1.  Any change to a `schemas/*.json` file that is not purely additive (e.g., removing a field, changing a type) is **forbidden**.
    2.  To introduce a breaking change, a **new version** of the schema must be created (e.g., `trade_intent_v2.json`).
    3.  The component emitting the new version must update its `dto_version` field.
    4.  The consuming component must be updated to handle both `v1` and `v2` for a deprecation window of at least two release cycles.
*   **Freeze Criteria:** The CI/CD pipeline will include a `semantic-diff` check that fails the build if a non-additive change is detected in any schema file, thus programmatically enforcing the protocol.
