"""
P6 dataset hygiene / provenance engine.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from apps.reference.domains.neocortex.config_models import DatasetConfig
from apps.reference.domains.neocortex.logic.datasets.contracts import (
    DatasetEvaluatedSample,
    DatasetManifest,
    DatasetSampleProvenance,
    DatasetSplitManifest,
)


OBJECTIVE_FAMILIES = {
    "representation",
    "regime_supervision",
    "execution_quality",
    "policy",
}


class DatasetPolicyEngine:
    """
    Evaluate raw samples into explicit dataset eligibility/provenance contracts.
    """

    def __init__(
        self,
        config: DatasetConfig,
        *,
        policy_training_mode: str,
        representation_training_mode: str,
        sequence_inference_mode: str,
    ) -> None:
        self.config = config
        self.policy_training_mode = str(policy_training_mode).strip().lower()
        self.representation_training_mode = str(
            representation_training_mode
        ).strip().lower()
        self.sequence_inference_mode = str(sequence_inference_mode).strip().lower()

    def evaluate_sample(
        self,
        sample: Mapping[str, Any],
        *,
        objective_family: str,
        source_type: str,
        source_ref: str,
        source_event_type: str,
        ingestion_mode: str,
    ) -> DatasetEvaluatedSample:
        sample_dict = dict(sample)
        family = str(objective_family).strip().lower()

        exclusion_reasons: List[str] = []
        quarantine_reasons: List[str] = []

        if family not in OBJECTIVE_FAMILIES:
            exclusion_reasons.append("unknown_objective_family")
            family = "representation"

        if not source_type or not source_ref or not source_event_type:
            exclusion_reasons.append("missing_source_provenance")

        event_ts_ms = self._extract_event_ts_ms(sample_dict)
        if event_ts_ms is None:
            exclusion_reasons.append("missing_event_ts_ms")
            event_ts_ms = 0

        if self._contains_magicmock(sample_dict):
            quarantine_reasons.append("magicmock_contamination")

        if self._has_contaminated_identifier(sample_dict):
            quarantine_reasons.append("contaminated_identifier")

        legacy_non_causal = self._is_legacy_non_causal(sample_dict)

        status = "rejected"
        if not quarantine_reasons:
            family_status, family_exclusions, family_quarantines = self._evaluate_family_rules(
                family,
                sample_dict,
                legacy_non_causal=legacy_non_causal,
            )
            status = family_status
            exclusion_reasons.extend(family_exclusions)
            quarantine_reasons.extend(family_quarantines)

        if quarantine_reasons:
            status = "quarantined"
        elif exclusion_reasons and status == "trainable":
            status = "rejected"

        sequence_contract_mode = self._extract_sequence_contract_mode(
            family,
            sample_dict,
        )
        provenance = DatasetSampleProvenance(
            dataset_sample_id=self._build_dataset_sample_id(
                family=family,
                source_type=source_type,
                source_ref=source_ref,
                source_event_type=source_event_type,
                event_ts_ms=event_ts_ms,
                symbol=sample_dict.get("symbol"),
                lifecycle_id=sample_dict.get("lifecycle_id"),
                trade_id=sample_dict.get("trade_id"),
            ),
            objective_family=family,
            source_type=str(source_type),
            source_ref=str(source_ref),
            source_event_type=str(source_event_type),
            event_ts_ms=int(event_ts_ms),
            symbol=self._coerce_optional_string(sample_dict.get("symbol")),
            lifecycle_id=self._coerce_optional_string(sample_dict.get("lifecycle_id")),
            trade_id=self._coerce_optional_string(sample_dict.get("trade_id")),
            ingestion_mode=str(ingestion_mode),
            legacy_causal_mode=legacy_non_causal,
            sequence_contract_mode=sequence_contract_mode,
            policy_training_mode=self.policy_training_mode,
            eligibility_status=status,
            exclusion_reasons=sorted(set(exclusion_reasons)),
            quarantine_reasons=sorted(set(quarantine_reasons)),
        )
        return DatasetEvaluatedSample(
            objective_family=provenance.objective_family,
            eligibility_status=provenance.eligibility_status,
            is_trainable=provenance.eligibility_status == "trainable",
            sample=sample_dict,
            provenance=provenance,
        )

    def build_manifest(
        self,
        samples: Iterable[DatasetEvaluatedSample],
        *,
        objective_family: str,
    ) -> DatasetManifest:
        evaluated = list(samples)
        family = str(objective_family).strip().lower()
        if family not in OBJECTIVE_FAMILIES:
            raise ValueError(f"Unknown objective family: {objective_family}")

        for item in evaluated:
            if item.objective_family != family:
                raise ValueError("Mixed objective families are forbidden in one dataset manifest")

        build_time_ms = int(time.time() * 1000)
        sample_counts = Counter(
            item.eligibility_status for item in evaluated
        )
        exclusion_reason_counts = Counter()
        quarantine_reason_counts = Counter()
        reward_complete_stats = Counter({"complete": 0, "incomplete": 0, "missing": 0})
        symbols = set()
        source_inventory = set()
        sequence_modes = set()
        legacy_non_causal_count = 0
        event_times: List[int] = []

        for item in evaluated:
            prov = item.provenance
            exclusion_reason_counts.update(prov.exclusion_reasons)
            quarantine_reason_counts.update(prov.quarantine_reasons)
            source_inventory.add(f"{prov.source_type}:{prov.source_ref}")
            if prov.symbol:
                symbols.add(prov.symbol)
            if prov.sequence_contract_mode:
                sequence_modes.add(prov.sequence_contract_mode)
            if prov.legacy_causal_mode:
                legacy_non_causal_count += 1
            if prov.event_ts_ms > 0:
                event_times.append(prov.event_ts_ms)

            reward_complete = item.sample.get("reward_complete")
            if reward_complete is True:
                reward_complete_stats["complete"] += 1
            elif reward_complete is False:
                reward_complete_stats["incomplete"] += 1
            else:
                reward_complete_stats["missing"] += 1

        trainable = sorted(
            [item for item in evaluated if item.eligibility_status == "trainable"],
            key=lambda item: (item.provenance.event_ts_ms, item.provenance.dataset_sample_id),
        )
        splits = self._build_time_splits(trainable)
        dataset_id = self._build_dataset_id(family, evaluated)

        return DatasetManifest(
            dataset_id=dataset_id,
            objective_family=family,
            build_time_ms=build_time_ms,
            manifest_version=int(self.config.manifest_version),
            config_signature={
                "manifest_version": int(self.config.manifest_version),
                "split": {
                    "train_ratio": float(self.config.split.train_ratio),
                    "val_ratio": float(self.config.split.val_ratio),
                    "test_ratio": float(self.config.split.test_ratio),
                },
                "policy_training_mode": self.policy_training_mode,
                "representation_training_mode": self.representation_training_mode,
                "sequence_inference_mode": self.sequence_inference_mode,
            },
            source_inventory=sorted(source_inventory),
            time_window={
                "start_event_ts_ms": min(event_times) if event_times else None,
                "end_event_ts_ms": max(event_times) if event_times else None,
                "split_mode": "time_ordered_deterministic",
            },
            sample_counts={
                "trainable": int(sample_counts.get("trainable", 0)),
                "eval_only": int(sample_counts.get("eval_only", 0)),
                "diagnostics_only": int(sample_counts.get("diagnostics_only", 0)),
                "quarantined": int(sample_counts.get("quarantined", 0)),
                "rejected": int(sample_counts.get("rejected", 0)),
            },
            exclusion_reason_counts=dict(sorted(exclusion_reason_counts.items())),
            quarantine_reason_counts=dict(sorted(quarantine_reason_counts.items())),
            symbols=sorted(symbols),
            legacy_non_causal_count=legacy_non_causal_count,
            reward_complete_stats=dict(reward_complete_stats),
            sequence_contract_modes=sorted(sequence_modes),
            splits=splits,
        )

    def _evaluate_family_rules(
        self,
        family: str,
        sample: Mapping[str, Any],
        *,
        legacy_non_causal: bool,
    ) -> Tuple[str, List[str], List[str]]:
        exclusion_reasons: List[str] = []
        quarantine_reasons: List[str] = []

        if family == "representation":
            if not self._has_representation_payload(sample):
                exclusion_reasons.append("missing_representation_payload")
                return "rejected", exclusion_reasons, quarantine_reasons
            sequence_mode = self._extract_sequence_contract_mode(family, sample)
            if sequence_mode != self.representation_training_mode:
                exclusion_reasons.append("unsupported_sequence_contract")
                return "rejected", exclusion_reasons, quarantine_reasons
            if legacy_non_causal:
                exclusion_reasons.append("legacy_non_causal_representation")
                return "eval_only", exclusion_reasons, quarantine_reasons
            return "trainable", exclusion_reasons, quarantine_reasons

        if family == "regime_supervision":
            if legacy_non_causal:
                exclusion_reasons.append("legacy_non_causal_not_allowed")
            if sample.get("predicted_regime") is None or sample.get("realized_regime") is None:
                exclusion_reasons.append("missing_regime_target")
            if exclusion_reasons:
                return "rejected", exclusion_reasons, quarantine_reasons
            return "trainable", exclusion_reasons, quarantine_reasons

        if family == "execution_quality":
            if legacy_non_causal:
                exclusion_reasons.append("legacy_non_causal_not_allowed")
            if not sample.get("trade_id") and not sample.get("lifecycle_id"):
                exclusion_reasons.append("missing_lifecycle_identity")
            if sample.get("unresolved_lifecycle") or sample.get("unresolved_close"):
                quarantine_reasons.append("unresolved_lifecycle")
                return "quarantined", exclusion_reasons, quarantine_reasons
            if sample.get("reward_complete") is False or sample.get("reward_missing") is True:
                exclusion_reasons.append("reward_incomplete")
                return "diagnostics_only", exclusion_reasons, quarantine_reasons
            if exclusion_reasons:
                return "rejected", exclusion_reasons, quarantine_reasons
            return "trainable", exclusion_reasons, quarantine_reasons

        if family == "policy":
            if not sample.get("trade_id") and not sample.get("lifecycle_id"):
                exclusion_reasons.append("missing_lifecycle_identity")
            if sample.get("reward_complete") is not True or sample.get("reward_missing") is True:
                exclusion_reasons.append("reward_incomplete")
            if sample.get("unresolved_lifecycle") or sample.get("unresolved_close"):
                exclusion_reasons.append("unresolved_lifecycle")
            if legacy_non_causal:
                exclusion_reasons.append("legacy_non_causal_not_allowed")
            sequence_mode = self._extract_sequence_contract_mode(family, sample)
            if sequence_mode != self.sequence_inference_mode:
                exclusion_reasons.append("unsupported_sequence_contract")
            if self.policy_training_mode == "disabled":
                exclusion_reasons.append("policy_training_disabled")
            if exclusion_reasons:
                return "rejected", exclusion_reasons, quarantine_reasons
            return "trainable", exclusion_reasons, quarantine_reasons

        return "rejected", ["unknown_objective_family"], quarantine_reasons

    def _build_time_splits(
        self,
        trainable_samples: List[DatasetEvaluatedSample],
    ) -> List[DatasetSplitManifest]:
        n = len(trainable_samples)
        train_n = int(n * float(self.config.split.train_ratio))
        val_n = int(n * float(self.config.split.val_ratio))
        if train_n + val_n > n:
            val_n = max(0, n - train_n)
        train_items = trainable_samples[:train_n]
        val_items = trainable_samples[train_n:train_n + val_n]
        test_items = trainable_samples[train_n + val_n:]

        return [
            self._split_manifest("train", train_items),
            self._split_manifest("val", val_items),
            self._split_manifest("test", test_items),
        ]

    def _split_manifest(
        self,
        split_name: str,
        items: List[DatasetEvaluatedSample],
    ) -> DatasetSplitManifest:
        sample_ids = [item.provenance.dataset_sample_id for item in items]
        times = [item.provenance.event_ts_ms for item in items]
        return DatasetSplitManifest(
            split_name=split_name,
            sample_ids=sample_ids,
            sample_count=len(sample_ids),
            start_event_ts_ms=min(times) if times else None,
            end_event_ts_ms=max(times) if times else None,
        )

    def _build_dataset_id(
        self,
        objective_family: str,
        samples: List[DatasetEvaluatedSample],
    ) -> str:
        payload = {
            "objective_family": objective_family,
            "manifest_version": int(self.config.manifest_version),
            "split": {
                "train_ratio": float(self.config.split.train_ratio),
                "val_ratio": float(self.config.split.val_ratio),
                "test_ratio": float(self.config.split.test_ratio),
            },
            "sample_ids": sorted(
                item.provenance.dataset_sample_id for item in samples
            ),
            "policy_training_mode": self.policy_training_mode,
            "representation_training_mode": self.representation_training_mode,
            "sequence_inference_mode": self.sequence_inference_mode,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return f"{objective_family}:{digest}"

    def _build_dataset_sample_id(
        self,
        *,
        family: str,
        source_type: str,
        source_ref: str,
        source_event_type: str,
        event_ts_ms: int,
        symbol: Any,
        lifecycle_id: Any,
        trade_id: Any,
    ) -> str:
        payload = {
            "objective_family": family,
            "source_type": str(source_type),
            "source_ref": str(source_ref),
            "source_event_type": str(source_event_type),
            "event_ts_ms": int(event_ts_ms),
            "symbol": self._coerce_optional_string(symbol),
            "lifecycle_id": self._coerce_optional_string(lifecycle_id),
            "trade_id": self._coerce_optional_string(trade_id),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return f"{family}:{digest}"

    def _extract_sequence_contract_mode(
        self,
        family: str,
        sample: Mapping[str, Any],
    ) -> Optional[str]:
        explicit = sample.get("sequence_contract_mode")
        if explicit is not None:
            mode = str(explicit).strip().lower()
            return mode or None
        if family == "representation":
            return self.representation_training_mode
        if family == "policy":
            return self.sequence_inference_mode
        return None

    def _extract_event_ts_ms(self, sample: Mapping[str, Any]) -> Optional[int]:
        raw = sample.get("event_ts_ms")
        if raw is None or isinstance(raw, bool):
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _has_representation_payload(self, sample: Mapping[str, Any]) -> bool:
        return (
            sample.get("features_vector") is not None
            or sample.get("features") is not None
        )

    def _is_legacy_non_causal(self, sample: Mapping[str, Any]) -> bool:
        if sample.get("time_is_causal") is False:
            return True
        time_source = sample.get("time_source")
        return str(time_source).strip().lower() == "legacy_non_causal_file_offset"

    def _has_contaminated_identifier(self, sample: Mapping[str, Any]) -> bool:
        for field in ("lifecycle_id", "trade_id", "order_id", "client_order_id"):
            raw = sample.get(field)
            if raw is None:
                continue
            text = str(raw)
            lowered = text.lower()
            if "magicmock" in lowered or "<mock" in lowered or ".return_value" in lowered:
                return True
        return False

    def _contains_magicmock(self, value: Any) -> bool:
        type_name = type(value).__name__
        if type_name in {"MagicMock", "Mock", "AsyncMock"}:
            return True
        if isinstance(value, Mapping):
            return any(self._contains_magicmock(v) for v in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(self._contains_magicmock(v) for v in value)
        if isinstance(value, str):
            lowered = value.lower()
            return "magicmock" in lowered or "<mock" in lowered
        return False

    def _coerce_optional_string(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
