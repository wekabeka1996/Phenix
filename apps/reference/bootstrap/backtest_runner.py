from __future__ import annotations

from typing import Optional

from apps.reference.config_loader import AuroraConfig


def resolve_backtest_max_ticks(config: AuroraConfig) -> Optional[int]:
    """Resolve optional max_ticks from typed config only (SSOT, no env bypass)."""
    try:
        bt_cfg = getattr(getattr(config, "trading", None), "backtest", None)
        mt = getattr(bt_cfg, "max_ticks", None) if bt_cfg is not None else None
        if mt is None:
            return None
        max_ticks = int(mt)
        return max_ticks if max_ticks > 0 else None
    except Exception:
        return None
