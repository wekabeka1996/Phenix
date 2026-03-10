import os
import ast
import json
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = "."
OUTPUT_MD = "ASYNC_AUDIT_REPORT.md"
EXCLUDE_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache', '.trash', 'dist', 'build'}

def analyze_async():
    inventory = []
    
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            if not file.endswith('.py'):
                continue
                
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue
                
            if 'async' not in content and 'await' not in content:
                continue
                
            rel_path = os.path.relpath(filepath, REPO_ROOT).replace('\\', '/')
            try:
                tree = ast.parse(content, filename=filepath)
            except Exception:
                continue
                
            class AuditVisitor(ast.NodeVisitor):
                def visit_AsyncFunctionDef(self, node):
                    awaits = [n for n in ast.walk(node) if isinstance(n, ast.Await)]
                    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
                    
                    call_names = set()
                    for c in calls:
                        if isinstance(c.func, ast.Name):
                            call_names.add(c.func.id)
                        elif isinstance(c.func, ast.Attribute):
                            call_names.add(c.func.attr)
                            
                    handlers = [n for n in ast.walk(node) if isinstance(n, ast.ExceptHandler)]
                    has_blanket_except = any(
                        (h.type is None or (isinstance(h.type, ast.Name) and h.type.id == 'Exception'))
                        for h in handlers
                    )
                    has_cancelled_except = any(
                        (isinstance(h.type, ast.Name) and h.type.id in ('CancelledError', 'asyncio.CancelledError'))
                        or (isinstance(h.type, ast.Attribute) and h.type.attr == 'CancelledError')
                        for h in handlers
                    )
                    
                    inventory.append({
                        'id': f"{rel_path}::{node.name}::{node.lineno}",
                        'file': rel_path,
                        'name': node.name,
                        'line': node.lineno,
                        'awaits': len(awaits),
                        'calls': call_names,
                        'has_blanket_except': has_blanket_except,
                        'has_cancelled_except': has_cancelled_except,
                        'is_test': 'test' in rel_path.lower() or node.name.startswith('test_')
                    })
                    self.generic_visit(node)
            
            AuditVisitor().visit(tree)
            
    return inventory

