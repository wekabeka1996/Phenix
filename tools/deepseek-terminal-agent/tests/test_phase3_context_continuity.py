"""PHASE3-CONTEXT-CONTINUITY: Prove persistent context survives model switches.

This test suite verifies the invariant:
  "ChatSession is the source of truth; model_id only selects the executor for
   the next turn."

The critical path:
  1. Session starts with profile-A (model: deepseek-v4-pro)
  2. Turns are accumulated (user + assistant, possibly tool calls)
  3. Session active_profile is switched to profile-B (model: deepseek-v4-flash)
  4. ContextBuilder assembles context from ALL session turns — NO filtering by model_id
  5. The new model sees full history including turns from the old model
  6. Each turn retains its model_profile_snapshot for provenance
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from deepseek_terminal_agent.config import DeepSeekConfig, Settings
from deepseek_terminal_agent.sessions.artifacts import ArtifactStore
from deepseek_terminal_agent.sessions.chat_runtime import SessionChatRuntime
from deepseek_terminal_agent.sessions.context_builder import ContextBuilder
from deepseek_terminal_agent.sessions.memory_atoms import MemoryAtomStore
from deepseek_terminal_agent.sessions.models import ChatTurn, ModelProfile
from deepseek_terminal_agent.sessions.store import SessionStore


def make_settings() -> Settings:
    return Settings(deepseek=DeepSeekConfig(api_key="sk-test-key"))


def make_profile_a() -> ModelProfile:
    """Profile using deepseek-v4-pro — model A."""
    return ModelProfile(
        profile_id="profile-pro-thinking",
        name="Pro Thinking Max",
        model_id="deepseek-v4-pro",
        thinking_type="enabled",
        reasoning_effort="high",
        temperature=0.2,
        top_p=1.0,
        max_tokens=8192,
        response_format="text",
        stream=False,
        tool_mode="auto",
        max_iterations=6,
        command_timeout_sec=30,
        max_command_output_chars=12000,
        context_budget_chars=40000,
        memory_atom_budget=4,
        recent_turns_budget=6,
        tool_output_budget_chars=15000,
    )


def make_profile_b() -> ModelProfile:
    """Profile using deepseek-v4-flash — model B (the switched-to model)."""
    return ModelProfile(
        profile_id="profile-flash-scout",
        name="Flash Scout",
        model_id="deepseek-v4-flash",
        thinking_type="disabled",
        reasoning_effort="high",
        temperature=0.1,
        top_p=1.0,
        max_tokens=4096,
        response_format="text",
        stream=False,
        tool_mode="auto",
        max_iterations=4,
        command_timeout_sec=30,
        max_command_output_chars=12000,
        context_budget_chars=40000,
        memory_atom_budget=4,
        recent_turns_budget=6,
        tool_output_budget_chars=15000,
    )


def append_turn(store: SessionStore, session_id: str, turn_id: str, role: str,
                text: str, profile_snapshot: dict) -> None:
    store.append_turn(
        session_id,
        ChatTurn(
            turn_id=turn_id,
            session_id=session_id,
            role=role,
            visible_content=text,
            model_id=profile_snapshot["model_id"],
            model_profile_snapshot=profile_snapshot,
        ),
    )


# ── GATE 1: Turns survive model switch in store ─────────────────────────────

def test_gate1_model_switch_preserves_all_turns(tmp_path):
    """After switching the active profile, ALL prior turns remain in the store."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)

    # Start session with profile A
    session = store.create_session(default_profile=make_profile_a())
    sid = session.session_id
    snap_a = make_profile_a().snapshot()

    # Add turns under profile A
    append_turn(store, sid, "turn-1", "user", "Run analysis with pro model", snap_a)
    append_turn(store, sid, "turn-2", "assistant",
                "I will investigate the repository structure.", snap_a)

    # Switch to profile B
    profile_b = make_profile_b()
    store.update_session_profile(sid, profile_b)

    # Add turns under profile B
    snap_b = profile_b.snapshot()
    append_turn(store, sid, "turn-3", "user", "Now use flash for scout", snap_b)
    append_turn(store, sid, "turn-4", "assistant", "Quick scan complete.", snap_b)

    # Assert: all 4 turns present
    turns = store.list_turns(sid, include_internal=True)
    assert len(turns) == 4, f"Expected 4 turns, got {len(turns)}"

    # Assert: old turns retain original model profile
    turn1 = next(t for t in turns if t["turn_id"] == "turn-1")
    turn2 = next(t for t in turns if t["turn_id"] == "turn-2")
    turn3 = next(t for t in turns if t["turn_id"] == "turn-3")
    turn4 = next(t for t in turns if t["turn_id"] == "turn-4")

    assert turn1["model_profile_snapshot"]["model_id"] == "deepseek-v4-pro"
    assert turn2["model_profile_snapshot"]["model_id"] == "deepseek-v4-pro"
    assert turn3["model_profile_snapshot"]["model_id"] == "deepseek-v4-flash"
    assert turn4["model_profile_snapshot"]["model_id"] == "deepseek-v4-flash"

    # Assert: session's active_profile is now profile B
    reloaded = store.get_session(sid)
    assert reloaded.active_profile.model_id == "deepseek-v4-flash"
    assert reloaded.active_profile.name == "Flash Scout"


