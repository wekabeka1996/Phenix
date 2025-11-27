#!/usr/bin/env python3
"""
Static dependency analyzer for execution_position and shadow_execpos.

What it does:
  - Recursively scans Python modules under the provided roots.
  - Normalizes absolute imports like
    `apps.reference.domains.execution_position.*` into local module names.
  - Builds an internal dependency graph (module -> imported modules inside
    this domain).
  - Heuristically detects unused exports (functions/classes) by tracking:
      * local calls,
      * imported symbols used in other modules,
      * module attribute access on imported modules.
  - Emits a text report plus JSON and Mermaid graph files.

Limitations:
  - Static analysis only; dynamic imports and getattr-based access are not
    detected.
  - Wildcard imports mark all exports from the target module as "used" to
    avoid false positives.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Absolute import prefixes that should be folded into local module names
EXEC_POS_PREFIXES = (
    "apps.reference.domains.execution_position.",
    "apps.reference.domains.execution_position",
)

# Known external consumers: mark their symbols as "used" to reduce false positives
# when usage happens outside this domain (e.g., DecisionMaking, vfoundation).
EXTERNAL_USAGE_HINTS: Dict[str, Set[str] | str] = {
    # Adapter contract consumed by upstream services
    "execution_position.binance_execution_adapter": "*",
    # Facade contract consumed by FSM layer
    "execution_position.runtime_factory": {
        "build_execution_runtime",
        "V2RuntimeFacade",
        "ExecutionRuntime",
    },
    # Shadow runtime interface consumed by facade
    "shadow_execpos.runtime": {"ExecPosRuntimeV2"},
    "shadow_execpos.execution_service": {"ExecutionService"},
    # Domain contracts/utilities consumed by higher layers or tests
    "execution_position.brackets_config": {"clear_brackets_warning_cache"},
    "execution_position.contracts": {
        "BracketErrorCode",
        "BracketOrderPayload",
        "OrderStatus",
        "PositionPayload",
        "is_exit_order",
        "validate_order_command",
    },
    "execution_position.exposure_guard": {"ExposureGuard", "ClipResult"},
    "execution_position.idempotent_cancel": {"OrderStatus"},
    "execution_position.internal_types": {"ExecutionResult"},
    "execution_position.manage_config": {"clear_manage_config_cache"},
    "execution_position.metrics_collector": {"MetricsCollector"},
    "execution_position.order_index": {"OrderIndex"},
    "execution_position.utils_event_bus": {"LocalBus"},
    "execution_position.utils": {
        "calc_tp_sl_from_mark",
        "generate_client_order_id",
        "opposite_side",
        "validate_anti_2021",
        "validate_not_immediate",
    },
    "execution_position.watchdog": {"OrderTimeoutWatchdog"},
    "execution_position.agg_oco_introspection": {"AggOcoStateRow"},
    "execution_position.drift_monitor": {"aggregate_drift_metrics", "compute_drift"},
    "execution_position.config": {"Config"},
    # Shadow public helpers used in tests/tools
    "shadow_execpos.ab_replay": {"ExecPosReplay"},
    "shadow_execpos.agg_oco_replay": {"AggOcoReplayEnforcer"},
    "shadow_execpos.logging_v2": {
        "log_bracket_eval_snapshot",
        "log_runtime_event",
        "log_watchdog_action",
    },
}

# Explicit public API overrides: if provided for a module, only these exports
# will be considered public for reporting/unused checks.
PUBLIC_EXPORT_OVERRIDES: Dict[str, Set[str]] = {
    "execution_position.binance_execution_adapter": {
        "BinanceExecutionAdapter",
        "BinanceValidationError",
        "MockAuditLogger",
    },
    "execution_position.runtime_factory": {
        "ExecutionRuntime",
        "V2RuntimeFacade",
        "build_execution_runtime",
    },
    "shadow_execpos.runtime": {"ExecPosRuntimeV2"},
    "shadow_execpos.execution_service": {"ExecutionService"},
}


def _strip_execpos_prefix(module: str) -> str:
    """
    Convert absolute imports into local module names.

    Examples:
      apps.reference.domains.execution_position.runtime_factory
        -> execution_position.runtime_factory
      apps.reference.domains.execution_position.shadow_execpos.runtime
        -> shadow_execpos.runtime
    """
    for prefix in EXEC_POS_PREFIXES:
        if module == prefix.rstrip("."):
            return "execution_position"

        shadow_prefix = f"{prefix.rstrip('.')}.shadow_execpos."
        if module.startswith(shadow_prefix):
            suffix = module[len(shadow_prefix) :]
            return f"shadow_execpos.{suffix}" if suffix else "shadow_execpos"

        if module.startswith(shadow_prefix.rstrip(".")):
            return "shadow_execpos"

        norm_prefix = f"{prefix.rstrip('.')}."
        if module.startswith(norm_prefix):
            suffix = module[len(norm_prefix) :]
            return f"execution_position.{suffix}" if suffix else "execution_position"

        if module.startswith(prefix.rstrip(".")):
            return "execution_position"

    return module


def _resolve_relative_import(
    current_module: str, level: int, target: Optional[str]
) -> str:
    """
    Resolve a relative import to an absolute module name (within our local naming).
    """
    parts = current_module.split(".")
    # If this is a non-package module, drop the last segment to get the package
    if parts and parts[-1] != "__init__":
        parts = parts[:-1]

    # Walk up the tree for higher relative levels
    if level > 1:
        parts = parts[: -(level - 1)] if level - 1 <= len(parts) else []

    if target:
        parts.extend(target.split("."))

    return ".".join(p for p in parts if p)


@dataclass(frozen=True)
class ModuleSource:
    root: Path
    label: str  # e.g. "execution_position" or "shadow_execpos"


class ExecutionPositionDependencyAnalyzer(ast.NodeVisitor):
    """
    Collects exports, imports, and symbol usage for a single module.
    """

    def __init__(self, module_name: str, file_path: Path):
        self.module_name = module_name
        self.file_path = file_path

        # Exports
        self.exports: Set[str] = set()
        self.class_methods: Dict[str, Set[str]] = {}
        self._class_stack: List[str] = []

        # Imports and aliases
        self.imported_modules: Set[str] = set()
        self.import_aliases: Dict[str, str] = {}  # alias -> module
        self.imported_symbols: Dict[str, Tuple[str, str]] = {}  # alias -> (module, name)
        self.wildcard_imports: Set[str] = set()

        # Usage tracking
        self.symbol_usages: Set[Tuple[str, str]] = set()  # (module, symbol)
        self.local_usage: Set[str] = set()

    # -- AST visitors -----------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module = _strip_execpos_prefix(alias.name)
            alias_name = alias.asname or alias.name.split(".")[0]
            self.import_aliases[alias_name] = module
            if module:
                self.imported_modules.add(module)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None and node.level == 0:
            return

        if node.level and node.level > 0:
            module_name = _resolve_relative_import(self.module_name, node.level, node.module)
        else:
            module_name = _strip_execpos_prefix(node.module or "")

        module_name = module_name.strip(".")
        if module_name:
            self.imported_modules.add(module_name)

        for alias in node.names:
            if alias.name == "*":
                if module_name:
                    self.wildcard_imports.add(module_name)
                continue

            alias_name = alias.asname or alias.name
            self.imported_symbols[alias_name] = (module_name, alias.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if not self._class_stack:
            self.exports.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if not self._class_stack:
            self.exports.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.exports.add(node.name)
        methods: Set[str] = set()
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.add(item.name)
        if methods:
            self.class_methods[node.name] = methods
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_Name(self, node: ast.Name) -> None:
        # Local usage of exported symbol
        if node.id in self.exports:
            self.local_usage.add(node.id)

        # Imported symbol usage
        if node.id in self.imported_symbols:
            module, original = self.imported_symbols[node.id]
            if module:
                self.symbol_usages.add((module, original))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Handle module alias attr: alias.symbol
        if isinstance(node.value, ast.Name):
            base = node.value.id
            if base in self.import_aliases:
                module = self.import_aliases[base]
                if module:
                    self.symbol_usages.add((module, node.attr))
        self.generic_visit(node)


class ModuleDependencyGraph:
    """
    Scans module sources, builds dependency graph, and produces reports.
    """

    def __init__(self, sources: Iterable[ModuleSource]):
        self.sources = list(sources)
        self.modules: Dict[str, ExecutionPositionDependencyAnalyzer] = {}
        self._scan_sources()

    # -- Scanning ---------------------------------------------------------

    def _iter_py_files(self, root: Path) -> Iterable[Path]:
        for file in root.rglob("*.py"):
            if "__pycache__" in file.parts:
                continue
            yield file

    def _path_to_module_name(self, source: ModuleSource, file_path: Path) -> str:
        rel_parts = list(file_path.relative_to(source.root).parts)
        if rel_parts[-1] == "__init__.py":
            rel_parts = rel_parts[:-1]
        else:
            rel_parts[-1] = rel_parts[-1][:-3]  # strip .py

        if rel_parts:
            return ".".join([source.label] + rel_parts)
        return source.label

    def _scan_sources(self) -> None:
        for source in self.sources:
            for file_path in self._iter_py_files(source.root):
                # Avoid double-scanning when one source root is nested inside another
                skip = False
                for other in self.sources:
                    if other is source:
                        continue
                    # Only skip if the other root is inside this source root and the file is under that nested root
                    if other.root.is_relative_to(source.root) and file_path.is_relative_to(other.root):
                        skip = True
                        break
                if skip:
                    continue
                module_name = self._path_to_module_name(source, file_path)
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    content = file_path.read_text(errors="ignore")
                try:
                    tree = ast.parse(content, filename=str(file_path))
                except SyntaxError as exc:
                    print(f"[WARN] Skip {file_path}: syntax error {exc}")
                    continue

                analyzer = ExecutionPositionDependencyAnalyzer(module_name, file_path)
                analyzer.visit(tree)
                self.modules[module_name] = analyzer

        self._apply_public_overrides()

    def _apply_public_overrides(self) -> None:
        """
        Restrict exports for modules that have an explicit public API override.
        """
        for module_name, analyzer in self.modules.items():
            if module_name in PUBLIC_EXPORT_OVERRIDES:
                override = PUBLIC_EXPORT_OVERRIDES[module_name]
                analyzer.exports = {e for e in analyzer.exports if e in override}

    # -- Analysis helpers -------------------------------------------------

    def _resolve_dependency(self, import_name: str) -> Optional[str]:
        """
        Map an import string to a known module in this graph, if possible.
        Tries exact match first; otherwise attempts to match by prefix.
        """
        if import_name in self.modules:
            return import_name

        # Normalize with execution_position prefix stripping
        normalized = _strip_execpos_prefix(import_name)
        if normalized in self.modules:
            return normalized

        # If import refers to a package, see if any module starts with it
        for candidate in self.modules:
            if candidate.startswith(f"{normalized}."):
                return candidate

        return None

    def _build_used_symbols(self) -> Dict[str, Set[str]]:
        """
        Aggregate symbol usages across all modules.
        """
        used: Dict[str, Set[str]] = {}

        # Cross-module usages
        for analyzer in self.modules.values():
            for module, symbol in analyzer.symbol_usages:
                target = self._resolve_dependency(module)
                if target:
                    used.setdefault(target, set()).add(symbol)

            for wildcard in analyzer.wildcard_imports:
                target = self._resolve_dependency(wildcard)
                if target in self.modules:
                    # Mark all exports as used to avoid false positives
                    used.setdefault(target, set()).update(
                        self.modules[target].exports
                    )

        # Local usages
        for module_name, analyzer in self.modules.items():
            if analyzer.local_usage:
                used.setdefault(module_name, set()).update(analyzer.local_usage)

        # External usage hints (mark as used to suppress false positives)
        for module_name, symbols in EXTERNAL_USAGE_HINTS.items():
            if module_name not in self.modules:
                continue
            if symbols == "*":
                used.setdefault(module_name, set()).update(self.modules[module_name].exports)
            else:
                used.setdefault(module_name, set()).update(symbols)

        return used

    def find_unused_exports(self) -> Dict[str, Set[str]]:
        """
        Heuristic unused export detection.
        """
        used = self._build_used_symbols()
        unused: Dict[str, Set[str]] = {}

        for module_name, analyzer in self.modules.items():
            public_exports = {e for e in analyzer.exports if not e.startswith("_")}
            used_exports = used.get(module_name, set())
            unused_exports = public_exports - used_exports
            if unused_exports:
                unused[module_name] = unused_exports

        return unused

    def find_internal_dependencies(self) -> Dict[str, Set[str]]:
        """
        Returns module -> set(imported module) within this domain.
        """
        internal: Dict[str, Set[str]] = {}
        for module_name, analyzer in self.modules.items():
            deps: Set[str] = set()
            for imp in analyzer.imported_modules:
                target = self._resolve_dependency(imp)
                if target:
                    deps.add(target)
            if deps:
                internal[module_name] = deps
        return internal

    def find_cycles(self) -> List[List[str]]:
        deps = self.find_internal_dependencies()
        cycles: List[List[str]] = []

        def dfs(node: str, path: List[str], visited: Set[str]) -> None:
            if node in path:
                start = path.index(node)
                cycle = path[start:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            if node in visited:
                return

            visited.add(node)
            path.append(node)
            for neighbor in deps.get(node, set()):
                dfs(neighbor, path.copy(), visited.copy())

        for module in deps:
            dfs(module, [], set())
        return cycles

    # -- Reporting --------------------------------------------------------

    def generate_report(self) -> str:
        lines: List[str] = []
        lines.append("=" * 70)
        lines.append("Execution Position Dependency Report (main + shadow)")
        lines.append("=" * 70)

        total_exports = sum(len(m.exports) for m in self.modules.values())
        lines.append(f"\nSummary:")
        lines.append(f"  Modules scanned: {len(self.modules)}")
        lines.append(f"  Total exports (funcs/classes): {total_exports}")

        lines.append("\nModules:")
        for module_name in sorted(self.modules):
            analyzer = self.modules[module_name]
            lines.append(f"  - {module_name}")
            if analyzer.exports:
                exports = ", ".join(sorted(analyzer.exports))
                lines.append(f"      Exports: {exports}")
            if analyzer.imported_modules:
                resolved_internal = sorted(
                    dep for dep in (self._resolve_dependency(i) for i in analyzer.imported_modules) if dep
                )
                external = sorted(
                    dep
                    for dep in analyzer.imported_modules
                    if not self._resolve_dependency(dep)
                )
                if resolved_internal:
                    lines.append(f"      Internal imports: {', '.join(resolved_internal)}")
                if external:
                    lines.append(f"      External imports: {', '.join(external)}")

        unused = self.find_unused_exports()
        lines.append("\nUnused exports (heuristic):")
        if unused:
            for module, symbols in sorted(unused.items()):
                lines.append(f"  - {module}: {', '.join(sorted(symbols))}")
        else:
            lines.append("  (none)")

        cycles = self.find_cycles()
        lines.append("\nDependency cycles:")
        if cycles:
            for cycle in cycles:
                lines.append(f"  - {' -> '.join(cycle)}")
        else:
            lines.append("  (none)")

        deps = self.find_internal_dependencies()
        lines.append("\nInternal dependencies:")
        if deps:
            for module, targets in sorted(deps.items()):
                lines.append(f"  - {module} -> {', '.join(sorted(targets))}")
        else:
            lines.append("  (none)")

        independent = [
            m for m, a in self.modules.items()
            if not any(self._resolve_dependency(i) for i in a.imported_modules)
        ]
        lines.append("\nModules without internal imports:")
        if independent:
            for module in sorted(independent):
                lines.append(f"  - {module}")
        else:
            lines.append("  (none)")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    def export_to_json(self, output_file: str) -> None:
        data = {
            "modules": list(self.modules.keys()),
            "exports": {k: sorted(v.exports) for k, v in self.modules.items()},
            "unused_exports": {k: sorted(v) for k, v in self.find_unused_exports().items()},
            "internal_dependencies": {
                k: sorted(v) for k, v in self.find_internal_dependencies().items()
            },
            "cycles": self.find_cycles(),
        }
        Path(output_file).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] JSON written to {output_file}")

    def export_to_mermaid(self, output_file: str = "exec_pos_deps.md") -> None:
        deps = self.find_internal_dependencies()
        cycles = self.find_cycles()

        lines = ["```mermaid", "graph LR"]
        for module, targets in sorted(deps.items()):
            for target in sorted(targets):
                lines.append(f"    {module.replace('.', '_')}[{module}] --> {target.replace('.', '_')}[{target}]")

        if cycles:
            lines.append("    %% Detected cycles:")
            for cycle in cycles:
                lines.append(f"    %% {' -> '.join(cycle)}")

        lines.append("```")
        Path(output_file).write_text("\n".join(lines), encoding="utf-8")
        print(f"[OK] Mermaid graph written to {output_file}")


def main() -> None:
    exec_pos_dir = Path(__file__).parent.parent / "apps" / "reference" / "domains" / "execution_position"
    main_dir = exec_pos_dir
    shadow_dir = exec_pos_dir / "shadow_execpos"

    sources = [
        ModuleSource(root=main_dir, label="execution_position"),
        ModuleSource(root=shadow_dir, label="shadow_execpos"),
    ]

    print("Scanning module roots:")
    for src in sources:
        print(f"  - {src.label}: {src.root}")
    print()

    graph = ModuleDependencyGraph(sources)

    report = graph.generate_report()
    print(report)

    output_dir = exec_pos_dir / "analysis_output"
    output_dir.mkdir(exist_ok=True)

    graph.export_to_json(str(output_dir / "dependencies.json"))
    graph.export_to_mermaid(str(output_dir / "dependencies.md"))

    report_path = output_dir / "DEPENDENCY_REPORT.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n[OK] Report written to {report_path}")


if __name__ == "__main__":
    main()
