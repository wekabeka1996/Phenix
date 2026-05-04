import ast
import os
import json
from pathlib import Path

def analyze_ast(repo_root):
    async_funcs = []
    
    for root, dirs, files in os.walk(repo_root):
        # Exclude common dirs
        dirs[:] = [d for d in dirs if d not in ('.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache')]
        
        for file in files:
            if not file.endswith('.py'):
                continue
            
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'async' not in content and 'await' not in content:
                    continue
                    
                tree = ast.parse(content, filename=filepath)
                rel_path = os.path.relpath(filepath, repo_root)
                
                class AsyncVisitor(ast.NodeVisitor):
                    def visit_AsyncFunctionDef(self, node):
                        # Find awaits
                        awaits = [n for n in ast.walk(node) if isinstance(n, ast.Await)]
                        # Find sleep, sync IO
                        calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
                        call_names = []
                        for c in calls:
                            if isinstance(c.func, ast.Name):
                                call_names.append(c.func.id)
                            elif isinstance(c.func, ast.Attribute):
                                call_names.append(c.func.attr)
                        
                        creates_tasks = 'create_task' in call_names or 'ensure_future' in call_names
                        sleeps = 'sleep' in call_names
                        
                        # Check try/except Exception and CancelledError
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
                        
                        async_funcs.append({
                            'id': f"{rel_path}::{node.name}::{node.lineno}",
                            'file': rel_path,
                            'name': node.name,
                            'line': node.lineno,
                            'end_line': getattr(node, 'end_lineno', node.lineno),
                            'awaits_count': len(awaits),
                            'calls': list(set(call_names)),
                            'creates_tasks': creates_tasks,
                            'sleeps': sleeps,
                            'has_blanket_except': has_blanket_except,
                            'has_cancelled_except': has_cancelled_except
                        })
                        self.generic_visit(node)
                
                AsyncVisitor().visit(tree)
                
            except Exception as e:
                pass # skip unparseable
                
    with open('async_inventory.json', 'w', encoding='utf-8') as out:
        json.dump(async_funcs, out, indent=2)

if __name__ == "__main__":
    analyze_ast(".")
    print("DONE")
