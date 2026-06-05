from apps.reference.shared.decision_primitives.score_lineage import (
    PRIMARY_SCORE_FIELDS,
    SCORE_FIELD_REGISTRY,
    SCORE_SCALE_FAMILIES,
    THRESHOLD_FAMILIES,
    LIVE_AUTHORITY_STATUSES,
    get_score_field_contract,
)


def test_primary_score_registry_covers_required_fields_with_closed_contracts() -> None:
    assert set(PRIMARY_SCORE_FIELDS).issubset(SCORE_FIELD_REGISTRY.keys())

    for field in PRIMARY_SCORE_FIELDS:
        contract = get_score_field_contract(field)
        assert contract is not None
        assert contract.scale in SCORE_SCALE_FAMILIES
        assert contract.threshold_family in THRESHOLD_FAMILIES
        assert contract.live_authority_status in LIVE_AUTHORITY_STATUSES
        assert contract.producer
        assert contract.consumer


def test_primary_score_fields_are_not_dual_raw_and_normalized_semantics() -> None:
    for field in PRIMARY_SCORE_FIELDS:
        contract = get_score_field_contract(field)
        assert contract is not None
        numeric_contract = contract.numeric_contract.lower()
        assert not (
            "finite signed float" in numeric_contract
            and "0..1 normalized" in numeric_contract
        )
