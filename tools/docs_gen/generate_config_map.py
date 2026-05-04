#!/usr/bin/env python3
from __future__ import annotations

import ast
import inspect
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, get_args, get_origin

import yaml
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
APPS_REF = ROOT / "apps" / "reference"
CONFIG_DIR = ROOT / "config" / "aurora"
OUT_MD = ROOT / "docs" / "CONFIG_MAP.md"


FOCUS_TOKENS = (
    "risk",
    "drawdown",
    "loss",
    "cvar",
    "exposure",
    "utilization",
    "slippage",
    "latency",
    "timeout",
    "ttl",
    "cooldown",
    "leverage",
    "margin",
    "weights",
    "weight",
    "threshold",
    "qos",
    "watchdog",
    "order",
    "mode",
    "assign",
    "registry",
)


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig", errors="replace") as f:
        return yaml.safe_load(f)


def _flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            seg = str(k)
            path = f"{prefix}.{seg}" if prefix else seg
            if isinstance(v, dict):
                out.update(_flatten(v, path))
            elif isinstance(v, list):
                out[path] = v
                for item in v:
                    if isinstance(item, dict):
                        out.update(_flatten(item, f"{path}[*]"))
            else:
                out[path] = v
    else:
        if prefix:
            out[prefix] = data
    return out


def _unwrap_optional(tp: Any) -> Any:
    origin = get_origin(tp)
    if origin is None:
        return tp
    if origin is getattr(__import__("typing"), "Union"):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp


def _is_any(tp: Any) -> bool:
    return tp is Any


def _is_basemodel(tp: Any) -> bool:
    try:
        return inspect.isclass(tp) and issubclass(tp, BaseModel)
    except Exception:
        return False


@dataclass(frozen=True)
class Usage:
    files: set[str]
    roles: Counter[str]


class SchemaIndex:
    def __init__(self, root_model: type[BaseModel], *, globalns: dict[str, Any] | None = None):
        import typing

        self.children: dict[str, set[str]] = defaultdict(set)  # prefix -> {child segments}
        self.open_prefixes: set[str] = set()  # Dict[str, Any] accept-any namespaces
        self.model_prefixes: dict[type[BaseModel], set[str]] = defaultdict(set)
        self.leaf_paths: set[str] = set()
        self._visited: set[tuple[Any, str]] = set()
        self._typing = typing
        self._globalns = globalns or {}
        self._hints_cache: dict[type[BaseModel], dict[str, Any]] = {}
        self._walk(root_model, "")

    def _add_child(self, prefix: str, child: str) -> None:
        self.children[prefix].add(child)

    def _walk(self, tp: Any, prefix: str) -> None:
        tp = _unwrap_optional(tp)
        key = (tp, prefix)
        if key in self._visited:
            return
        self._visited.add(key)

        if _is_basemodel(tp):
            model: type[BaseModel] = tp
            self.model_prefixes[model].add(prefix)
            if model not in self._hints_cache:
                try:
                    self._hints_cache[model] = self._typing.get_type_hints(
                        model, globalns=self._globalns, localns=self._globalns, include_extras=True
                    )
                except Exception:
                    self._hints_cache[model] = {}
            for field_name, field in model.model_fields.items():
                self._add_child(prefix, field_name)
                child_prefix = f"{prefix}.{field_name}" if prefix else field_name
                ann = self._hints_cache[model].get(field_name, field.annotation)
                self._walk(ann, child_prefix)
            return

        origin = get_origin(tp)
        if origin is dict:
            args = get_args(tp) or (Any, Any)
            v_t = _unwrap_optional(args[1])
            if _is_any(v_t):
                self.open_prefixes.add(prefix)
                self.leaf_paths.add(prefix)
                return
            if _is_basemodel(v_t):
                self._add_child(prefix, "*")
                self._walk(v_t, f"{prefix}.*" if prefix else "*")
                return
            self._add_child(prefix, "*")
            self.leaf_paths.add(prefix)
            return

        if origin is list:
            args = get_args(tp) or (Any,)
            it = _unwrap_optional(args[0])
            if _is_basemodel(it):
                self._add_child(prefix, "[*]")
                self._walk(it, f"{prefix}.[*]" if prefix else "[*]")
                return
            self.leaf_paths.add(prefix)
            return

        self.leaf_paths.add(prefix)

    def combine_prefix(self, model: type[BaseModel], rel_path: str) -> list[str]:
        out: list[str] = []
        for pref in self.model_prefixes.get(model, set()):
            if not pref:
                out.append(rel_path)
            elif not rel_path:
                out.append(pref)
            else:
                out.append(f"{pref}.{rel_path}")
        return out

    def is_schema_path(self, path: str) -> bool:
        # Accept-any subtrees first.
        for op in self.open_prefixes:
            if op and (path == op or path.startswith(op + ".")):
                return True

        segs = path.split(".") if path else []

        def rec(i: int, cur: str) -> bool:
            if i == len(segs):
                return True
            seg = segs[i]
            kids = self.children.get(cur, set())

            if seg in kids:
                nxt = f"{cur}.{seg}" if cur else seg
                if rec(i + 1, nxt):
                    return True

            if "*" in kids:
                nxt = f"{cur}.*" if cur else "*"
                if rec(i + 1, nxt):
                    return True

            if "[*]" in kids:
                nxt = f"{cur}.[*]" if cur else "[*]"
                if rec(i + 1, nxt):
                    return True

            return False

        return rec(0, "")


