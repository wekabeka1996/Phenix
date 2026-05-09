#!/usr/bin/env python3
from __future__ import annotations
from calibrators.policy_gates.calibrate_low_vol_cost_floor import main

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from calibrators.policy_gates.calibrate_low_vol_cost_floor import *  # noqa: F401,F403


if __name__ == "__main__":
    raise SystemExit(main())
