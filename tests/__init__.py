"""
This file makes the 'tests' directory a Python package and ensures
that the project root is added to the system path before any tests are run.
"""

import sys
from pathlib import Path

# Add project root to the Python path to allow imports like 'from apps...'
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
