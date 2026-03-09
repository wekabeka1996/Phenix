#!/usr/bin/env python3
"""
Generate a trading configuration audit report.

Output: reports/config_audit_trading.md

This script is intentionally "best-effort":
- It derives the canonical config paths from Pydantic schema (apps/reference/config_models.py).
- It scans code (AST) to find where those paths are read (file + function/method).
- For dynamic Dict[str, Any] blocks (not fully typed in schema), it performs a small
  local dataflow to extract constant key usage (e.g., trading.risk.daily.enabled).

If something cannot be proven from code or schema, the report uses "NOT FOUND".
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, get_args, get_origin, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from pydantic import BaseModel  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Basic schema helpers (adapted from tools/generate_config_map.py)
# ──────────────────────────────────────────────────────────────────────────────


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
    from typing import Any as TypingAny

    return tp is TypingAny


def _is_basemodel(tp: Any) -> bool:
    try:
        return isinstance(tp, type) and issubclass(tp, BaseModel)
    except Exception:
        return False


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


def _qualname_from_stack(stack: list[str]) -> str:
    if not stack:
        return "<module>"
    return ".".join(stack)


# ──────────────────────────────────────────────────────────────────────────────
# Report data models
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldRow:
    path: str
    type_str: str
    default_str: str
    effect: str


@dataclass(frozen=True)
class UsageOcc:
    file: str
    qualname: str
    lineno: int


# ──────────────────────────────────────────────────────────────────────────────
# Schema index (needed for type-aware usage scan)
# ──────────────────────────────────────────────────────────────────────────────


class SchemaIndex:
    def __init__(self, root_model: type[BaseModel], *, globalns: dict[str, Any] | None = None):
        import typing

        self.model_prefixes: dict[type[BaseModel], set[str]] = defaultdict(set)
        self._visited: set[tuple[Any, str]] = set()
        self._typing = typing
        self._globalns = globalns or {}
        self._hints_cache: dict[type[BaseModel], dict[str, Any]] = {}
        self._walk(root_model, "")

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
                child_prefix = f"{prefix}.{field_name}" if prefix else field_name
                ann = self._hints_cache[model].get(field_name, field.annotation)
                self._walk(ann, child_prefix)
            return

        origin = get_origin(tp)
        if origin is dict:
            args = get_args(tp) or (Any, Any)
            v_t = _unwrap_optional(args[1])
            if _is_any(v_t):
                return
            if _is_basemodel(v_t):
                self._walk(v_t, f"{prefix}.*" if prefix else "*")
            return

        if origin is list:
            args = get_args(tp) or (Any,)
            it = _unwrap_optional(args[0])
            if _is_basemodel(it):
                self._walk(it, f"{prefix}.[*]" if prefix else "[*]")
            return

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


# ──────────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────────────────


def _first_sentence(text: str) -> str:
    s = " ".join(text.strip().split())
    if not s:
        return ""
    m = re.search(r"^(.{1,240}?)(?:\\.|$)", s)
    return (m.group(1) + ".") if m else (s[:240] + "…")


def _fmt_type(tp: Any) -> str:
    origin = get_origin(tp)
    if origin is None:
        if isinstance(tp, type):
            return tp.__name__
        return str(tp).replace("typing.", "")

    # Optional[T]
    if origin is getattr(__import__("typing"), "Union") and any(a is type(None) for a in get_args(tp)):
        args = [a for a in get_args(tp) if a is not type(None)]
        inner = args[0] if len(args) == 1 else args
        return f"Optional[{_fmt_type(inner)}]"

    if origin is list:
        args = get_args(tp) or (Any,)
        return f"List[{_fmt_type(args[0])}]"
    if origin is dict:
        args = get_args(tp) or (Any, Any)
        return f"Dict[{_fmt_type(args[0])}, {_fmt_type(args[1])}]"
    if str(origin).endswith("Literal"):
        args = get_args(tp)
        vals = ", ".join(repr(a) for a in args[:10])
        more = "" if len(args) <= 10 else f", …+{len(args) - 10}"
        return f"Literal[{vals}{more}]"

    # Fallback
    return str(tp).replace("typing.", "")


def _fmt_default(field) -> str:
    try:
        if field.is_required():
            return "required"
    except Exception:
        pass

    default = getattr(field, "default", None)
    default_factory = getattr(field, "default_factory", None)
    if default_factory is not None:
        return f"default_factory={getattr(default_factory, '__name__', repr(default_factory))}"
    if default is None:
        return "None"
    try:
        s = repr(default)
    except Exception:
        s = str(default)
    if len(s) > 120:
        return s[:117] + "…"
    return s


def _display_path(path: str) -> str:
    """Convert wildcard paths to human-friendly placeholders."""
    segs = path.split(".")
    out: list[str] = []
    for i, seg in enumerate(segs):
        if seg != "*":
            out.append(seg)
            continue
        prev = segs[i - 1] if i > 0 else ""
        placeholder = {
            "assets": "<SYMBOL>",
            "instruments": "<SYMBOL>",
            "assignments": "<SYMBOL>",
            "leverage_defaults": "<SYMBOL>",
            "ttl_by_tf_sec": "<TF_SEC>",
            "regime_thresholds": "<REGIME>",
            "regime_threshold_multipliers": "<REGIME>",
            "regime_sizing": "<REGIME>",
            "sl_mult": "<REGIME>",
            "tp_mult": "<REGIME>",
            "sl_k_atr": "<REGIME>",
            "rr_by_regime": "<REGIME>",
            "regime_multipliers": "<REGIME>",
            "feature_neutrals": "<FEATURE>",
            "weights": "<FEATURE>",
            "signal_weights": "<FEATURE>",
            "score_weights": "<FEATURE>",
            "risk_score_weights": "<FEATURE>",
            "priority": "<STRATEGY_ID>",
            "degraded_context_critical_keys_by_strategy": "<STRATEGY_ID>",
        }.get(prev, "<KEY>")
        out.append(placeholder)
    return ".".join(out)


def _risk_sentence(path: str) -> str:
    low = path.lower()
    if "trading_mode" in low or low.endswith(".trading_mode") or low == "trading_mode":
        return "Wrong mode can accidentally place live orders or invalidate backtest comparability."
    if "leverage" in low:
        return "Too high leverage increases liquidation/exposure risk; too low can underuse capital and reduce returns."
    if "margin_pct" in low or "exposure" in low:
        return "Loose limits can blow exposure/drawdown; overly tight limits can block most trades."
    if "slippage" in low or "tca" in low:
        return "Too tight limits can reject trades; too loose can allow bad fills and degrade PnL."
    if "fee" in low or "commission" in low:
        return "Mis-modeled costs can make backtests non-transferable and distort sizing/TP/SL."
    if "cooldown" in low or "holding_period" in low:
        return "Too small values can cause churn/fee drag; too large values can miss reversals and reduce trade count."
    if "ttl" in low or "timeout" in low or "watchdog" in low:
        return "Too short can cause premature cancels/false timeouts; too long can leave stale orders/locks."
    if "threshold" in low or "cutoff" in low or "min_" in low or "max_" in low:
        return "Too strict can suppress trades; too lax can overtrade and increase drawdowns/fees."
    if ".enabled" in low:
        return "Disabling can remove safety gates; enabling with bad params can block good trades."
    if "post_only" in low or "maker_only" in low or "gtx" in low or "tif" in low:
        return "Forcing maker can reduce fees but increase missed fills; allowing taker can improve fills but raise costs."
    return "Misconfiguration can change behavior subtly; validate with config_hash + config snapshot in reports."


# ──────────────────────────────────────────────────────────────────────────────
# Schema traversal to build field list
# ──────────────────────────────────────────────────────────────────────────────


def iter_schema_leaf_fields(root_model: type[BaseModel], *, globalns: dict[str, Any]) -> list[FieldRow]:
    import typing

    rows: list[FieldRow] = []
    hints_cache: dict[type[BaseModel], dict[str, Any]] = {}

    exclude_top = {"observability", "system_meta"}

    def walk(model: type[BaseModel], prefix: str) -> None:
        if model not in hints_cache:
            try:
                hints_cache[model] = typing.get_type_hints(
                    model, globalns=globalns, localns=globalns, include_extras=True
                )
            except Exception:
                hints_cache[model] = {}

        for field_name, field in model.model_fields.items():
            if prefix == "" and field_name in exclude_top:
                continue

            path = f"{prefix}.{field_name}" if prefix else field_name
            ann = hints_cache[model].get(field_name, field.annotation)
            ann_u = _unwrap_optional(ann)
            origin = get_origin(ann_u)

            desc = getattr(field, "description", None) or ""
            effect = _first_sentence(desc) if desc else "NOT FOUND"

            # Nested model
            if _is_basemodel(ann_u) and ann_u is not BaseModel:
                walk(ann_u, path)
                continue

            # Dict handling
            if origin is dict:
                args = get_args(ann_u) or (Any, Any)
                v_t = _unwrap_optional(args[1])
                # Open dict (Dict[str, Any]) – leaf container only
                if _is_any(v_t):
                    rows.append(
                        FieldRow(
                            path=path,
                            type_str=_fmt_type(ann),
                            default_str=_fmt_default(field),
                            effect=effect,
                        )
                    )
                    continue

                # Dict[str, BaseModel] – recurse with wildcard key
                if _is_basemodel(v_t) and v_t is not BaseModel:
                    walk(v_t, f"{path}.*")
                    continue

                # Dict[str, scalar] – record container (keys are runtime-defined)
                rows.append(
                    FieldRow(
                        path=path,
                        type_str=_fmt_type(ann),
                        default_str=_fmt_default(field),
                        effect=effect,
                    )
                )
                continue

            # List handling
            if origin is list:
                rows.append(
                    FieldRow(
                        path=path,
                        type_str=_fmt_type(ann),
                        default_str=_fmt_default(field),
                        effect=effect,
                    )
                )
                continue

            # Scalar leaf
            rows.append(
                FieldRow(
                    path=path,
                    type_str=_fmt_type(ann),
                    default_str=_fmt_default(field),
                    effect=effect,
                )
            )

    walk(root_model, "")
    # De-dup (some models appear in multiple prefixes)
    uniq: dict[str, FieldRow] = {}
    for r in rows:
        uniq.setdefault(r.path, r)
    return [uniq[k] for k in sorted(uniq.keys())]


# ──────────────────────────────────────────────────────────────────────────────
# Code usage scanning (typed config access + dynamic dict key extraction)
# ──────────────────────────────────────────────────────────────────────────────


def scan_config_usage(*, schema_paths: set[str], roots: list[Path]) -> dict[str, list[UsageOcc]]:
    raise NotImplementedError("scan_config_usage replaced by scan_usage_detailed()")


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


def scan_usage_detailed(
    schema: SchemaIndex,
    *,
    model_module: Any,
    roots: list[Path],
) -> dict[str, list[UsageOcc]]:
    """
    AST usage scan with type inference (based on tools/generate_config_map.py),
    but returns file+function contexts and also records dict usage via `.get()`.
    """

    model_classes: dict[str, type[BaseModel]] = {
        name: obj for name, obj in vars(model_module).items() if _is_basemodel(obj) and obj is not BaseModel
    }
    field_name_to_models: dict[str, list[type[BaseModel]]] = defaultdict(list)
    for m in model_classes.values():
        try:
            for fname in m.model_fields.keys():
                field_name_to_models[str(fname)].append(m)
        except Exception:
            continue

    # DomainConfigResolver getter return types
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

    # Invert schema model prefixes to infer types from attribute paths
    prefix_to_models: dict[str, set[type[BaseModel]]] = defaultdict(set)
    for model_t, prefixes in schema.model_prefixes.items():
        for pref in prefixes:
            # Include empty prefix ("") so we can infer AuroraConfig itself for self.config / cfg roots.
            prefix_to_models[pref].add(model_t)

    def model_from_annotation(ann_last: str | None) -> type[BaseModel] | None:
        if ann_last and ann_last in model_classes:
            return model_classes[ann_last]
        return None

    def infer_model_from_value(
        local_types: dict[str, type[BaseModel]],
        self_attr_types: dict[str, type[BaseModel]],
        value: ast.AST,
    ) -> type[BaseModel] | None:
        # Case 0: simple alias (x = typed_var)
        if isinstance(value, ast.Name) and value.id in local_types:
            return local_types[value.id]

        # Case 1: call to DomainConfigResolver getter
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
            inferred = resolver_return_types.get(value.func.attr)
            if inferred is not None:
                return inferred

        # Case 1b: getattr(<typed_model_expr>, "field_name", <default?>)
        # Common pattern in this repo for back-compat optional blocks:
        #   ep_cfg = getattr(self.config.domains.decision_making, "entry_plan", None)
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "getattr"
            and len(value.args) >= 2
        ):
            base_expr = value.args[0]
            field_expr = value.args[1]
            if isinstance(field_expr, ast.Constant) and isinstance(field_expr.value, str):
                field_name = field_expr.value

                base_model: type[BaseModel] | None = None
                if isinstance(base_expr, ast.Name) and base_expr.id in local_types:
                    base_model = local_types[base_expr.id]
                elif isinstance(base_expr, ast.Attribute):
                    base_model = infer_model_from_value(local_types, self_attr_types, base_expr)

                if base_model is not None:
                    fld = base_model.model_fields.get(field_name)
                    if fld is not None:
                        ann = _unwrap_optional(fld.annotation)
                        if _is_basemodel(ann) and ann is not BaseModel:
                            return ann

        # Case 2: attribute chain rooted at a typed base and pointing to a known model prefix
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

            # Heuristic: self.config is usually AuroraConfig (esp. subclasses)
            if len(chain) >= 2 and chain[0] == "self" and chain[1] == "config":
                base_model = model_module.AuroraConfig
                rel = ".".join(chain[2:])
                for full in schema.combine_prefix(base_model, rel):
                    candidates |= prefix_to_models.get(full, set())

            if len(candidates) == 1:
                return next(iter(candidates))
        return None

    usages: dict[str, list[UsageOcc]] = defaultdict(list)

    def record(path: str, file_rel: str, qualname: str, lineno: int) -> None:
        if not path:
            return
        usages[path].append(UsageOcc(file=file_rel, qualname=qualname, lineno=lineno))

    skip_terminal = {
        "model_dump",
        "model_copy",
        "model_validate",
        "model_construct",
        "copy",
        "dict",
    }
    dict_terminals = {"get", "keys", "items", "values", "pop", "setdefault"}

    def scan_function(
        fn: ast.AST,
        *,
        file_rel: str,
        qualname: str,
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

        # Record attribute/subscript usage in this function scope
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and not _is_intermediate_attr(node, parents):
                chain = _expr_chain(node)
                if not chain:
                    continue

                # Handle dict terminals: record base path (without `.get`, etc)
                terminal = chain[-1]
                if terminal in dict_terminals and len(chain) >= 2:
                    chain = chain[:-1]
                    terminal = chain[-1]

                # Skip non-config terminals
                if terminal in skip_terminal:
                    continue

                lineno = getattr(node, "lineno", 0) or 0

                # Local var root
                root = chain[0]
                if root in local_types:
                    model = local_types[root]
                    rel = ".".join(chain[1:])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, qualname, lineno)
                    continue

                # self.<attr> root
                if len(chain) >= 2 and chain[0] == "self" and chain[1] in self_attr_types:
                    model = self_attr_types[chain[1]]
                    rel = ".".join(chain[2:])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, qualname, lineno)
                    continue

                # Heuristic: self.config
                if len(chain) >= 2 and chain[0] == "self" and chain[1] == "config":
                    model = model_module.AuroraConfig
                    rel = ".".join(chain[2:])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, qualname, lineno)

            if isinstance(node, ast.Subscript):
                base = _expr_chain(node.value)
                if not base:
                    continue
                if not (isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
                    continue
                key = node.slice.value
                lineno = getattr(node, "lineno", 0) or 0

                if base[0] in local_types:
                    model = local_types[base[0]]
                    rel = ".".join(base[1:] + [key])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, qualname, lineno)
                    continue

                if len(base) >= 2 and base[0] == "self" and base[1] in self_attr_types:
                    model = self_attr_types[base[1]]
                    rel = ".".join(base[2:] + [key])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, qualname, lineno)
                    continue

                if len(base) >= 2 and base[0] == "self" and base[1] == "config":
                    model = model_module.AuroraConfig
                    rel = ".".join(base[2:] + [key])
                    for full in schema.combine_prefix(model, rel):
                        record(full, file_rel, qualname, lineno)

            # DecisionMaking helper: _get_strict(<cfg_obj>, "leaf_key", ...)
            # This is an important dynamic access pattern for TCA/RiskBudgets.
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args:
                if node.func.id == "_get_strict" and len(node.args) >= 2:
                    a0 = node.args[0]
                    a1 = node.args[1]
                    if isinstance(a1, ast.Constant) and isinstance(a1.value, str):
                        leaf_key = a1.value
                        lineno = getattr(node, "lineno", 0) or 0

                        model: type[BaseModel] | None = None
                        if isinstance(a0, ast.Name) and a0.id in local_types:
                            model = local_types[a0.id]
                        elif isinstance(a0, ast.Attribute):
                            chain0 = _expr_chain(a0)
                            if chain0 and len(chain0) >= 2 and chain0[0] == "self" and chain0[1] in self_attr_types:
                                model = self_attr_types[chain0[1]]
                            elif chain0 and len(chain0) >= 2 and chain0[0] == "self" and chain0[1] == "config":
                                model = model_module.AuroraConfig

                        if model is not None:
                            for full in schema.combine_prefix(model, leaf_key):
                                record(full, file_rel, qualname, lineno)

                # getattr(<cfg_obj>, "leaf_key", default)
                if node.func.id == "getattr" and len(node.args) >= 2:
                    a0 = node.args[0]
                    a1 = node.args[1]
                    if isinstance(a1, ast.Constant) and isinstance(a1.value, str):
                        leaf_key = a1.value
                        lineno = getattr(node, "lineno", 0) or 0

                        model: type[BaseModel] | None = None
                        if isinstance(a0, ast.Name) and a0.id in local_types:
                            model = local_types[a0.id]
                        elif isinstance(a0, ast.Attribute):
                            model = infer_model_from_value(local_types, self_attr_types, a0)

                        # If we can't infer the base type, attempt a schema-unique field-name match.
                        # This is safe only when exactly one model declares this field name.
                        if model is None:
                            cands = field_name_to_models.get(leaf_key, [])
                            if len(cands) == 1:
                                model = cands[0]

                        if model is not None:
                            for full in schema.combine_prefix(model, leaf_key):
                                record(full, file_rel, qualname, lineno)

    # Precompute class-level self attribute types (from __init__ scopes)
    class_self_attrs: dict[str, dict[str, type[BaseModel]]] = {}

    for root in roots:
        for pf in root.rglob("*.py"):
            if pf.name == "config_models.py":
                continue
            try:
                src = pf.read_text(encoding="utf-8", errors="replace")
                module_tree = ast.parse(src, filename=str(pf))
            except SyntaxError:
                continue

            file_rel = str(pf.relative_to(REPO_ROOT))

            for node in module_tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue

                init_fn = next(
                    (n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
                    None,
                )
                if init_fn is not None:
                    inferred_self: dict[str, type[BaseModel]] = {}
                    init_local_types: dict[str, type[BaseModel]] = {}
                    for arg in init_fn.args.args + init_fn.args.kwonlyargs:
                        model = model_from_annotation(_annotation_last(arg.annotation))
                        if model is not None:
                            init_local_types[arg.arg] = model

                    # Small fixed-point inference for __init__ to capture self.* types
                    for _ in range(2):
                        before = (len(init_local_types), len(inferred_self))
                        for sub in ast.walk(init_fn):
                            if isinstance(sub, ast.Assign):
                                inferred = infer_model_from_value(init_local_types, inferred_self, sub.value)
                                if inferred is None:
                                    continue
                                for tgt in sub.targets:
                                    if isinstance(tgt, ast.Name):
                                        init_local_types[tgt.id] = inferred
                                    elif (
                                        isinstance(tgt, ast.Attribute)
                                        and isinstance(tgt.value, ast.Name)
                                        and tgt.value.id == "self"
                                    ):
                                        inferred_self[tgt.attr] = inferred
                            elif isinstance(sub, ast.AnnAssign) and sub.value is not None:
                                inferred = infer_model_from_value(init_local_types, inferred_self, sub.value)
                                if inferred is None:
                                    continue
                                tgt = sub.target
                                if isinstance(tgt, ast.Name):
                                    init_local_types[tgt.id] = inferred
                                elif (
                                    isinstance(tgt, ast.Attribute)
                                    and isinstance(tgt.value, ast.Name)
                                    and tgt.value.id == "self"
                                ):
                                    inferred_self[tgt.attr] = inferred
                        after = (len(init_local_types), len(inferred_self))
                        if after == before:
                            break
                    class_self_attrs[f"{file_rel}:{node.name}"] = inferred_self

                # Scan methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        scan_function(
                            item,
                            file_rel=file_rel,
                            qualname=f"{node.name}.{item.name}",
                            self_attrs=class_self_attrs.get(f"{file_rel}:{node.name}"),
                        )

            # Module-level functions
            for node in module_tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scan_function(node, file_rel=file_rel, qualname=node.name, self_attrs=None)

            # Note: module-level statements are not scanned here; most config reads are in functions/methods.

    # De-dup occurrences per path (file+qualname)
    out: dict[str, list[UsageOcc]] = {}
    for path, occs in usages.items():
        seen: set[tuple[str, str]] = set()
        uniq: list[UsageOcc] = []
        for o in sorted(occs, key=lambda x: (x.file, x.qualname, x.lineno)):
            k = (o.file, o.qualname)
            if k in seen:
                continue
            seen.add(k)
            uniq.append(o)
        out[path] = uniq
    return out


def scan_dynamic_dict_usage(
    *,
    roots: list[Path],
    dynamic_roots: set[str],
) -> dict[str, list[UsageOcc]]:
    """Extract constant-key usage under dynamic dict roots (e.g., trading.risk.*)."""

    out: dict[str, list[UsageOcc]] = defaultdict(list)

    def record(path: str, file_rel: str, qualname: str, lineno: int) -> None:
        out[path].append(UsageOcc(file=file_rel, qualname=qualname, lineno=lineno))

    def scan_function_body(body: list[ast.stmt], *, file_rel: str, qualname: str) -> None:
        # var -> canonical dict path (e.g. trading.risk.daily)
        alias: dict[str, str] = {}

        mod = ast.Module(body=body, type_ignores=[])  # type: ignore[arg-type]

        def _derived_alias(expr: ast.AST) -> str | None:
            # var["k"]
            if isinstance(expr, ast.Subscript) and isinstance(expr.value, ast.Name):
                base = expr.value.id
                if base in alias and isinstance(expr.slice, ast.Constant) and isinstance(expr.slice.value, str):
                    return f"{alias[base]}.{expr.slice.value}"

            # var.get("k")
            if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
                if (
                    isinstance(expr.func.value, ast.Name)
                    and expr.func.attr == "get"
                    and expr.args
                    and isinstance(expr.args[0], ast.Constant)
                    and isinstance(expr.args[0].value, str)
                ):
                    base = expr.func.value.id
                    if base in alias:
                        return f"{alias[base]}.{expr.args[0].value}"

            # a if cond else b  -> try body first
            if isinstance(expr, ast.IfExp):
                return _derived_alias(expr.body) or _derived_alias(expr.orelse)

            # x or y -> try each side
            if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.Or):
                for v in expr.values:
                    got = _derived_alias(v)
                    if got:
                        return got

            return None

        # Pass 1: seed aliases from assignments (fixed-point; order-independent)
        for _ in range(3):
            before = len(alias)
            for node in ast.walk(mod):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                tgt = node.targets[0]
                if not isinstance(tgt, ast.Name):
                    continue
                name = tgt.id

                chain = _expr_chain(node.value) if isinstance(node.value, ast.AST) else None
                if chain:
                    for i in range(len(chain)):
                        cand = ".".join(chain[i:])
                        if cand in dynamic_roots:
                            alias[name] = cand
                            break

                # var2 = var1["k"] / var1.get("k") / (var1["k"] if … else …) / (var1.get("k") or …)
                derived = _derived_alias(node.value) if isinstance(node.value, ast.AST) else None
                if derived is not None:
                    alias[name] = derived

            if len(alias) == before:
                break

        # Pass 2: record constant key reads
        for node in ast.walk(mod):
            lineno = getattr(node, "lineno", 0) or 0

            # alias["k"]
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                base = node.value.id
                if base in alias and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    record(f"{alias[base]}.{node.slice.value}", file_rel, qualname, lineno)

            # alias.get("k")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if (
                    node.func.attr == "get"
                    and isinstance(node.func.value, ast.Name)
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    base = node.func.value.id
                    if base in alias:
                        record(f"{alias[base]}.{node.args[0].value}", file_rel, qualname, lineno)

    for root in roots:
        for pf in root.rglob("*.py"):
            try:
                src = pf.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(src, filename=str(pf))
            except SyntaxError:
                continue

            file_rel = str(pf.relative_to(REPO_ROOT))

            class Visitor(ast.NodeVisitor):
                def __init__(self) -> None:
                    self.class_stack: list[str] = []

                def visit_ClassDef(self, node: ast.ClassDef) -> None:
                    self.class_stack.append(node.name)
                    self.generic_visit(node)
                    self.class_stack.pop()

                def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                    qn = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
                    scan_function_body(node.body, file_rel=file_rel, qualname=qn)
                    self.generic_visit(node)

                def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                    qn = ".".join([*self.class_stack, node.name]) if self.class_stack else node.name
                    scan_function_body(node.body, file_rel=file_rel, qualname=qn)
                    self.generic_visit(node)

            Visitor().visit(tree)

    # De-dup (file+qualname)
    deduped: dict[str, list[UsageOcc]] = {}
    for path, occs in out.items():
        seen: set[tuple[str, str]] = set()
        uniq: list[UsageOcc] = []
        for o in sorted(occs, key=lambda x: (x.file, x.qualname, x.lineno)):
            k = (o.file, o.qualname)
            if k in seen:
                continue
            seen.add(k)
            uniq.append(o)
        deduped[path] = uniq
    return deduped


# ──────────────────────────────────────────────────────────────────────────────
# Report generation
# ──────────────────────────────────────────────────────────────────────────────


def _category(path: str) -> str:
    low = path.lower()

    # Exit
    if ".exit." in low or ".take_profit." in low or ".trailing_stop." in low or low.startswith("trailing."):
        return "Exit/TP/SL"

    # Cooldown / re-entry / churn control
    if (
        "cooldown" in low
        or "holding_period" in low
        or "retry" in low
        or ".qos." in low
        or "pending_entry_ttl" in low
        or "anti_race" in low
    ):
        return "Cooldown/Re-entry"

    # Costs / fill realism
    if (
        "slippage" in low
        or "tca" in low
        or "fee" in low
        or "commission" in low
        or "maker_preference" in low
        or "trade_through" in low
        or "volume_participation" in low
        or "fill_probability_at_touch" in low
    ):
        return "Costs/Fill realism"

    # Backtest
    if low.startswith("trading.backtest") or "backtest" in low:
        return "Backtest plumbing"

    # Entry execution
    if (
        ".execution." in low
        or "order_" in low
        or ".orders." in low
        or ".order_params." in low
        or "tif" in low
        or "post_only" in low
        or "maker_only" in low
    ):
        return "Entry execution"

    # Regime (explicit)
    if low.startswith("basis_tf_sec") or low.startswith("uncertain_cutoff") or low.startswith("liveness_factor") or low.startswith("models."):
        return "Regime"
    if "regime" in low and "tpsl" not in low and ".exit." not in low and ".take_profit." not in low:
        return "Regime"

    # Sizing/Risk
    if (
        "leverage" in low
        or "margin" in low
        or "position_sizing" in low
        or "exposure" in low
        or "drawdown" in low
        or "cvar" in low
        or low.startswith("domains.risk_management")
        or low.startswith("trading.risk_budgets")
        or low.startswith("trading.risk")
    ):
        return "Sizing/Risk"

    return "Signal/Decision"


def _render_usage(usages: list[UsageOcc] | None) -> str:
    if not usages:
        return "NOT FOUND"
    parts: list[str] = []
    for u in usages:
        parts.append(f"`{u.file}:{u.qualname}`")
    # Limit width in markdown: show first N if too many
    if len(parts) > 6:
        return ", ".join(parts[:6]) + f", … (+{len(parts) - 6} more)"
    return ", ".join(parts)


def main() -> int:
    from apps.reference import config_models as config_models_module

    out_path = REPO_ROOT / "reports" / "config_audit_trading.md"

    # 1) Schema-derived field list (filtered later by top-level prefixes)
    all_fields = iter_schema_leaf_fields(config_models_module.AuroraConfig, globalns=vars(config_models_module))

    include_prefixes = (
        "trading_mode",
        "trading.",
        "domains.",
        "instruments.",
        "strategies_registry.",
        "strategies.",
        "basis_tf_sec",
        "uncertain_cutoff",
        "liveness_factor",
        "models.",
        "execution.",
        "brackets.",
        "trailing.",
        "system.market_data.",
        "ops.",
        "account_observer.",
        "binance_api.",
    )

    fields: list[FieldRow] = [f for f in all_fields if f.path == "trading_mode" or f.path.startswith(include_prefixes)]

    # 2) Augment: expand dynamic Dict[str, Any] blocks we know affect trading (legacy but live).
    # Currently: trading.risk.* leaf keys from YAML (untyped in schema).
    try:
        import yaml

        raw = yaml.safe_load((REPO_ROOT / "config" / "aurora" / "trading.yaml").read_text(encoding="utf-8"))
        risk_block = (raw or {}).get("trading", {}).get("risk", {})

        def _flatten_yaml(obj: Any, prefix: str) -> dict[str, Any]:
            out: dict[str, Any] = {}
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = str(k)
                    p = f"{prefix}.{key}" if prefix else key
                    out.update(_flatten_yaml(v, p))
                return out
            if isinstance(obj, list):
                out[prefix] = obj
                return out
            out[prefix] = obj
            return out

        risk_leafs = _flatten_yaml(risk_block, "trading.risk") if isinstance(risk_block, dict) else {}

        def _infer_value_type(v: Any) -> str:
            if v is None:
                return "None"
            if isinstance(v, bool):
                return "bool"
            if isinstance(v, int) and not isinstance(v, bool):
                return "int"
            if isinstance(v, float):
                return "float"
            if isinstance(v, str):
                return "str"
            if isinstance(v, list):
                return "list"
            if isinstance(v, dict):
                return "dict"
            return type(v).__name__

        existing_paths = {f.path for f in fields}
        for p, v in sorted(risk_leafs.items()):
            if p in existing_paths:
                continue
            fields.append(
                FieldRow(
                    path=p,
                    type_str=_infer_value_type(v),
                    default_str="NOT FOUND (untyped dict)",
                    effect="NOT FOUND (untyped dict; see consumer code)",
                )
            )
    except Exception:
        # Best-effort: if YAML can't be parsed, skip expansion.
        pass

    # 2b) Backtest realism knobs (not YAML today; hardcoded defaults in MockBroker)
    # These are critical for PnL/WR realism in backtests.
    backtest_realism_fields = [
        FieldRow(
            path="backtest_engine.MockBroker.commission_maker",
            type_str="float",
            default_str="0.0002 (hardcoded default)",
            effect="Backtest: maker fee rate applied to fills.",
        ),
        FieldRow(
            path="backtest_engine.MockBroker.commission_taker",
            type_str="float",
            default_str="0.0004 (hardcoded default)",
            effect="Backtest: taker fee rate applied to fills.",
        ),
        FieldRow(
            path="backtest_engine.MockBroker.slippage_bps",
            type_str="float",
            default_str="2.0 (hardcoded default)",
            effect="Backtest: market/stop/TP slippage in basis points.",
        ),
        FieldRow(
            path="backtest_engine.MockBroker.fill_probability_at_touch",
            type_str="float",
            default_str="0.0 (hardcoded default)",
            effect="Backtest: probability to fill when price only touches limit (0 = trade-through only).",
        ),
        FieldRow(
            path="backtest_engine.MockBroker.max_volume_participation",
            type_str="float",
            default_str="0.05 (hardcoded default)",
            effect="Backtest: max fraction of bar volume a single order can take.",
        ),
    ]
    fields.extend(backtest_realism_fields)

    # 3) Scan code usage (typed config access + best-effort dict `.get()` usage)
    schema = SchemaIndex(config_models_module.AuroraConfig, globalns=vars(config_models_module))
    usage_map = scan_usage_detailed(
        schema,
        model_module=config_models_module,
        roots=[REPO_ROOT / "apps" / "reference", REPO_ROOT / "backtest_engine"],
    )
    # Dynamic dict: trading.risk.* (legacy but used)
    dyn_usage = scan_dynamic_dict_usage(
        roots=[REPO_ROOT / "apps" / "reference", REPO_ROOT / "backtest_engine"],
        dynamic_roots={"trading.risk"},
    )
    for p, occs in dyn_usage.items():
        usage_map.setdefault(p, [])
        usage_map[p].extend(occs)
    # Hardcode the "read" location for MockBroker realism knobs.
    for f in backtest_realism_fields:
        usage_map.setdefault(f.path, [])
        usage_map[f.path].append(
            UsageOcc(file="backtest_engine/mock_broker.py", qualname="MockBroker.__init__", lineno=0)
        )
    # Final de-dup after merge
    for p, occs in list(usage_map.items()):
        seen: set[tuple[str, str]] = set()
        uniq: list[UsageOcc] = []
        for o in sorted(occs, key=lambda x: (x.file, x.qualname, x.lineno)):
            k = (o.file, o.qualname)
            if k in seen:
                continue
            seen.add(k)
            uniq.append(o)
        usage_map[p] = uniq

    # 4) Group by categories
    by_cat: dict[str, list[FieldRow]] = defaultdict(list)
    for f in fields:
        by_cat[_category(f.path)].append(f)

    categories_order = [
        "Signal/Decision",
        "Regime",
        "Sizing/Risk",
        "Entry execution",
        "Exit/TP/SL",
        "Cooldown/Re-entry",
        "Costs/Fill realism",
        "Backtest plumbing",
    ]

    # 5) Render markdown
    lines: list[str] = []
    lines.append("# Trading Config Audit (Aurora + Mean Reversion)\n\n")
    lines.append(
        "Goal: create a **config impact map** (what реально впливає) and **where each field is read in code**.\n"
        "No guesses: if a consumer can’t be proven via static scan, it is marked **NOT FOUND**.\n\n"
    )
    lines.append("Generated: 2026-02-01\n\n")

    # 1) Config files table (manual, anchored to ConfigLoader behavior)
    lines.append("## 1) Конфіг-файли та їх роль (таблиця)\n\n")
    lines.append("| Файл | Хто лоадить | Merge / пріоритет | Секції, що впливають на торгову поведінку |\n")
    lines.append("| :--- | :--- | :--- | :--- |\n")
    lines.append(
        "| `config/aurora/system.yaml` | `apps/reference/config_loader.py:ConfigLoader.load_config()` | merged first at root; some keys extracted → `system_meta.*` | `trading_mode`, `system.market_data.*` (TTL/WS), `ops.panic_killswitch`, `trailing.*` |\n"
    )
    lines.append(
        "| `config/aurora/trading.yaml` | `apps/reference/config_loader.py:ConfigLoader.load_config()` | deep-merged after system.yaml; provides `trading.*` + `binance_api.*` | `trading.mode`, `trading.backtest.*`, `trading.tca_prefs.*`, `trading.risk_budgets.*`, `trading.execution.*`, `trading.risk.*` (legacy gates) |\n"
    )
    lines.append(
        "| `config/aurora/regime.yaml` | `apps/reference/config_loader.py:ConfigLoader.load_config()` | deep-merged after trading.yaml | `basis_tf_sec`, `uncertain_cutoff`, `liveness_factor`, `models.*` (regime detector) |\n"
    )
    lines.append(
        "| `config/aurora/domains.yaml` | `apps/reference/config_loader.py:ConfigLoader._merge_config_fragments()` | namespaced under `domains.*` (SSOT); trading.yaml domain mirrors forbidden | `domains.decision_making.*`, `domains.feature_engineering.*`, `domains.risk_management.*`, `domains.execution_position.*` |\n"
    )
    lines.append(
        "| `config/aurora/instruments.yaml` | `apps/reference/config_loader.py:ConfigLoader._merge_config_fragments()` | SSOT under `instruments.*`; trading.yaml mirror forbidden | per-symbol precision + execution/sizing SSOT: `instruments.<SYMBOL>.{tick_size,step_size,min_qty,min_notional,execution.*,sizing.*,flip.*}` |\n"
    )
    lines.append(
        "| `config/aurora/strategies.yaml` | `apps/reference/config_loader.py:ConfigLoader._merge_config_fragments()` | mandatory; loaded under `strategies_registry.*`; drives which profiles load | `strategies_registry.assignments` (activation), `strategies_registry.arbitration.*` (conflict resolution) |\n"
    )
    lines.append(
        "| `config/aurora/strategies/aurora.yaml` | loaded via registry in `ConfigLoader._merge_config_fragments()` | SSOT under `strategies.aurora.*` | signal policy (`decision.*`), per-symbol overrides (`assets.<SYMBOL>.*`), execution policy (`execution.*`), exits (`exit/take_profit/trailing_stop`) |\n"
    )
    lines.append(
        "| `config/aurora/strategies/mean_reversion.yaml` | loaded via registry in `ConfigLoader._merge_config_fragments()` | SSOT under `strategies.mean_reversion.*` | MR entry params (`strategy.*`), regime filters, per-asset overrides, execution policy |\n"
    )
    lines.append(
        "| `config/aurora/observability.yaml` | `ConfigLoader._load_observability()` | validated separately; defaults if missing | logging only (no trading behavior) |\n"
    )
    lines.append("\n")

    # 2) Impact map
    lines.append("## 2) “Impact Map” по категоріях\n\n")
    lines.append(
        "Format per field:\n"
        "- YAML path\n"
        "- type/default (Pydantic)\n"
        "- де читається в коді (file+function)\n"
        "- effect (1 sentence)\n"
        "- risk (1 sentence)\n\n"
    )

    for cat in categories_order:
        lines.append(f"### {cat}\n\n")
        items = by_cat.get(cat, [])
        if not items:
            lines.append("(none)\n\n")
            continue

        # Stable sort by path
        for f in sorted(items, key=lambda x: x.path):
            disp_path = _display_path(f.path)
            usages = usage_map.get(f.path)
            lines.append(f"- `{disp_path}`\n")
            lines.append(f"  - type/default: `{f.type_str}` / `{f.default_str}`\n")
            lines.append(f"  - read: {_render_usage(usages)}\n")
            lines.append(f"  - effect: {f.effect}\n")
            lines.append(f"  - risk: {_risk_sentence(disp_path)}\n")
        lines.append("\n")

    # 3) Silent behaviors (manual, high-signal list)
    lines.append("## 3) Конфіги, що “тіньово” впливають\n\n")
    lines.append("### Potential Silent Behavior\n\n")
    lines.append(
        "- `trading.symbols_to_track` is **derived** from `strategies_registry.assignments` in `ConfigLoader._derive_symbols_to_track_ssot()` (YAML value is forbidden in strict mode).\n"
        "- Backtest safety: if `trading.mode: backtest`, loader may force root `trading_mode=backtest` (see `ConfigLoader.load_config()` backtest sync block).\n"
        "- Root aliasing: `AuroraConfig._backcompat_root_execution_alias()` sets root `execution = trading.execution` when root is null.\n"
        "- Timeframe precedence: `ConfigLoader._apply_timeframe_sec_ssot_precedence()` can override `strategies.mean_reversion.timeframe_sec` using `strategies.aurora.assets.<SYMBOL>.timeframe_sec` overrides.\n"
        "- Liquidity gate precedence (explicit but easy to miss): per-asset → per-strategy → Aurora decision-level (see `LiquidityGateConfig` docstring).\n"
        "- `getattr(..., default)` fallbacks: `apps/reference/domains/decision_making/decision_making.py:DecisionMaking.__init__` uses `getattr(trading_config, 'tca_prefs', {})` / `risk_budgets` (silent empty dict if missing).\n"
        "- Null → default example: `backtest_engine/wrappers.py:BacktestExecPosFSM._on_order_fill` uses `float(getattr(exp_cfg, 'post_fill_hold_ttl_sec', ttl) or ttl)` (0/None collapses to default).\n"
        "- 0 → None example: `apps/reference/domains/decision_making/decision_making.py` does `int(tca_budget.get('max_slippage_bps', 0)) or None`.\n"
        "- Backtest realism defaults are **not** YAML-controlled today: `backtest_engine/mock_broker.py:MockBroker.__init__` defaults (commission/slippage/trade-through/volume cap) apply unless explicitly passed.\n"
    )
    lines.append("\n")

    # 4) Safe baselines
    lines.append("## 4) Мінімальний “safe baseline”\n\n")
    lines.append("Only fields found in code paths above (i.e., `read != NOT FOUND`).\n\n")

    def is_used(path: str) -> bool:
        return bool(usage_map.get(path))

    aurora_baseline = [
        "trading_mode",
        "strategies_registry.assignments",
        "strategies_registry.arbitration.mode",
        "strategies_registry.arbitration.window_ms",
        "strategies_registry.arbitration.priority",
        "instruments.*.tick_size",
        "instruments.*.step_size",
        "instruments.*.min_qty",
        "instruments.*.min_notional",
        "instruments.*.execution.margin_mode",
        "instruments.*.execution.target_leverage",
        "instruments.*.sizing.margin_pct",
        "strategies.aurora.enabled",
        "strategies.aurora.timeframe_sec",
        "strategies.aurora.execution.entry_order_type",
        "strategies.aurora.execution.entry_tif",
        "strategies.aurora.decision.signal_threshold",
        "strategies.aurora.decision.neutral_threshold",
        "strategies.aurora.decision.cooldown_sec",
        "strategies.aurora.assets.*.enabled",
        "strategies.aurora.assets.*.allowed_regimes",
        "strategies.aurora.assets.*.weights.obi",
        "strategies.aurora.assets.*.weights.tfi",
        "strategies.aurora.assets.*.weights.delta_price",
        "strategies.aurora.assets.*.weights.ema_bias",
        "strategies.aurora.assets.*.weights.volume_spike",
        "strategies.aurora.assets.*.weights.volatility_state",
        "strategies.aurora.assets.*.weights.depth_imbalance",
        "strategies.aurora.assets.*.weights.macro_resid",
        "strategies.aurora.assets.*.weights.macro_sync",
        "strategies.aurora.assets.*.exit.sl_pct",
        "strategies.aurora.assets.*.exit.regime_tpsl.enabled",
        "strategies.aurora.assets.*.exit.regime_tpsl.mode",
        "strategies.aurora.assets.*.exit.regime_tpsl.min_sl_pct",
        "strategies.aurora.assets.*.exit.regime_tpsl.max_sl_pct",
        "strategies.aurora.assets.*.exit.regime_tpsl.min_tp_rr",
        "strategies.aurora.assets.*.exit.regime_tpsl.max_tp_rr",
        "strategies.aurora.assets.*.exit.regime_tpsl.min_dist_bps",
        "strategies.aurora.assets.*.take_profit.tp_low_ratio",
        "strategies.aurora.assets.*.take_profit.tp_high_ratio",
        "strategies.aurora.assets.*.take_profit.partial_exit_pct",
    ]

    lines.append("### Aurora baseline\n\n")
    for p in aurora_baseline:
        if is_used(p):
            lines.append(f"- `{_display_path(p)}`\n")
    lines.append("\n")

    mr_baseline = [
        "strategies.mean_reversion.enabled",
        "strategies.mean_reversion.timeframe_sec",
        "strategies.mean_reversion.execution.entry_order_type",
        "strategies.mean_reversion.strategy.bb_window",
        "strategies.mean_reversion.strategy.bb_num_std",
        "strategies.mean_reversion.strategy.atr_window",
        "strategies.mean_reversion.strategy.entry_threshold",
        "strategies.mean_reversion.strategy.sl_atr_mult",
        "strategies.mean_reversion.strategy.tp_to_mid",
        "strategies.mean_reversion.strategy.cooldown_sec",
        "strategies.mean_reversion.regime_thresholds.high_vol_pct",
        "strategies.mean_reversion.regime_thresholds.low_vol_pct",
        "strategies.mean_reversion.allowed_regimes",
        "strategies.mean_reversion.assets.*.enabled",
        "strategies.mean_reversion.assets.*.allowed_regimes",
        "strategies.mean_reversion.regime_sizing.*.sizing_mult",
        "strategies.mean_reversion.regime_sizing.*.stop_mult",
        "strategies.mean_reversion.regime_sizing.*.target_mult",
    ]

    lines.append("### Mean Reversion baseline\n\n")
    for p in mr_baseline:
        if is_used(p):
            lines.append(f"- `{_display_path(p)}`\n")
    lines.append("\n")

    # Practical commands
    lines.append("## Як збирати (практичні команди)\n\n")
    lines.append("Ripgrep quick-start:\n\n")
    lines.append("```bash\n")
    lines.append("rg -n \"load_config|ConfigLoader|deep_merge|strategies_registry|assignments\" apps/reference backtest_engine\n")
    lines.append("rg -n \"Aurora.*Config|MeanReversion.*Config|BaseModel\" apps/reference/config_models.py\n")
    lines.append("rg -n \"fees|commission|slippage|trade_through|volume_cap\" apps/reference backtest_engine\n")
    lines.append("rg -n \"market_regime|RegimeDetector|basis_tf_sec|atr_baseline\" apps/reference config/aurora\n")
    lines.append("rg -n \"tp_rr|sl_pct|regime_tpsl|guardrails|cooldown|reentry|post_only|GTX|timeInForce|TIF\" apps/reference config/aurora\n")
    lines.append("```\n\n")

    lines.append("Pydantic field inventory (auto):\n\n")
    lines.append("```bash\n")
    lines.append("python3 tools/generate_trading_config_audit.py\n")
    lines.append("```\n\n")

    # What to do now
    lines.append("## Що робити прямо зараз (коротко)\n\n")
    lines.append(
        "- Use the existing backtest config snapshot + hash (see `backtest_engine/reporting.py:_extract_backtest_config_snapshot`) so **one run = one config_hash**.\n"
        "- Store `resolved_config` + per-file hashes (regime.yaml + strategy profile + instruments.yaml + strategies.yaml) in each report JSON/MD.\n"
        "- Then A/B becomes clean: change ONLY a LOW_VOL block (e.g., `regime_sizing`, thresholds, cooldown) and compare runs by `config_hash`.\n"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
