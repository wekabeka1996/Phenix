"""Static test to verify no legacy FSM imports in production runtime modules.

This test reads runtime code as plain text and checks for forbidden legacy imports.
It does NOT import Python modules, just scans file contents with regex.

Forbidden imports:
- ExecPosFSM, ManageFlowFSM, CloseFlowFSM, OpenFlowFSM (legacy FSM classes)
- from apps.reference.domains.execution_position.fsm import ...
- from apps.reference.domains.execution_position.legacy import ...

Checked modules:
- apps/reference/main.py (entry point)
- apps/reference/domains/execution_position/shadow_execpos/** (V2 runtime)
"""

import re
from pathlib import Path
from typing import List, Tuple


def get_runtime_modules() -> List[Path]:
    """Get list of runtime modules to check for legacy imports."""
    repo_root = Path(__file__).parents[2]

    runtime_modules = []

    # 1. Main entry point
    main_py = repo_root / "apps" / "reference" / "main.py"
    if main_py.exists():
        runtime_modules.append(main_py)

    # 2. All Python files in shadow_execpos/
    shadow_dir = repo_root / "apps" / "reference" / \
        "domains" / "execution_position" / "shadow_execpos"
    if shadow_dir.exists():
        for py_file in shadow_dir.glob("*.py"):
            if py_file.name != "__init__.py":  # Include __init__.py for completeness
                runtime_modules.append(py_file)

    return runtime_modules


def check_file_for_legacy_imports(file_path: Path) -> List[Tuple[int, str]]:
    """
    Check a single file for legacy FSM imports.

    Returns:
        List of (line_number, line_content) tuples for lines with legacy imports
    """
    # Patterns that indicate actual imports (not just mentions in comments/docstrings)
    forbidden_patterns = [
        # Legacy module imports (from ... import ...)
        r'from\s+apps\.reference\.domains\.execution_position\.fsm\b',
        r'from\s+apps\.reference\.domains\.execution_position\.fsm_open\b',
        r'from\s+apps\.reference\.domains\.execution_position\.fsm_manage\b',
        r'from\s+apps\.reference\.domains\.execution_position\.fsm_close\b',

        # Legacy directory imports
        r'from\s+apps\.reference\.domains\.execution_position\.legacy\b',
        r'import\s+apps\.reference\.domains\.execution_position\.legacy\b',

        # Direct imports of legacy FSM classes (not in comments/docstrings)
        r'^[^#]*\bfrom\s+.*\s+import\s+.*\bExecPosFSM\b',
        r'^[^#]*\bfrom\s+.*\s+import\s+.*\bManageFlowFSM\b',
        r'^[^#]*\bfrom\s+.*\s+import\s+.*\bCloseFlowFSM\b',
        r'^[^#]*\bfrom\s+.*\s+import\s+.*\bOpenFlowFSM\b',
    ]

    violations = []

    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        in_docstring = False
        docstring_delim = None

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track docstring state
            if '"""' in line or "'''" in line:
                # Count occurrences
                triple_double = line.count('"""')
                triple_single = line.count("'''")

                if triple_double % 2 == 1:
                    in_docstring = not in_docstring
                    docstring_delim = '"""'
                elif triple_single % 2 == 1:
                    in_docstring = not in_docstring
                    docstring_delim = "'''"

            # Skip if in docstring or comment
            if in_docstring or stripped.startswith('#'):
                continue

            # Check for forbidden patterns
            for pattern in forbidden_patterns:
                if re.search(pattern, line):
                    violations.append((line_num, line.strip()))
                    break  # One violation per line is enough

    except Exception as e:
        # If file can't be read, that's a test failure
        violations.append((0, f"Error reading file: {e}"))

    return violations


def test_main_py_no_legacy_imports():
    """Verify that main.py does not import legacy FSM classes."""
    repo_root = Path(__file__).parents[2]
    main_py = repo_root / "apps" / "reference" / "main.py"

    assert main_py.exists(), "main.py not found"

    violations = check_file_for_legacy_imports(main_py)

    if violations:
        error_msg = f"main.py contains {len(violations)} legacy FSM import(s):\n"
        for line_num, line in violations:
            error_msg += f"  Line {line_num}: {line}\n"
        assert False, error_msg


def test_shadow_execpos_runtime_no_legacy_imports():
    """Verify that shadow_execpos/runtime.py does not import legacy FSM."""
    repo_root = Path(__file__).parents[2]
    runtime_py = repo_root / "apps" / "reference" / "domains" / \
        "execution_position" / "shadow_execpos" / "runtime.py"

    assert runtime_py.exists(), "shadow_execpos/runtime.py not found"

    violations = check_file_for_legacy_imports(runtime_py)

    if violations:
        error_msg = f"runtime.py contains {len(violations)} legacy FSM import(s):\n"
        for line_num, line in violations:
            error_msg += f"  Line {line_num}: {line}\n"
        assert False, error_msg


def test_shadow_execpos_bracket_service_no_legacy_imports():
    """Verify that shadow_execpos/bracket_service.py does not import legacy FSM."""
    repo_root = Path(__file__).parents[2]
    bracket_service_py = repo_root / "apps" / "reference" / "domains" / \
        "execution_position" / "shadow_execpos" / "bracket_service.py"

    assert bracket_service_py.exists(), "shadow_execpos/bracket_service.py not found"

    violations = check_file_for_legacy_imports(bracket_service_py)

    if violations:
        error_msg = f"bracket_service.py contains {len(violations)} legacy FSM import(s):\n"
        for line_num, line in violations:
            error_msg += f"  Line {line_num}: {line}\n"
        assert False, error_msg


def test_all_shadow_execpos_modules_no_legacy_imports():
    """Verify that ALL shadow_execpos modules do not import legacy FSM."""
    repo_root = Path(__file__).parents[2]
    shadow_dir = repo_root / "apps" / "reference" / \
        "domains" / "execution_position" / "shadow_execpos"

    assert shadow_dir.exists(), "shadow_execpos directory not found"

    all_violations = {}

    for py_file in shadow_dir.glob("*.py"):
        violations = check_file_for_legacy_imports(py_file)
        if violations:
            all_violations[py_file.name] = violations

    if all_violations:
        error_msg = f"Found legacy FSM imports in {len(all_violations)} shadow_execpos module(s):\n\n"
        for filename, violations in all_violations.items():
            error_msg += f"{filename}:\n"
            for line_num, line in violations:
                error_msg += f"  Line {line_num}: {line}\n"
            error_msg += "\n"
        assert False, error_msg


def test_runtime_modules_summary():
    """Summary test: report all runtime modules checked and total violation count."""
    runtime_modules = get_runtime_modules()

    assert len(runtime_modules) > 0, "No runtime modules found to check"

    total_violations = 0
    files_with_violations = []

    for module_path in runtime_modules:
        violations = check_file_for_legacy_imports(module_path)
        if violations:
            total_violations += len(violations)
            files_with_violations.append(module_path.name)

    # This test always passes, but logs summary info
    summary = f"""
    Runtime modules checked: {len(runtime_modules)}
    Files with legacy imports: {len(files_with_violations)}
    Total legacy import violations: {total_violations}
    """

    if files_with_violations:
        summary += f"\nFiles with violations: {', '.join(files_with_violations)}"

    # Print summary (will be visible in pytest -v output)
    print(summary)

    # Assert no violations found
    assert total_violations == 0, f"Found {total_violations} legacy import(s) in runtime modules"
