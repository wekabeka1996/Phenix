"""
Conftest for tests/adapters directory.

Ensures apps/ is in sys.path for adapter tests.
"""

import sys
from pathlib import Path

# Add apps root to sys.path if not already there
project_root = Path(__file__).parent.parent.parent
apps_root = project_root / "apps"

if str(apps_root) not in sys.path:
    sys.path.insert(0, str(apps_root))