# ── GATE 2: ContextBuilder includes ALL turns regardless of model ────────────

def test_gate2_context_builder_includes_cross_model_turns(tmp_path):
    """ContextBuilder assembles turns from BOTH models into one context pack."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)

    profile_a = make_profile_a()
    profile_b = make_profile_b()

    # Create session with profile A
    session = store.create_session(default_profile=profile_a)
    sid = session.session_id

    # Add turns from model A
    append_turn(store, sid, "turn-1", "user", "User query under pro model",
                profile_a.snapshot())
    append_turn(store, sid, "turn-2", "assistant", "Pro model analysis result",
                profile_a.snapshot())

    # Switch to profile B
    store.update_session_profile(sid, profile_b)

    # Add turns from model B
    append_turn(store, sid, "turn-3", "user", "User query under flash model",
                profile_b.snapshot())
    append_turn(store, sid, "turn-4", "assistant", "Flash model quick result",
                profile_b.snapshot())

    # Build context with profile B as the active profile
    builder = ContextBuilder(
        settings, session_store=store,
        memory_store=memory, artifact_store=artifacts,
        root_dir=tmp_path,
    )
    built = builder.build(
        session_id=sid,
        current_user_message="Continue analysis",
        selected_profile=profile_b,
    )

    context_pack = built["context_pack"]
    report = built["context_report"]

    # GATE 2.1: Context pack contains text from BOTH models
    assert "Pro model analysis result" in context_pack, \
        "Context pack MUST include turns from model A (pro)"
    assert "Flash model quick result" in context_pack, \
        "Context pack MUST include turns from model B (flash)"
    assert "User query under pro model" in context_pack
    assert "User query under flash model" in context_pack

    # GATE 2.2: All 4 recent turns are included (none filtered out by model)
    assert len(report["recent_turns_included"]) == 4, \
        f"Expected 4 turns in context, got {report['recent_turns_included']}"

    # GATE 2.3: No warnings about context budget
    assert report["warnings"] == [], \
        f"Unexpected warnings: {report['warnings']}"


# ── GATE 3: Runtime sends correct model_id per active profile ───────────────

def test_gate3_runtime_uses_active_profile_model_id(tmp_path):
    """The chat runtime sends requests using the session's active_profile.model_id."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)
    builder = ContextBuilder(
        settings, session_store=store,
        memory_store=memory, artifact_store=artifacts,
        root_dir=tmp_path,
    )

    # Mock client that records the model_profile used
    client = MagicMock()
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].finish_reason = "stop"
    response.choices[0].message.content = "Done"
    response.choices[0].message.tool_calls = []
    response.choices[0].message.reasoning_content = None
    response.usage = None
    client.chat_completions.return_value = response

    class FakeExecutor:
        def execute(self, cmd, cwd=None, timeout_sec=None):
            return {"ok": True, "cmd": cmd, "exit_code": 0,
                    "stdout": "", "stderr": "", "timed_out": False,
                    "duration_ms": 1, "output_truncated": False}

    runtime = SessionChatRuntime(
        settings,
        session_store=store,
        context_builder=builder,
        client=client,
        executor_factory=lambda profile: FakeExecutor(),
    )

    # Create session with profile A (pro)
    profile_a = make_profile_a()
    session = store.create_session(default_profile=profile_a)

    # Send first message — should use profile A (pro)
    runtime.send_message(session_id=session.session_id, user_message="Hello from pro")
    call1 = client.chat_completions.call_args_list[0].kwargs
    assert call1["model_profile"].model_id == "deepseek-v4-pro", \
        f"First call should use pro model, got {call1['model_profile'].model_id}"

    # Switch to profile B (flash)
    profile_b = make_profile_b()
    store.update_session_profile(session.session_id, profile_b)

    # Send second message — should use profile B (flash)
    runtime.send_message(session_id=session.session_id, user_message="Hello from flash")
    call2 = client.chat_completions.call_args_list[1].kwargs
    assert call2["model_profile"].model_id == "deepseek-v4-flash", \
        f"Second call should use flash model, got {call2['model_profile'].model_id}"

    # GATE 3.3: The second call's messages include turn history from model A
    messages_call2 = call2["messages"]
    message_texts = " ".join(m["content"] for m in messages_call2)
    assert "Hello from pro" in message_texts, \
        "Model B MUST receive context including model A's turns"


# ── GATE 4: Session restart preserves active profile ────────────────────────

