from __future__ import annotations
import importlib.util

import json
import sys
from pathlib import Path

import libcst as cst

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_move_map_contains_addendum_3_rows():
    from dm_split_lib import load_move_map

    rows = {(row.source_path, row.target_path) for row in load_move_map()}
    assert (
        "apps/reference/domains/decision_making/position_queries.py",
        "apps/reference/domains/decision_making/primitives/position_queries.py",
    ) in rows
    assert (
        "apps/reference/domains/decision_making/operational_mode.py",
        "apps/reference/domains/decision_making/primitives/operational_mode.py",
    ) in rows


def test_build_rename_plan_positive_and_noop():
    from dm_split_lib import MoveRow, build_rename_plan

    plan = build_rename_plan([
        MoveRow("apps/reference/domains/decision_making/a.py",
                "apps/reference/domains/decision_making/core/a.py"),
        MoveRow("apps/reference/domains/decision_making/__init__.py",
                "apps/reference/domains/decision_making/__init__.py"),
    ])
    assert plan["apps.reference.domains.decision_making.a"] == "apps.reference.domains.decision_making.core.a"
    assert "apps.reference.domains.decision_making.__init__" not in plan


def test_load_move_map_supports_package3_columns(tmp_path):
    from dm_split_lib import load_move_map

    move_map = tmp_path / "dm_move_map_p3.csv"
    move_map.write_text(
        "source,destination,reason\n"
        "apps/reference/domains/decision_making/strategies/bridge.py,"
        "apps/reference/domains/strategies/runtimes/bridge.py,"
        "strategy_runtime_cross_domain_split\n",
        encoding="utf-8",
    )

    rows = load_move_map(move_map)

    assert rows[0].source_path == "apps/reference/domains/decision_making/strategies/bridge.py"
    assert rows[0].target_path == "apps/reference/domains/strategies/runtimes/bridge.py"


def test_move_files_plans_init_paths_from_target_tree():
    from dm_split_lib import MoveRow

    mover = _load_module("move_files", "05_move_files.py")
    planned = mover.planned_init_paths([
        MoveRow(
            "apps/reference/domains/decision_making/strategies/__init__.py",
            "apps/reference/domains/strategies/runtimes/__init__.py",
        ),
        MoveRow(
            "apps/reference/domains/decision_making/strategies/aurora/__init__.py",
            "apps/reference/domains/strategies/runtimes/aurora/__init__.py",
        ),
        MoveRow(
            "apps/reference/domains/decision_making/primitives/entry_plan.py",
            "apps/reference/shared/decision_primitives/entry_plan.py",
        ),
    ])

    assert "apps/reference/shared/decision_primitives/__init__.py" in planned
    assert "apps/reference/domains/strategies/runtimes/__init__.py" not in planned
    assert "apps/reference/domains/strategies/runtimes/aurora/__init__.py" not in planned


def test_import_rewriter_rewrites_absolute_and_relative_imports():
    rewriter = _load_module("rewrite_imports", "04_rewrite_imports.py")
    old_module = "apps.reference.domains.decision_making.primitives.position_queries"
    new_module = "apps.reference.domains.decision_making.primitives.position_queries"
    plan = {
        old_module: new_module,
    }
    source = "\n".join([
        "from .position_queries import PositionQueries",
        f"from {old_module} import PositionQueries as PQ",
        f'MODULE = "{old_module}"',
        "",
    ])
    module = cst.parse_module(source)
    updated = module.visit(
        rewriter.ImportRewriter(
            plan,
            "apps.reference.domains.decision_making.core.facade",
        )
    ).code
    assert f"from {new_module} import PositionQueries" in updated
    assert "PositionQueries as PQ" in updated
    assert "from .position_queries" not in updated
    assert "decision_making.position_queries" not in updated
    assert f'"{new_module}"' in updated


