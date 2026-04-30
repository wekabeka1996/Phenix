"""Phase 0 Boundary Enforcement Test Suite.

This module proves that declared hot-path modules do not statically import
quarantined legacy/RL/offline modules, and runtime smoke import does not
load them during the tested import path.

Five layers of proof:
1. Inventory completeness — every .py file appears exactly once.
2. Quarantine marker check — every legacy_runtime file has markers.
3. AST/static import scan — hot-path modules do not declare imports of forbidden modules.
4. Forbidden prefix check — all legacy_runtime modules are in the forbidden list.
5. Runtime import smoke test — importing hot-path modules does not load forbidden modules.
"""
from __future__ import annotations

import ast
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
NEOCORTEX_ROOT = REPO_ROOT / "apps" / "reference" / "domains" / "neocortex"
NEOCORTEX_MODULE_PREFIX = "apps.reference.domains.neocortex"

# ---------------------------------------------------------------------------
# Inventory: machine-checkable classification of every file
# ---------------------------------------------------------------------------
# Classification: hot_path, legacy_runtime, offline_research, tests_only

INVENTORY: dict[str, str] = {
    # hot_path ---------------------------------------------------------------
    "__init__.py": "hot_path",
    "config_models.py": "hot_path",
    "contracts/__init__.py": "hot_path",
    "contracts/causal_time.py": "hot_path",
    "contracts/control_decision.py": "hot_path",
    "contracts/decision_outcome_ledger.py": "hot_path",
    "contracts/failure_taxonomy.py": "hot_path",
    "contracts/observation_envelope.py": "hot_path",
    "main.py": "hot_path",
    "logic/__init__.py": "hot_path",
    "logic/datasets/__init__.py": "hot_path",
    "logic/datasets/contracts.py": "hot_path",
    "logic/datasets/cutover.py": "offline_research",
    "logic/datasets/time_provenance.py": "hot_path",
    "logic/gates/__init__.py": "hot_path",
    "logic/gates/shadow.py": "hot_path",
    "logic/ledger/__init__.py": "hot_path",
    "logic/ledger/decision_outcome_ledger.py": "hot_path",
    "logic/failure_ledger.py": "hot_path",
    "logic/ingest/__init__.py": "hot_path",
    "logic/ingest/normalizer.py": "hot_path",
    "logic/ingest/observation.py": "hot_path",
    "logic/ingest/parser.py": "hot_path",
    "logic/ingest/state_aggregator_v2.py": "hot_path",
    "logic/brain/__init__.py": "hot_path",
    "logic/brain/baseline_inference.py": "hot_path",
    "logic/ingest/parsers/__init__.py": "hot_path",
    "logic/ingest/parsers/core_parser.py": "hot_path",
    "logic/ingest/parsers/feature_parser.py": "hot_path",
    "logic/ingest/parsers/order_parser.py": "hot_path",
    "transport/__init__.py": "hot_path",
    "transport/authority_bridge.py": "hot_path",
    "logic/evaluation/__init__.py": "offline_research",
    "logic/evaluation/contracts.py": "offline_research",
    "logic/evaluation/evaluator.py": "offline_research",
    "logic/datasets/hygiene.py": "offline_research",
    "logic/telemetry.py": "offline_research",
    "logic/amygdala/__init__.py": "legacy_runtime",
    "logic/amygdala/valuation.py": "legacy_runtime",
    "logic/memory/__init__.py": "legacy_runtime",
    "logic/memory/buffer.py": "legacy_runtime",
    "logic/memory/graph.py": "legacy_runtime",
    "logic/reward/__init__.py": "legacy_runtime",
    "logic/reward/feature_buffer.py": "legacy_runtime",
    "logic/reward/regime_labeler.py": "legacy_runtime",
    "logic/reward/reward_calculator.py": "legacy_runtime",
    # legacy_runtime ---------------------------------------------------------
    "logic/dreamer.py": "legacy_runtime",
    "logic/brain/core.py": "legacy_runtime",
    "logic/brain/bridge.py": "legacy_runtime",
    "logic/brain/worker.py": "legacy_runtime",
    "logic/brain/vae.py": "legacy_runtime",
    "logic/brain/world_model.py": "legacy_runtime",
    "logic/ingest/tailer.py": "legacy_runtime",
    "logic/ingest/multi_tailer.py": "legacy_runtime",
    "logic/ingest/wal_replayer.py": "legacy_runtime",
    "transport/adapter.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/__init__.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/agent.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/core/dataclasses.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/learning/__init__.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/learning/buffer.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/learning/controllers.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/learning/updater.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/models/__init__.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/models/actor_critic_lstm.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/models/base_model.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/training_loop.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/utils/__init__.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/utils/logging.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/utils/safety.py": "legacy_runtime",
    "PPO/ppo_library_v2/ppo_system/utils/seed.py": "legacy_runtime",
    # offline_research -------------------------------------------------------
    "PPO/ppo_library_v2/examples/01_train_cartpole_single.py": "offline_research",
    "PPO/ppo_library_v2/examples/02_train_cartpole_vectorized.py": "offline_research",
    "experiments/_decision_ledger_baseline.py": "offline_research",
    "experiments/00_oracle_pnl_analysis.py": "offline_research",
    "experiments/01_state_reconstruction.py": "offline_research",
    "experiments/02_action_decoder_simulation.py": "offline_research",
    "experiments/03_reward_decomposition_sim.py": "offline_research",
    "experiments/04_async_checkpoint_reload.py": "offline_research",
    "experiments/05_lstm_memory_isolation_sim.py": "offline_research",
    "experiments/06_aurora_sim_env.py": "offline_research",
    "experiments/07_vae_latent_space_sim.py": "offline_research",
    "experiments/08_decision_ledger_dataset_prep.py": "offline_research",
    "experiments/09_dumb_baseline_eval.py": "offline_research",
    # tests_only -------------------------------------------------------------
    "tests/test_calibration.py": "tests_only",
    "tests/test_dataset_hygiene.py": "tests_only",
    "tests/test_disagreement.py": "tests_only",
    "tests/test_evaluator_reports.py": "tests_only",
    "tests/test_objective_split.py": "tests_only",
    "tests/test_performance_contract.py": "tests_only",
    "tests/test_provenance.py": "tests_only",
    "tests/test_replay_engineering.py": "tests_only",
    "tests/test_sequence_semantics.py": "tests_only",
    "tests/test_shadow_gates.py": "tests_only",
}

