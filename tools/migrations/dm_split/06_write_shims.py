"""Write backward-compatible shims for authorized moved modules.

Input: hard-coded shim allowlist derived from Audit section 12.4 and B.2.
Output: shim .py files at old decision_making module paths.
Side effects: writes shim files unless --dry-run is passed.
"""

from __future__ import annotations

import argparse

from dm_split_lib import ROOT

SHIMS = {
    "decision_making.py": ("apps.reference.domains.decision_making.core.facade", "DecisionMaking"),
    "normalized_reject_reasons.py": ("apps.reference.domains.decision_making.contracts.normalized_reject_reasons", "NormalizedRejectReasons"),
    "schemas.py": ("apps.reference.domains.decision_making.contracts.schemas", "PortfolioStatePayload"),
    "dm_log_adapter.py": ("apps.reference.domains.decision_making.observability.log_adapter", "DecisionLog"),
    "why_codes.py": ("apps.reference.domains.decision_making.contracts.why_codes", "WhyCode"),
    "mean_reversion_handler.py": ("apps.reference.domains.strategies.runtimes.mean_reversion.handler", "MeanReversionHandler"),
    "aurora_handler.py": ("apps.reference.domains.strategies.runtimes.aurora.handler", "AuroraHandler"),
    "md_amr_handler.py": ("apps.reference.domains.strategies.runtimes.md_amr.handler", "MDAMRHandler"),
    "quadratic_scoring_kernel.py": ("apps.reference.shared.decision_primitives.scoring_kernel", "QuadraticScoringKernel"),
    "entry_plan.py": ("apps.reference.shared.decision_primitives.entry_plan", "EntryPlanResult"),
}


def shim_text(old_name: str, target: str, symbol: str) -> str:
    old_module = f"apps.reference.domains.decision_making.{old_name[:-3]}"
    return f'''"""Backward-compat shim for {old_module}.

Deprecation window: one release from 2026-04-24 Package 2.
"""

import warnings

warnings.warn(
    "{old_module} is moved to {target}",
    DeprecationWarning,
    stacklevel=2,
)

from {target} import *  # noqa: F401,F403
from {target} import {symbol}  # noqa: F401
'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    base = ROOT / "apps/reference/domains/decision_making"
    for old_name, (target, symbol) in SHIMS.items():
        path = base / old_name
        text = shim_text(old_name, target, symbol)
        if args.dry_run:
            print(f"write {path.relative_to(ROOT).as_posix()} -> {target}")
            continue
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