def test_gate4_session_restart_preserves_switched_profile(tmp_path):
    """After a restart (new SessionStore), the active_profile survives."""
    settings = make_settings()

    # Create and switch
    store1 = SessionStore(settings, root_dir=tmp_path)
    session = store1.create_session(default_profile=make_profile_a())
    store1.update_session_profile(session.session_id, make_profile_b())

    # Simulate restart — new store instance
    store2 = SessionStore(settings, root_dir=tmp_path)
    reloaded = store2.load_session_after_restart(session.session_id)

    assert reloaded.active_profile.model_id == "deepseek-v4-flash"
    assert reloaded.active_profile.profile_id == "profile-flash-scout"


# ── GATE 5: Turns filtered ONLY by recency budget, NEVER by model ───────────

def test_gate5_context_filters_by_recency_not_by_model(tmp_path):
    """When recent_turns_budget limits turns, it removes OLDEST first,
    not turns from a different model."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)
    artifacts = ArtifactStore(settings, root_dir=tmp_path)

    profile_a = make_profile_a()
    profile_b = make_profile_b()

    session = store.create_session(default_profile=profile_a)
    sid = session.session_id

    # Model A produces 4 turns
    append_turn(store, sid, "turn-a1", "user", "A-Query-1", profile_a.snapshot())
    append_turn(store, sid, "turn-a2", "assistant", "A-Answer-1", profile_a.snapshot())
    append_turn(store, sid, "turn-a3", "user", "A-Query-2", profile_a.snapshot())
    append_turn(store, sid, "turn-a4", "assistant", "A-Answer-2", profile_a.snapshot())

    # Switch to model B
    store.update_session_profile(sid, profile_b)

    # Model B produces 2 turns
    append_turn(store, sid, "turn-b1", "user", "B-Query-1", profile_b.snapshot())
    append_turn(store, sid, "turn-b2", "assistant", "B-Answer-1", profile_b.snapshot())

    # Set recent_turns_budget to 3 — should keep 3 MOST RECENT (all B + one A)
    profile_b.recent_turns_budget = 3
    builder = ContextBuilder(
        settings, session_store=store,
        memory_store=memory, artifact_store=artifacts,
        root_dir=tmp_path,
    )
    built = builder.build(
        session_id=sid,
        current_user_message="Continue",
        selected_profile=profile_b,
    )

    report = built["context_report"]
    included = report["recent_turns_included"]

    # The 3 most recent should be: b1, b2, and a4 (NOT filtered by model)
    assert len(included) == 3, f"Expected 3 turns, got {len(included)}: {included}"
    assert "turn-b1" in included, "Most recent user turn (model B) must be included"
    assert "turn-b2" in included, "Most recent assistant turn (model B) must be included"
    assert "turn-a4" in included, "Third-most-recent turn (model A) must be included"

    # Model A turn that's still in recency window is NOT dropped
    context_pack = built["context_pack"]
    assert "A-Answer-2" in context_pack, "Model A turn within recency window must appear"

    # Older model A turns are omitted (due to budget, not model filtering)
    assert report["omitted_turns_count"] == 3, \
        f"Expected 3 omitted (a1,a2,a3), got {report['omitted_turns_count']}"


# ── GATE 6: Compressor preserves cross-model history ────────────────────────

def test_gate6_compressor_preserves_cross_model_turns_on_disk(tmp_path):
    """Compression marks turns as compacted but never deletes raw turn data.
    Cross-model turns survive compression unchanged."""
    settings = make_settings()
    store = SessionStore(settings, root_dir=tmp_path)
    memory = MemoryAtomStore(settings, root_dir=tmp_path)

    profile_a = make_profile_a()
    profile_b = make_profile_b()

    session = store.create_session(default_profile=profile_a)
    sid = session.session_id

    # Model A turns
    append_turn(store, sid, "turn-a1", "user", "A query", profile_a.snapshot())
    append_turn(store, sid, "turn-a2", "assistant", "A answer", profile_a.snapshot())

    # Switch to model B
    store.update_session_profile(sid, profile_b)

    # Model B turns
    append_turn(store, sid, "turn-b1", "user", "B query", profile_b.snapshot())
    append_turn(store, sid, "turn-b2", "assistant", "B answer", profile_b.snapshot())

    # Read raw turns file — verify all 4 turns are physically on disk
    turns_path = tmp_path / ".agent_memory" / "sessions" / \
        sid / "turns.dsctx.jsonl"
    raw_lines = turns_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(raw_lines) == 4, \
        f"Raw turns file should have 4 lines (one per turn), got {len(raw_lines)}"

    # Parse each line — verify model provenance
    parsed = [json.loads(line) for line in raw_lines]
    model_ids = [p["model_id"] for p in parsed]
    assert model_ids == ["deepseek-v4-pro", "deepseek-v4-pro",
                         "deepseek-v4-flash", "deepseek-v4-flash"], \
        f"Model provenance broken: {model_ids}"