def test_import_rewriter_load_plan_supports_explicit_plan_file(tmp_path):
    rewriter = _load_module("rewrite_imports", "04_rewrite_imports.py")
    plan_path = tmp_path / "package3_rename_plan.json"
    plan_path.write_text(
        json.dumps([
            {
                "old": "apps.reference.domains.strategies.runtimes",
                "new": "apps.reference.domains.strategies.runtimes",
            }
        ]),
        encoding="utf-8",
    )

    plan = rewriter.load_plan(plan_path, None)

    assert plan["apps.reference.domains.strategies.runtimes"] == "apps.reference.domains.strategies.runtimes"


def test_shim_text_contains_deprecation_warning():
    shims = _load_module("write_shims", "06_write_shims.py")
    text = shims.shim_text(
        "aurora_handler.py",
        "apps.reference.domains.strategies.runtimes.aurora.handler",
        "AuroraHandler",
    )
    assert "DeprecationWarning" in text
    assert "AuroraHandler" in text


def test_yaml_json_update_payload_is_stable(tmp_path):
    updater = _load_module("update_yaml_json", "07_update_yaml_json.py")
    assert updater is not None
    payload = {"updated": [],
               "note": "No Package 2 YAML/JSON key-path rewrites required."}
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["updated"] == []


def test_audit_imports_positive(tmp_path):
    audit_imports = _load_module("audit_imports", "audit_imports.py")
    root = tmp_path / "apps" / "reference" / "domains" / "decision_making"
    _write(
        root / "primitives" / "scoring_kernel.py",
        "from apps.reference.domains.decision_making.primitives.aurora_math import compute_aurora_math\n"
        "from apps.reference.domains.decision_making.primitives.aurora_policy import apply_aurora_policy\n",
    )
    _write(root / "primitives" / "aurora_math.py", "\n")
    _write(root / "primitives" / "aurora_policy.py", "\n")
    _write(root / "primitives" / "shields" /
           "base.py", "class BaseShield: ...\n")
    _write(
        root / "primitives" / "shields" / "memory_shield.py",
        "import json\n"
        "from apps.reference.domains.decision_making.primitives.shields.base import BaseShield\n"
        "from apps.reference.core.time.clock import LiveClock\n"
        "from vfoundation.core.protocol import Message\n",
    )
    _write(
        root / "strategies" / "aurora" / "handler.py",
        "from apps.reference.domains.decision_making.primitives.scoring_kernel import QuadraticScoringKernel\n",
    )

    result = audit_imports.inspect_import_graph(
        root, "apps.reference.domains.decision_making")

    assert result["violations"] == []
    assert result["checks"]["scoring_kernel_pair"] is True
    assert result["checks"]["shields_primitives_only"] is True
    assert result["checks"]["handlers_import_primitives"] is True
    assert result["checks"]["handlers_no_facade_or_gateway"] is True
    report = audit_imports.render_report(result)
    assert "Pre-audit passed." in report


def test_audit_imports_detects_forbidden_shield_import(tmp_path):
    audit_imports = _load_module("audit_imports", "audit_imports.py")
    root = tmp_path / "apps" / "reference" / "domains" / "decision_making"
    _write(
        root / "primitives" / "scoring_kernel.py",
        "from apps.reference.domains.decision_making.primitives.aurora_math import compute_aurora_math\n"
        "from apps.reference.domains.decision_making.primitives.aurora_policy import apply_aurora_policy\n",
    )
    _write(root / "primitives" / "aurora_math.py", "\n")
    _write(root / "primitives" / "aurora_policy.py", "\n")
    _write(root / "primitives" / "shields" /
           "base.py", "class BaseShield: ...\n")
    _write(
        root / "primitives" / "shields" / "memory_shield.py",
        "from apps.reference.domains.decision_making.primitives.shields.base import BaseShield\n"
        "from apps.reference.domains.decision_making.gates.execution_gate import ExecutionGate\n",
    )
    _write(
        root / "strategies" / "aurora" / "handler.py",
        "from apps.reference.domains.decision_making.primitives.scoring_kernel import QuadraticScoringKernel\n",
    )

    result = audit_imports.inspect_import_graph(
        root, "apps.reference.domains.decision_making")

    assert any(
        "primitives/shields/memory_shield.py imports apps.reference.domains.decision_making.gates.execution_gate" in entry
        for entry in result["violations"]
    )
    assert result["checks"]["shields_primitives_only"] is False
    report = audit_imports.render_report(result)
    assert "## BLOCKED" in report


