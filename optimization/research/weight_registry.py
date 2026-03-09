"""
optimization/research/weight_registry.py — Registry of available weight search spaces.

Maps group names to their YAML file paths.
All 8 groups cover the complete set of tunable weights in the Aurora system.
"""

from pathlib import Path
from typing import Dict, List

# Base directory for all search space YAML files
_SEARCH_SPACES_DIR = Path(__file__).parent / "search_spaces"

# Registry: group_name -> filename (relative to _SEARCH_SPACES_DIR)
_WEIGHT_GROUPS: Dict[str, str] = {
    "btc_weights":           "btc_weights.yaml",
    "eth_weights":           "eth_weights.yaml",
    "sol_weights":           "sol_weights.yaml",
    "global_signal_weights": "global_signal_weights.yaml",
    "feature_neutrals":      "feature_neutrals.yaml",
    "regime_knobs":          "regime_knobs.yaml",
    "risk_weights":          "risk_weights.yaml",
    "pillar_weights":        "pillar_weights.yaml",
}


def list_groups() -> List[str]:
    """Return the list of all registered weight group names."""
    return sorted(_WEIGHT_GROUPS.keys())


def resolve_paths(names: List[str], base_dir: Path = None) -> List[Path]:
    """
    Resolve group names to absolute YAML file paths.

    Args:
        names: list of group names (e.g., ["btc_weights", "global_signal_weights"])
        base_dir: override base directory (default: optimization/research/search_spaces/)

    Returns:
        List of resolved Path objects.

    Raises:
        KeyError: if any name is not in the registry.
        FileNotFoundError: if any resolved file does not exist.
    """
    search_dir = base_dir or _SEARCH_SPACES_DIR
    result = []
    for name in names:
        if name not in _WEIGHT_GROUPS:
            raise KeyError(
                f"Unknown weight group: '{name}'. "
                f"Available: {list_groups()}"
            )
        path = search_dir / _WEIGHT_GROUPS[name]
        if not path.exists():
            raise FileNotFoundError(
                f"Search space file not found: {path}. "
                f"Re-create optimization/research/search_spaces/ directory."
            )
        result.append(path)
    return result


def describe_group(name: str) -> Dict:
    """
    Return the 'meta' section from the YAML for a given group name.
    Useful for documentation / CLI --list output.
    """
    import yaml

    [path] = resolve_paths([name])
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw.get("meta", {"description": "(no meta)"})
