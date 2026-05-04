from __future__ import annotations

import sys
from pathlib import Path


PPO_ROOT = Path(__file__).resolve().parents[8] / "apps" / "reference" / "domains" / "neocortex" / "PPO" / "ppo_library_v2"
if str(PPO_ROOT) not in sys.path:
    sys.path.insert(0, str(PPO_ROOT))