def _annotation_last(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _annotation_last(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.split(".")[-1]
    return None


def _expr_chain(expr: ast.AST) -> list[str] | None:
    if isinstance(expr, ast.Name):
        return [expr.id]
    if isinstance(expr, ast.Attribute):
        base = _expr_chain(expr.value)
        if base is None:
            return None
        return base + [expr.attr]
    if isinstance(expr, ast.Subscript):
        base = _expr_chain(expr.value)
        if base is None:
            return None
        return base + ["*"]
    return None


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    out: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            out[id(child)] = parent
    return out


def _is_intermediate_attr(node: ast.Attribute, parents: dict[int, ast.AST]) -> bool:
    p = parents.get(id(node))
    return isinstance(p, ast.Attribute) and p.value is node


def _classify(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    cur: ast.AST = node
    for _ in range(6):
        p = parents.get(id(cur))
        if p is None:
            break
        if isinstance(p, (ast.If, ast.While)) and getattr(p, "test", None) is cur:
            return "Logic Control"
        if isinstance(p, (ast.Compare, ast.BinOp)):
            return "Math/Threshold"
        if isinstance(p, ast.Call):
            fn = p.func
            fn_name = None
            if isinstance(fn, ast.Name):
                fn_name = fn.id
            elif isinstance(fn, ast.Attribute):
                fn_name = fn.attr
            if fn_name and any(
                t in fn_name.lower()
                for t in ("connect", "client", "session", "request", "open", "path", "url", "db", "sqlite", "ws")
            ):
                return "Infrastructure"
        cur = p
    return "Other"


def scan_usage(schema: SchemaIndex, *, model_module) -> dict[str, Usage]:
    model_classes: dict[str, type[BaseModel]] = {
        name: obj
        for name, obj in vars(model_module).items()
        if _is_basemodel(obj) and obj is not BaseModel
    }

    usage_files: dict[str, set[str]] = defaultdict(set)
    usage_roles: dict[str, Counter[str]] = defaultdict(Counter)

    def record(path: str, file_rel: str, role: str) -> None:
        if not path:
            return
        last = path.split(".")[-1]
        if last.startswith("__") or last in {
            "model_dump",
            "model_copy",
            "model_validate",
            "model_construct",
            "copy",
            "dict",
            "get",
            "keys",
            "items",
            "values",
            "pop",
            "setdefault",
        }:
            return
        usage_files[path].add(file_rel)
        usage_roles[path][role] += 1

    def model_from_annotation(ann_last: str | None) -> type[BaseModel] | None:
        if ann_last and ann_last in model_classes:
            return model_classes[ann_last]
        return None

    # DomainConfigResolver getter return types (maps resolver.get_*() return objects)
    resolver_return_types: dict[str, type[BaseModel]] = {}
    try:
        import typing
        import apps.reference.domain_config as domain_config_module  # type: ignore
        from apps.reference.domain_config import DomainConfigResolver  # type: ignore

        for name, fn in vars(DomainConfigResolver).items():
            if not callable(fn) or not name.startswith("get_"):
                continue
            try:
                hints = typing.get_type_hints(
                    fn, globalns=vars(domain_config_module), localns=vars(domain_config_module)
                )
            except Exception:
                hints = {}
            ret = hints.get("return")
            if ret is None:
                continue
            ret = _unwrap_optional(ret)
            if _is_basemodel(ret) and ret is not BaseModel:
                resolver_return_types[name] = ret
    except Exception:
        resolver_return_types = {}

    # Invert schema model prefixes so we can infer types from config attribute paths.
    prefix_to_models: dict[str, set[type[BaseModel]]] = defaultdict(set)
    for model_t, prefixes in schema.model_prefixes.items():
        for pref in prefixes:
            if pref:
                prefix_to_models[pref].add(model_t)

    def infer_model_from_value(
        local_types: dict[str, type[BaseModel]],
        self_attr_types: dict[str, type[BaseModel]],
        value: ast.AST,
    ) -> type[BaseModel] | None:
        # Case 1: call to DomainConfigResolver getter
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
            inferred = resolver_return_types.get(value.func.attr)
            if inferred is not None:
                return inferred

        # Case 2: call to _get_config_value(["a","b"]) returning a known model prefix
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "_get_config_value":
            if value.args and isinstance(value.args[0], ast.List):
                segs: list[str] = []
                for elt in value.args[0].elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        segs.append(elt.value)
                    else:
                        segs = []
                        break
                if segs:
                    path = ".".join(segs)
                    candidates = prefix_to_models.get(path, set())
                    if len(candidates) == 1:
                        return next(iter(candidates))

        # Case 3: attribute chain rooted at a typed base and pointing to a known model prefix
        if isinstance(value, ast.Attribute):
            chain = _expr_chain(value)
            if not chain:
                return None
            candidates: set[type[BaseModel]] = set()

            # Local base
            if chain[0] in local_types:
                base_model = local_types[chain[0]]
                rel = ".".join(chain[1:])
                for full in schema.combine_prefix(base_model, rel):
                    candidates |= prefix_to_models.get(full, set())

            # self.<attr> base
            if len(chain) >= 2 and chain[0] == "self" and chain[1] in self_attr_types:
                base_model = self_attr_types[chain[1]]
                rel = ".".join(chain[2:])
                for full in schema.combine_prefix(base_model, rel):
                    candidates |= prefix_to_models.get(full, set())

            if len(candidates) == 1:
                return next(iter(candidates))
        return None

    def scan_function(
        fn: ast.AST,
        *,
        file_rel: str,
        self_attrs: dict[str, type[BaseModel]] | None,
    ) -> None:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return

        parents = _parents(fn)
        local_types: dict[str, type[BaseModel]] = {}
        self_attr_types = dict(self_attrs or {})

        # Seed locals from arg annotations
        for arg in fn.args.args + fn.args.kwonlyargs:
            model = model_from_annotation(_annotation_last(arg.annotation))
            if model is not None:
                local_types[arg.arg] = model

        # Seed locals from get_config() / load_config() assignments
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                callee = node.value.func
                is_get_cfg = isinstance(callee, ast.Name) and callee.id == "get_config"
                is_load_cfg = isinstance(callee, ast.Attribute) and callee.attr == "load_config"
                if is_get_cfg or is_load_cfg:
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            local_types[t.id] = model_module.AuroraConfig

        # Inference loop: learn new locals and self attrs
        for _ in range(2):
            before = (len(local_types), len(self_attr_types))
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign):
                    inferred = infer_model_from_value(local_types, self_attr_types, node.value)
                    if inferred is None:
                        continue
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            local_types[tgt.id] = inferred
                        elif (
                            isinstance(tgt, ast.Attribute)
                            and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == "self"
                        ):
                            self_attr_types[tgt.attr] = inferred
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    inferred = infer_model_from_value(local_types, self_attr_types, node.value)
                    if inferred is None:
                        continue
                    tgt = node.target
                    if isinstance(tgt, ast.Name):
                        local_types[tgt.id] = inferred
                    elif (
                        isinstance(tgt, ast.Attribute)
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "self"
                    ):
                        self_attr_types[tgt.attr] = inferred
            after = (len(local_types), len(self_attr_types))
            if after == before:
                break

        # Dynamic: _get_config_value(["a","b","c"])
        literal_get_paths: set[str] = set()
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Attribute) and node.func.attr == "_get_config_value"):
                continue
            if not node.args or not isinstance(node.args[0], ast.List):
                continue
            segs: list[str] = []
            ok = True
            for elt in node.args[0].elts:
                if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
                    ok = False
                    break
                segs.append(elt.value)
            if not ok or not segs:
                continue
            path = ".".join(segs)
            literal_get_paths.add(path)
            record(path, file_rel, "Other")

        # Record attribute/subscript usage in this function scope
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and not _is_intermediate_attr(node, parents):
                chain = _expr_chain(node)
                if not chain:
                    continue
                role = _classify(node, parents)

                # Local var root
                root = chain[0]
                if root in local_types:
                    model = local_types[root]
                    rel = ".".join(chain[1:])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, role)
                    continue

                # self.<attr> root
                if len(chain) >= 2 and chain[0] == "self" and chain[1] in self_attr_types:
                    model = self_attr_types[chain[1]]
                    rel = ".".join(chain[2:])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, role)

            if isinstance(node, ast.Subscript):
                base = _expr_chain(node.value)
                if not base:
                    continue
                if not (isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
                    continue
                key = node.slice.value
                role = _classify(node, parents)

                if base[0] in local_types:
                    model = local_types[base[0]]
                    rel = ".".join(base[1:] + [key])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, role)
                    continue

                if len(base) >= 2 and base[0] == "self" and base[1] in self_attr_types:
                    model = self_attr_types[base[1]]
                    rel = ".".join(base[2:] + [key])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, role)

            # ExecPosFSM helper: get_watchdog_setting("ack_ttl_ms", ...)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args:
                if node.func.id == "get_watchdog_setting":
                    a0 = node.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        leaf_key = a0.value
                        for base in sorted([p for p in literal_get_paths if p.endswith("watchdog")]):
                            record(f"{base}.{leaf_key}", file_rel, "Other")

    # Precompute class-level self attribute types (from __init__ scopes)
    class_self_attrs: dict[str, dict[str, type[BaseModel]]] = {}

    for pf in APPS_REF.rglob("*.py"):
        if pf.name == "config_models.py":
            continue
        try:
            src = pf.read_text(encoding="utf-8", errors="replace")
            module_tree = ast.parse(src, filename=str(pf))
        except SyntaxError:
            continue

        file_rel = str(pf.relative_to(ROOT))

        for node in module_tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            init_fn = next(
                (n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
                None,
            )
            if init_fn is not None:
                # Infer self attrs by scanning __init__ in its own scope.
                inferred_self: dict[str, type[BaseModel]] = {}
                # Seed local types from __init__ args
                init_local_types: dict[str, type[BaseModel]] = {}
                for arg in init_fn.args.args + init_fn.args.kwonlyargs:
                    model = model_from_annotation(_annotation_last(arg.annotation))
                    if model is not None:
                        init_local_types[arg.arg] = model

                # Run a small inference for assignments in __init__ (captures self.config = config, and resolver getters)
                for sub in ast.walk(init_fn):
                    if isinstance(sub, ast.Assign):
                        inferred = infer_model_from_value(init_local_types, inferred_self, sub.value)
                        if inferred is None:
                            continue
                        for tgt in sub.targets:
                            if (
                                isinstance(tgt, ast.Attribute)
                                and isinstance(tgt.value, ast.Name)
                                and tgt.value.id == "self"
                            ):
                                inferred_self[tgt.attr] = inferred
                class_self_attrs[node.name] = inferred_self

            # Scan methods in class with class self attrs
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scan_function(item, file_rel=file_rel, self_attrs=class_self_attrs.get(node.name))

        # Also scan module-level functions
        for node in module_tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scan_function(node, file_rel=file_rel, self_attrs=None)

    return {k: Usage(files=v, roles=usage_roles.get(k, Counter())) for k, v in usage_files.items()}


def normalize_yaml_sources() -> tuple[dict[str, dict[str, Any]], dict[str, set[str]]]:
    out_by_file: dict[str, dict[str, Any]] = {}
    sources_by_path: dict[str, set[str]] = defaultdict(set)

    def add(rel_file: str, flat: dict[str, Any]) -> None:
        out_by_file[rel_file] = flat
        for p in flat.keys():
            sources_by_path[p].add(rel_file)

    # trading.yaml is merged at root.
    add("config/aurora/trading.yaml", _flatten(_load_yaml(CONFIG_DIR / "trading.yaml")))

    # system.yaml is merged at root; some keys are extracted into system_meta.*
    system_raw = _load_yaml(CONFIG_DIR / "system.yaml")
    system_flat = _flatten(system_raw)
    extracted: dict[str, Any] = {}
    mapping = {
        "config_version": "system_meta.system_config_version",
        "sequential_tests": "system_meta.sequential_tests",
        "risk_core": "system_meta.risk_core",
        "kelly": "system_meta.kelly",
        "calibrator": "system_meta.calibrator",
        "hawkes": "system_meta.hawkes",
        "hardening": "system_meta.hardening",
        "position_tracking": "system_meta.position_tracking",
    }
    for src, dst in mapping.items():
        # Move the entire subtree (src or src.*) into system_meta.*
        to_move = [k for k in system_flat.keys() if k == src or k.startswith(src + ".")]
        for k in to_move:
            suffix = "" if k == src else k[len(src) :]
            extracted[dst + suffix] = system_flat.pop(k)
    add("config/aurora/system.yaml", system_flat)
    if extracted:
        add("config/aurora/system.yaml#extracted_to_system_meta", extracted)

    # regime.yaml is merged at root; config_version is extracted to system_meta.regime_config_version
    regime_raw = _load_yaml(CONFIG_DIR / "regime.yaml")
    regime_flat = _flatten(regime_raw)
    regime_meta: dict[str, Any] = {}
    if "config_version" in regime_flat:
        regime_meta["system_meta.regime_config_version"] = regime_flat.pop("config_version")
    if "hotreload_whitelist" in regime_flat:
        # copy (not move) per ConfigLoader._extract_system_meta
        regime_meta["system_meta.hotreload_whitelist"] = regime_flat["hotreload_whitelist"]
    add("config/aurora/regime.yaml", regime_flat)
    if regime_meta:
        add("config/aurora/regime.yaml#extracted_or_copied_to_system_meta", regime_meta)

    # domains.yaml becomes root.domains.*
    domains_flat = _flatten(_load_yaml(CONFIG_DIR / "domains.yaml"))
    add("config/aurora/domains.yaml", {f"domains.{k}": v for k, v in domains_flat.items()})

    # instruments.yaml becomes root.instruments.* (strip optional top-level 'instruments')
    inst_raw = _load_yaml(CONFIG_DIR / "instruments.yaml")
    if isinstance(inst_raw, dict) and "instruments" in inst_raw and isinstance(inst_raw["instruments"], dict):
        inst_raw = inst_raw["instruments"]
    inst_flat = _flatten(inst_raw)
    add("config/aurora/instruments.yaml", {f"instruments.{k}": v for k, v in inst_flat.items()})

    # strategies.yaml becomes root.strategies_registry.*
    reg_flat = _flatten(_load_yaml(CONFIG_DIR / "strategies.yaml"))
    add("config/aurora/strategies.yaml", {f"strategies_registry.{k}": v for k, v in reg_flat.items()})

    # strategy profiles become root.strategies.<id>.*
    for profile in sorted((CONFIG_DIR / "strategies").glob("*.yaml")):
        strategy_id = profile.stem
        raw = _load_yaml(profile)
        if isinstance(raw, dict) and strategy_id in raw and isinstance(raw[strategy_id], dict):
            raw = raw[strategy_id]
        flat = _flatten(raw)
        add(f"config/aurora/strategies/{profile.name}", {f"strategies.{strategy_id}.{k}": v for k, v in flat.items()})

    return out_by_file, sources_by_path


def _role_summary(roles: Counter[str]) -> str:
    if not roles:
        return ""
    return ", ".join([f"{k}={v}" for k, v in roles.most_common(3)])


def _pick_critical_keys(keys: Iterable[str]) -> list[str]:
    picked: list[str] = []
    for k in sorted(set(keys)):
        low = k.lower()
        if k in ("trading_mode", "trading.mode"):
            picked.append(k)
            continue
        if any(tok in low for tok in FOCUS_TOKENS):
            picked.append(k)
    return picked[:220]


def main() -> int:
    from apps.reference import config_models as config_models_module
    from apps.reference.config_loader import ConfigLoader

    schema = SchemaIndex(config_models_module.AuroraConfig, globalns=vars(config_models_module))
    usage = scan_usage(schema, model_module=config_models_module)

    yaml_by_file, sources_by_path = normalize_yaml_sources()
    normalized_yaml_paths = set(sources_by_path.keys())

    loader = ConfigLoader()
    cfg = loader.load_config()
    cfg_flat = _flatten(cfg.model_dump(exclude_none=False))
    active_paths = set(cfg_flat.keys())

    # YAML -> schema mismatches (after normalization)
    yaml_unloadable: dict[str, list[str]] = {}
    for rel, flat in yaml_by_file.items():
        bad = sorted([p for p in flat.keys() if not schema.is_schema_path(p)])
        if bad:
            yaml_unloadable[rel] = bad

    # Dead candidates:
    # - active keys (effective config leafs) with 0 refs
    # - YAML-defined keys with 0 refs
    def is_under_open(path: str) -> bool:
        return any(path == op or path.startswith(op + ".") for op in schema.open_prefixes if op)

    active_dead = sorted([p for p in active_paths if schema.is_schema_path(p) and not is_under_open(p) and p not in usage])
    yaml_dead = sorted([p for p in normalized_yaml_paths if not is_under_open(p) and p not in usage])

    # Code -> schema drift (paths referenced in code but not present in schema)
    drift = sorted([p for p in usage.keys() if not schema.is_schema_path(p)])

    # Duplicate heuristic: trading vs domains, focus tokens, match by leaf name
    trading_paths = set(yaml_by_file.get("config/aurora/trading.yaml", {}).keys())
    domains_paths = set(yaml_by_file.get("config/aurora/domains.yaml", {}).keys())

    def is_focus(path: str) -> bool:
        low = path.lower()
        return any(tok in low for tok in FOCUS_TOKENS) and not low.endswith(".enabled")

    by_last: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for p in trading_paths:
        if is_focus(p):
            by_last[p.split(".")[-1]]["trading"].append(p)
    for p in domains_paths:
        if is_focus(p):
            by_last[p.split(".")[-1]]["domains"].append(p)

    duplicates: list[tuple[str, list[str], list[str]]] = []
    for leaf, buckets in sorted(by_last.items()):
        if "trading" in buckets and "domains" in buckets:
            duplicates.append((leaf, sorted(buckets["trading"]), sorted(buckets["domains"])))

    atlas_keys = _pick_critical_keys(usage.keys())

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# CONFIG_MAP (Aurora)\n\n")
    lines.append(
        "Generated by `tools/generate_config_map.py` using:\n"
        "- `apps/reference/config_models.py` (Pydantic schema)\n"
        "- `config/aurora/*.yaml` (+ `config/aurora/strategies/*.yaml`)\n"
        "- `apps/reference/**` (AST usage scan)\n\n"
    )

    lines.append("## 1) The Dead List (Candidates for Deletion)\n\n")
    lines.append(
        f"- Active config leaf keys with 0 code references: **{len(active_dead)}**\n"
        f"- YAML leaf keys with 0 code references: **{len(yaml_dead)}**\n\n"
        "Notes:\n"
        "- Paths under `Dict[str, Any]` namespaces (e.g. `trading.risk`, `trading.tca_prefs`) are treated as dynamic and not expanded.\n"
        "- ‘0 references’ is based on static AST extraction of attribute access and string-key subscripts; dynamic access patterns may not be detected.\n\n"
    )

    lines.append("### [DEAD] Active Keys (Effective Config)\n\n")
    if not active_dead:
        lines.append("(none)\n\n")
    else:
        for p in active_dead:
            srcs = ", ".join(sorted(sources_by_path.get(p, {"<default/derived>"})))
            lines.append(f"- `[DEAD]` `{p}` (defined in: {srcs})\n")
        lines.append("\n")

    lines.append("### [DEAD] YAML Keys\n\n")
    if not yaml_dead:
        lines.append("(none)\n\n")
    else:
        for p in yaml_dead:
            srcs = ", ".join(sorted(sources_by_path.get(p, set())))
            lines.append(f"- `[DEAD]` `{p}` (defined in: {srcs})\n")
        lines.append("\n")

    lines.append("## 2) The Duplicate List (Conflict Zones)\n\n")
    lines.append(
        "Semantic duplicates are detected by matching leaf key names across `trading.yaml` and `domains.yaml` within a focus token set.\n"
        "This is intended to spotlight shadow configs after refactors.\n\n"
    )
    if not duplicates:
        lines.append("(none detected by heuristic)\n\n")
    else:
        for leaf, t_paths, d_paths in duplicates:
            lines.append(f"### `{leaf}`\n\n")
            lines.append("**Trading-side candidates**\n")
            for p in t_paths:
                used = "USED" if p in usage else "UNUSED"
                files = ", ".join(sorted(usage.get(p, Usage(set(), Counter())).files))
                lines.append(f"- `{p}` — **{used}**" + (f" (in: {files})" if files else "") + "\n")
            lines.append("\n**Domains-side candidates**\n")
            for p in d_paths:
                used = "USED" if p in usage else "UNUSED"
                files = ", ".join(sorted(usage.get(p, Usage(set(), Counter())).files))
                lines.append(f"- `{p}` — **{used}**" + (f" (in: {files})" if files else "") + "\n")
            lines.append("\n")

    lines.append("## 3) Active Configuration Atlas\n\n")
    lines.append("| Config Key | Defined In | Used In Module(s) | Logic/Formula Role |\n")
    lines.append("| :--- | :--- | :--- | :--- |\n")
    for key in atlas_keys:
        srcs = ", ".join(sorted(sources_by_path.get(key, {"<default/derived>"})))
        used_in = usage.get(key)
        modules = ", ".join(sorted(used_in.files)) if used_in else ""
        role = _role_summary(used_in.roles) if used_in else ""
        lines.append(f"| `{key}` | {srcs} | {modules} | {role} |\n")
    lines.append("\n")

    lines.append("## Schema vs YAML Reconciliation\n\n")
    lines.append("### Loader Migrations / Structure Drift (By Design)\n\n")
    lines.append(
        "The loader performs explicit migrations before Pydantic validation:\n"
        "- `system.yaml` root meta keys (e.g. `sequential_tests`, `risk_core`, `kelly`, …) are moved under `system_meta.*`.\n"
        "- `regime.yaml:config_version` is moved to `system_meta.regime_config_version`.\n"
        "- `regime.yaml:hotreload_whitelist` stays at root and is also copied into `system_meta.hotreload_whitelist`.\n"
        "- `domains.yaml` is loaded under `domains.*` (entire file is namespaced).\n"
        "- `strategies.yaml` is loaded under `strategies_registry.*`.\n"
        "- `strategies/<id>.yaml` is loaded under `strategies.<id>.*` (with optional top-level `<id>` wrapper).\n\n"
    )

    lines.append("### YAML Keys Not Representable by Schema (Unloadable Data)\n\n")
    if not yaml_unloadable:
        lines.append("(none detected after normalization)\n\n")
    else:
        for f, bad in sorted(yaml_unloadable.items()):
            lines.append(f"- `{f}`: {len(bad)} key(s)\n")
            for p in bad[:80]:
                lines.append(f"  - `{p}`\n")
            if len(bad) > 80:
                lines.append(f"  - … and {len(bad) - 80} more\n")
        lines.append("\n")

    # Schema keys missing in YAML (defaults/derived) — only for *effective* leaf keys.
    missing_in_yaml = sorted(
        [
            p
            for p in active_paths
            if schema.is_schema_path(p)
            and not is_under_open(p)
            and p not in normalized_yaml_paths
        ]
    )
    lines.append("### Schema Keys Missing in YAML (Defaults / Derived)\n\n")
    lines.append(
        f"Effective leaf keys present at runtime but not sourced from YAML: **{len(missing_in_yaml)}**\n\n"
    )
    if missing_in_yaml:
        for p in missing_in_yaml:
            used = "USED" if p in usage else "UNUSED"
            lines.append(f"- `[DEFAULT/DERIVED]` `{p}` — **{used}**\n")
        lines.append("\n")

    lines.append("### Code → Schema Drift (Potential Runtime Crashes)\n\n")
    if not drift:
        lines.append("(none detected)\n")
    else:
        lines.append(
            "These config paths are referenced in code but do not exist in `apps/reference/config_models.py`.\n"
            "If the referenced module is executed, this is likely an `AttributeError` / fail-closed crash.\n\n"
        )
        for p in drift:
            files = ", ".join(sorted(usage[p].files))
            lines.append(f"- `{p}` (in: {files})\n")

    OUT_MD.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_MD}")
    print(f"Dead(active)={len(active_dead)} Dead(yaml)={len(yaml_dead)} Duplicates={len(duplicates)} Drift={len(drift)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