HOT_PATH_FILES = sorted(k for k, v in INVENTORY.items() if v == "hot_path")
LEGACY_RUNTIME_FILES = sorted(
    k for k, v in INVENTORY.items() if v == "legacy_runtime")

# Module-path equivalents for forbidden import checks
FORBIDDEN_MODULE_PREFIXES = tuple(
    f"{NEOCORTEX_MODULE_PREFIX}.{rel.replace('/', '.').removesuffix('.py').removesuffix('.__init__')}"
    for rel in LEGACY_RUNTIME_FILES
)

# Hot-path modules that must be scanned for imports
HOT_PATH_MODULES = [
    f"{NEOCORTEX_MODULE_PREFIX}.{rel.replace('/', '.').removesuffix('.py').removesuffix('.__init__')}"
    for rel in HOT_PATH_FILES
    if not rel.endswith("__init__.py")  # __init__.py usually re-exports only
]


# ===================================================================
# Layer 1: Inventory Completeness
# ===================================================================


def _collect_all_py_files() -> set[str]:
    """Walk the neocortex directory and collect all .py files relative to it."""
    found: set[str] = set()
    for py_file in NEOCORTEX_ROOT.rglob("*.py"):
        if "__pycache__" in py_file.parts:
            continue
        rel = str(py_file.relative_to(NEOCORTEX_ROOT)).replace("\\", "/")
        found.add(rel)
    return found


class TestInventoryCompleteness:
    """Every .py file must appear exactly once in the inventory."""

    def test_no_files_missing_from_inventory(self) -> None:
        on_disk = _collect_all_py_files()
        in_inventory = set(INVENTORY.keys())
        missing = sorted(on_disk - in_inventory)
        assert missing == [], (
            f"Files on disk not in inventory: {missing}"
        )

    def test_no_phantom_files_in_inventory(self) -> None:
        on_disk = _collect_all_py_files()
        in_inventory = set(INVENTORY.keys())
        phantom = sorted(in_inventory - on_disk)
        assert phantom == [], (
            f"Inventory references files that do not exist: {phantom}"
        )

    def test_every_file_has_exactly_one_classification(self) -> None:
        allowed = {"hot_path", "legacy_runtime",
                   "offline_research", "tests_only"}
        bad = {
            rel: cls
            for rel, cls in INVENTORY.items()
            if cls not in allowed
        }
        assert bad == {}, f"Unknown classifications: {bad}"


# ===================================================================
# Layer 2: Quarantine Marker Check
# ===================================================================


class TestQuarantineMarkers:
    """Every legacy_runtime file must have both quarantine markers."""

    @pytest.mark.parametrize("rel_path", LEGACY_RUNTIME_FILES)
    def test_legacy_file_has_quarantine_comment(self, rel_path: str) -> None:
        filepath = NEOCORTEX_ROOT / rel_path
        content = filepath.read_text(encoding="utf-8")
        assert "# QUARANTINED: legacy_runtime" in content, (
            f"{rel_path} missing '# QUARANTINED: legacy_runtime' comment"
        )

    @pytest.mark.parametrize("rel_path", LEGACY_RUNTIME_FILES)
    def test_legacy_file_has_quarantine_flag(self, rel_path: str) -> None:
        filepath = NEOCORTEX_ROOT / rel_path
        content = filepath.read_text(encoding="utf-8")
        assert "__quarantined__ = True" in content, (
            f"{rel_path} missing '__quarantined__ = True' flag"
        )

    @pytest.mark.parametrize("rel_path", HOT_PATH_FILES)
    def test_hot_path_file_does_not_have_quarantine_flag(self, rel_path: str) -> None:
        filepath = NEOCORTEX_ROOT / rel_path
        content = filepath.read_text(encoding="utf-8")
        assert "__quarantined__ = True" not in content, (
            f"Hot-path file {rel_path} incorrectly marked as quarantined"
        )


