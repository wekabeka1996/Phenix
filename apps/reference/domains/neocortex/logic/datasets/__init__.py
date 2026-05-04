"""
Dataset hygiene / provenance contracts for neocortex.
"""

from .contracts import (
    DatasetCutoverDecision,
    DatasetCutoverSummary,
    DatasetEvaluatedSample,
    DatasetManifest,
    DatasetSampleProvenance,
    DatasetSplitManifest,
)
from .hygiene import DatasetPolicyEngine

__all__ = [
    "DatasetCutoverDecision",
    "DatasetCutoverEvaluator",
    "DatasetCutoverSummary",
    "DatasetEvaluatedSample",
    "DatasetManifest",
    "DatasetPolicyEngine",
    "DatasetSampleProvenance",
    "DatasetSplitManifest",
    "build_dataset_cutover_summary",
]


def __getattr__(name: str) -> object:
    if name in {"DatasetCutoverEvaluator", "build_dataset_cutover_summary"}:
        from .cutover import DatasetCutoverEvaluator, build_dataset_cutover_summary

        exports = {
            "DatasetCutoverEvaluator": DatasetCutoverEvaluator,
            "build_dataset_cutover_summary": build_dataset_cutover_summary,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