def test_audit_imports_detects_forbidden_handler_import(tmp_path):
    audit_imports = _load_module("audit_imports", "audit_imports.py")
    root = tmp_path / "apps" / "reference" / "domains" / "decision_making"
    _write(
        root / "primitives" / "scoring_kernel.py",
        "from apps.reference.domains.decision_making.primitives.aurora_math import compute_aurora_math\n"
        "from apps.reference.domains.decision_making.primitives.aurora_policy import apply_aurora_policy\n",
    )
    _write(root / "primitives" / "aurora_math.py", "\n")
    _write(root / "primitives" / "aurora_policy.py", "\n")
    _write(root / "primitives" / "shields" /
           "base.py", "class BaseShield: ...\n")
    _write(
        root / "primitives" / "shields" / "memory_shield.py",
        "from apps.reference.domains.decision_making.primitives.shields.base import BaseShield\n",
    )
    _write(
        root / "strategies" / "aurora" / "handler.py",
        "from apps.reference.domains.decision_making.primitives.scoring_kernel import QuadraticScoringKernel\n"
        "from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway\n",
    )

    result = audit_imports.inspect_import_graph(
        root, "apps.reference.domains.decision_making")

    assert any(
        "strategies/aurora/handler.py imports apps.reference.domains.decision_making.gateway.strategy_gateway" in entry
        for entry in result["violations"]
    )
    assert result["checks"]["handlers_no_facade_or_gateway"] is False
    report = audit_imports.render_report(result)
    assert "## BLOCKED" in report


def test_audit_imports_shared_tree_allows_config_models(tmp_path):
    audit_imports = _load_module("audit_imports", "audit_imports.py")
    root = tmp_path / "apps" / "reference" / "shared" / "decision_primitives"
    _write(
        root / "exit_manager.py",
        "from apps.reference.config_models import ExitManagerConfig, DangerZoneExitType\n",
    )
    _write(
        root / "shields" / "memory_shield.py",
        "from apps.reference.shared.decision_primitives.shields.base import BaseShield\n"
        "from apps.reference.core.time.clock import LiveClock\n",
    )
    _write(root / "shields" / "base.py", "class BaseShield: ...\n")
    _write(root / "scoring_kernel.py",
           "from apps.reference.shared.decision_primitives.aurora_math import compute_aurora_math\n")
    _write(root / "aurora_math.py", "\n")

    result = audit_imports.inspect_import_graph(
        root, "apps.reference.shared.decision_primitives")

    assert result["violations"] == []
    assert result["checks"]["shared_tree_allowed_prefixes"] is True
    assert result["checks"]["shared_shields_allowed_prefixes"] is True
    report = audit_imports.render_report(result)
    assert "shared decision primitives import only shared/core/config_models/vfoundation/stdlib" in report


def test_audit_imports_shared_tree_detects_forbidden_domain_import(tmp_path):
    audit_imports = _load_module("audit_imports", "audit_imports.py")
    root = tmp_path / "apps" / "reference" / "shared" / "decision_primitives"
    _write(
        root / "exit_manager.py",
        "from apps.reference.domains.decision_making.gates.execution_gate import ExecutionGate\n",
    )
    _write(root / "scoring_kernel.py", "\n")

    result = audit_imports.inspect_import_graph(
        root, "apps.reference.shared.decision_primitives")

    assert any(
        "shared/decision_primitives/exit_manager.py imports apps.reference.domains.decision_making.gates.execution_gate" in entry
        for entry in result["violations"]
    )
    assert result["checks"]["shared_tree_allowed_prefixes"] is False