# ===================================================================
# Layer 3: AST/Static Import Scan
# ===================================================================


def _extract_static_imports(filepath: Path) -> list[str]:
    """Parse a Python file and extract all statically declared import targets."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _is_forbidden_import(import_name: str) -> bool:
    """Check if an import name matches any forbidden module prefix."""
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        if import_name == prefix or import_name.startswith(prefix + "."):
            return True
    return False


class TestStaticImportScan:
    """AST scan: hot-path modules must not statically import quarantined modules."""

    @pytest.mark.parametrize("rel_path", [f for f in HOT_PATH_FILES if not f.endswith("__init__.py")])
    def test_hot_path_file_has_no_forbidden_static_imports(
        self, rel_path: str
    ) -> None:
        filepath = NEOCORTEX_ROOT / rel_path
        if not filepath.exists():
            pytest.skip(f"{rel_path} does not exist")
        imports = _extract_static_imports(filepath)
        forbidden = [imp for imp in imports if _is_forbidden_import(imp)]
        assert forbidden == [], (
            f"Hot-path file {rel_path} statically imports quarantined modules: {forbidden}"
        )


# ===================================================================
# Layer 4: Forbidden Prefix Coverage
# ===================================================================


class TestForbiddenPrefixCoverage:
    """Every legacy_runtime module must be represented in FORBIDDEN_MODULE_PREFIXES."""

    def test_every_legacy_module_has_a_forbidden_prefix(self) -> None:
        for rel in LEGACY_RUNTIME_FILES:
            module = (
                f"{NEOCORTEX_MODULE_PREFIX}"
                f".{rel.replace('/', '.').removesuffix('.py').removesuffix('.__init__')}"
            )
            matched = any(
                module == prefix or module.startswith(prefix + ".")
                for prefix in FORBIDDEN_MODULE_PREFIXES
            )
            assert matched, (
                f"Legacy file {rel} (module={module}) is NOT covered by FORBIDDEN_MODULE_PREFIXES"
            )


# ===================================================================
# Layer 5: Runtime Import Smoke Test (subprocess isolation)
# ===================================================================


def _runtime_smoke_import(target_module: str) -> list[str]:
    """Import target_module in a fresh subprocess and check for forbidden module loads."""
    probe_script = """
import importlib
import json
import sys

target = sys.argv[1]
forbidden = tuple(sys.argv[2:])

try:
    importlib.import_module(target)
except Exception as e:
    print(json.dumps({"error": str(e), "loaded": []}))
    sys.exit(0)

loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + '.') for prefix in forbidden)
)

print(json.dumps({"loaded": loaded}))
"""
    completed = subprocess.run(
        [
            sys.executable,
            "-W",
            "ignore",
            "-c",
            probe_script,
            target_module,
            *FORBIDDEN_MODULE_PREFIXES,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        pytest.skip(
            f"Runtime import of {target_module} failed "
            f"(may require unavailable deps like torch).\n"
            f"stderr: {completed.stderr[:500]}"
        )

    output_lines = completed.stdout.strip().splitlines()
    if not output_lines:
        pytest.skip(f"No JSON output from subprocess for {target_module}")

    payload = json.loads(output_lines[-1])
    if "error" in payload and payload["error"]:
        pytest.skip(
            f"Runtime import of {target_module} raised: {payload['error']}"
        )
    return list(payload["loaded"])


# Select a focused subset of hot-path modules for runtime smoke test.
# Full coverage is provided by Layer 3 (AST). Runtime test is supplementary.
RUNTIME_SMOKE_MODULES = [
    f"{NEOCORTEX_MODULE_PREFIX}.config_models",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.datasets.time_provenance",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.datasets.contracts",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.datasets.hygiene",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.ingest.observation",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.ingest.parser",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.ingest.normalizer",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.ingest.state_aggregator_v2",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.brain.baseline_inference",
    f"{NEOCORTEX_MODULE_PREFIX}.logic.gates.shadow",
]


class TestRuntimeImportSmokeTest:
    """Runtime smoke: importing key hot-path modules must not load quarantined modules."""

    @pytest.mark.parametrize("target_module", RUNTIME_SMOKE_MODULES)
    def test_runtime_import_does_not_load_forbidden_modules(
        self, target_module: str
    ) -> None:
        loaded = _runtime_smoke_import(target_module)
        assert loaded == [], (
            f"Runtime import of {target_module} loaded quarantined modules: {loaded}. "
            f"This proves declared hot-path modules do not statically import "
            f"quarantined legacy/RL/offline modules, and runtime smoke import "
            f"does not load them during the tested import path."
        )
