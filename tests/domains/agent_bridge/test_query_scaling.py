from pathlib import Path

from apps.reference.domains.agent_bridge.query_scaling import profile_query_scaling
from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore
from tests.domains.agent_bridge.test_scenario_memory import _store


def test_query_scaling_profile_is_read_only_and_componentized(tmp_path: Path) -> None:
    store, btc, _ = _store(tmp_path)
    store.build_index(persist=True)
    before = store.ledger_path.read_bytes()
    profile = profile_query_scaling(tmp_path, packet_id=btc.pre_action_note.packet_id, iterations=2)
    assert profile["read_only"] is True
    assert profile["raw_ledger_mutated"] is False
    assert set(profile["components_ms"]) == {
        "file_io", "ledger_parse_validation", "latest_revision_selection",
        "persisted_index_load_validation", "query_filtering", "response_serialization",
    }
    assert set(profile["cold_query_ms"]) == {"completed", "lessons", "confusion", "packet"}
    assert profile["cache_info"]["hits"] > 0
    assert store.ledger_path.read_bytes() == before