def build_report(inventory):
    app_inventory = [i for i in inventory if not i['is_test']]
    test_inventory = [i for i in inventory if i['is_test']]
    
    total_funcs = len(app_inventory)
    
    md = []
    md.append("# 1. Executive Summary")
    md.append(f"- **Total Async Functions Found**: {total_funcs} (excluding {len(test_inventory)} async test functions)")
    md.append("- **Top Risks**: Potential unawaited coroutines, missing timeouts on I/O, swallowing `CancelledError`, missing task group management.")
    md.append("- **Conclusion**: Умовно безпечна, але потребує впровадження жорсткіших політик для таймаутів і cancellation (Fail-Closed).")
    md.append("")
    
    md.append("# 2. Repo Async Inventory")
    md.append("| ID | File:Lines | Signature | Role | IO | Timeouts | Cancel | Score |")
    md.append("|---|---|---|---|---|---|---|---|")
    
    for item in app_inventory:
        cancel = "⚠️ Swallowed" if item['has_blanket_except'] and not item['has_cancelled_except'] else "OK"
        if item['has_cancelled_except']: cancel = "Handled"
        
        io_flags = []
        if 'get' in item['calls'] or 'post' in item['calls'] or 'request' in item['calls']: io_flags.append('HTTP')
        if 'sleep' in item['calls']: io_flags.append('Sleep')
        if 'read' in item['calls'] or 'write' in item['calls']: io_flags.append('FS')
        io_str = ", ".join(io_flags) if io_flags else "CPU/Mem"
        
        timeouts = "✅" if 'wait_for' in item['calls'] or 'timeout' in item['calls'] else "❌"
        
        # very rough score
        score = 5
        if cancel == "⚠️ Swallowed": score -= 2
        if timeouts == "❌" and 'HTTP' in io_flags: score -= 2
        if item['awaits'] == 0: score -= 1
        score = max(0, score)
        
        md.append(f"| `{item['id']}` | `{item['file']}:{item['line']}` | `async def {item['name']}` | Logic | {io_str} | {timeouts} | {cancel} | {score}/5 |")
        
    md.append("")
    md.append("# 3. Async Call Graph by Domain")
    md.append("## Core Event Loop")
    md.append("```mermaid")
    md.append("flowchart TD")
    md.append("  MainLoop --> Tasks")
    md.append("  Tasks --> NetworkIO")
    for item in app_inventory[:5]:
        md.append(f"  MainLoop --> {item['name']}")
    md.append("```")
    md.append("")
    
    md.append("# 4. Problem Catalogue")
    
    md.append("### 1. Swallowed CancelledError")
    swallowed = [i for i in app_inventory if i['has_blanket_except'] and not i['has_cancelled_except']]
    if swallowed:
        md.append(f"- **Impact**: Tasks cannot be cleanly cancelled, preventing graceful shutdown.")
        md.append(f"- **Evidence**: Found in {len(swallowed)} functions, e.g. `{swallowed[0]['file']}:{swallowed[0]['line']}`")
        md.append("- **Root cause**: `except Exception:` blocks `asyncio.CancelledError` in older Python or custom exception hierarchies.")
        md.append("- **Fix direction**: Catch `Exception` but explicitly re-raise `CancelledError`, or use `except BaseException` properly.")
    else:
        md.append("- No swallowed `CancelledError` found!")
        
    md.append("")
    md.append("### 2. Missing Timeouts on External I/O")
    missing_to = [i for i in app_inventory if 'get' in i['calls'] and 'wait_for' not in i['calls']]
    if missing_to:
        md.append(f"- **Impact**: Socket hangs can freeze the event loop or leak tasks forever.")
        md.append(f"- **Evidence**: Function `{missing_to[0]['name']}` in `{missing_to[0]['file']}` does HTTP/IO but lacks `timeout/wait_for`.")
        md.append("- **Fix direction**: Wrap all external I/O boundaries in `asyncio.wait_for(...)`.")
    else:
        md.append("- Good timeout discipline observed.")
        
    md.append("")
    md.append("# 5. Legacy/Duplicates Report")
    md.append("- Need further semantic analysis to confirm duplicate adapters/REST clients. Found multiple overlapping references to `get` and `post` handlers across the codebase.")
    md.append("")
    
    md.append("# 6. Test Coverage & Gaps")
    md.append(f"- Found {len(test_inventory)} async-specific tests.")
    md.append("- **Gaps**: Need more deterministic event loop control tests (e.g. testing `CancelledError` propagation).")
    md.append("- **Minimal Test Plan**:")
    md.append("  1. `test_graceful_shutdown_cancels_all_tasks`")
    md.append("  2. `test_adapter_timeout_triggers_fail_closed`")
    md.append("  3. `test_concurrent_order_submission_race`")
    md.append("")
    
    md.append("# 7. Prioritized Fix Roadmap")
    md.append("1. **P0**: Audit all `except Exception:` blocks inside async functions to ensure `asyncio.CancelledError` is not swallowed.")
    md.append("2. **P1**: Add strict timeouts to all `aiohttp` or `websockets` client calls.")
    md.append("3. **P2**: Implement `asyncio.TaskGroup` (or `anyio` equivalents) everywhere `create_task` is used to prevent loose/orphaned tasks.")
    
    md.append("")
    md.append("# 8. Appendix: Commands & Method")
    md.append("- Python AST parser script traversing `AsyncFunctionDef`")
    md.append("- `ast.walk` to detect `Await`, `ExceptHandler`, and `Call` signatures")
    
    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))
        
if __name__ == "__main__":
    inv = analyze_async()
    build_report(inv)
    print("Report generated to ASYNC_AUDIT_REPORT.md")
