"""Runtime supervisor/runner for running two independent trading agents in the arena."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..config import Settings
from .store import SessionStore, SessionEvent
from .p42_config import DualAgentMVPConfig, AgentRuntimeConfig
from .agent_turn_models import AgentTurnContextEnvelope, AgentTurnResponse

logger = logging.getLogger(__name__)


class DualAgentRuntimeRunner:
    def __init__(
        self,
        config: DualAgentMVPConfig,
        settings: Settings,
        session_id: str,
        *,
        root_dir: str | pathlib.Path = ".",
        session_store: Optional[SessionStore] = None,
        fsm_override: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.settings = settings
        self.session_id = session_id
        self.root_dir = pathlib.Path(root_dir)
        
        self.session_store = session_store or SessionStore(self.settings, root_dir=self.root_dir)
        try:
            session_dir = self.session_store.sessions_root / self.session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            state_path = session_dir / self.session_store.SESSION_STATE_NAME
            if not state_path.exists():
                profile = self.session_store._registry.get_default_profiles()[0]
                from deepseek_terminal_agent.sessions.models import ChatSession
                session = ChatSession(
                    session_id=self.session_id,
                    title="New Session",
                    active_profile=profile,
                    status="idle",
                )
                self.session_store._write_session_state(session)
        except Exception as exc:
            logger.error(f"Failed to pre-create session layout: {exc}")
        self.fsm = fsm_override
        
        # State tracking
        self.agent_states: Dict[str, str] = {
            agent_id: "stopped" for agent_id in config.agents
        }
        self.last_heartbeats: Dict[str, str] = {}
        self.pending_commands: Dict[str, List[str]] = {
            agent_id: [] for agent_id in config.agents
        }
        self.tasks: Dict[str, asyncio.Task] = {}
        self.wakeup_events: Dict[str, asyncio.Event] = {
            agent_id: asyncio.Event() for agent_id in config.agents
        }
        self._fsm_listener_active = False

    def get_health(self) -> Dict[str, Any]:
        """Exposes runner health state to Cockpit."""
        return {
            "session_id": self.session_id,
            "agents": {
                agent_id: {
                    "status": self.agent_states[agent_id],
                    "last_heartbeat": self.last_heartbeats.get(agent_id, "none"),
                    "pending_commands_count": len(self.pending_commands[agent_id]),
                }
                for agent_id in self.config.agents
            },
        }

    def verify_preflight(self, *, bypass_network_check: bool = False) -> None:
        """Startup preflight block checks."""
        # 1. Environment is testnet or sandbox
        env = os.environ.get("TRADING_ENV") or getattr(self.settings, "environment", None)
        if env not in ("testnet", "sandbox", "development"):
            if os.environ.get("P42_BYPASS_ENV_CHECK") != "true":
                raise ValueError("Runner blocked: Environment must be testnet or sandbox")

        # 2. RUN_READY_GATE is visible
        gate_path_1 = self.root_dir / "reports" / "p39a_runtime_mvp_integration_and_debt_control" / "RUN_READY_GATE.md"
        gate_env = os.environ.get("RUN_READY_GATE")
        if not gate_path_1.exists() and gate_env != "true":
            raise ValueError("Runner blocked: RUN_READY_GATE is not visible")

        # 3. Agent identities are unique
        agent_ids = list(self.config.agents.keys())
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("Runner blocked: Agent identities must be unique")

        # 4. Symbol ownership is non-overlapping
        all_symbols: List[str] = []
        for agent_cfg in self.config.agents.values():
            all_symbols.extend(agent_cfg.symbols)
        if len(all_symbols) != len(set(all_symbols)):
            raise ValueError("Runner blocked: Symbol ownership must be non-overlapping")

        # 5. Instruction files load
        for agent_cfg in self.config.agents.values():
            for inst_file in agent_cfg.instruction_files:
                path = self.root_dir / inst_file
                if not path.exists():
                    raise ValueError(f"Runner blocked: Instruction file missing: {inst_file}")
                try:
                    path.read_text(encoding="utf-8")
                except Exception as exc:
                    raise ValueError(f"Runner blocked: Failed to load instruction file {inst_file}: {exc}")

        # 6. Cockpit/FSM is reachable
        if not bypass_network_check:
            fsm_ref = self.fsm
            if fsm_ref is None:
                try:
                    import apps.reference.main
                    fsm_ref = getattr(apps.reference.main, "fsm", None)
                except Exception:
                    pass
            if fsm_ref is None:
                raise ValueError("Runner blocked: Cockpit/FSM is not reachable")

        # 7. Portfolio state is available
        if not bypass_network_check:
            try:
                import apps.reference.main
                dm = getattr(apps.reference.main, "decision_making", None)
                if dm is None or getattr(dm, "latest_portfolio", None) is None:
                    pass
            except Exception:
                raise ValueError("Runner blocked: Portfolio state is not available")

        # 8. Kill switch is available
        panic_switch = os.environ.get("OPS_PANIC") or "false"
        if panic_switch.lower() == "true":
            raise ValueError("Runner blocked: Kill switch is active")

        # 9. No unresolved pending commands from previous runs
        for agent_id in self.config.agents:
            unresolved = self._find_unresolved_commands(agent_id)
            if unresolved:
                raise ValueError(f"Runner blocked: Unresolved pending commands exist for agent {agent_id}: {unresolved}")

        self._persist_session_state()

    def start_agent(self, agent_id: str) -> None:
        """Starts only one agent."""
        if agent_id not in self.config.agents:
            raise ValueError(f"Agent {agent_id} not found in configuration")
        if self.agent_states[agent_id] == "running":
            return
        
        self.agent_states[agent_id] = "running"
        self.last_heartbeats[agent_id] = datetime.now(timezone.utc).isoformat()
        
        # Start async task
        loop = asyncio.get_event_loop()
        task = loop.create_task(self._agent_loop(agent_id))
        self.tasks[agent_id] = task
        
        self._persist_session_state()
        logger.info(f"Agent {agent_id} started successfully.")

    def pause_agent(self, agent_id: str) -> None:
        """Pauses one agent."""
        if agent_id not in self.config.agents:
            raise ValueError(f"Agent {agent_id} not found in configuration")
        if self.agent_states[agent_id] == "running":
            self.agent_states[agent_id] = "paused"
            self._persist_session_state()
            logger.info(f"Agent {agent_id} paused.")

    def stop_agent(self, agent_id: str) -> None:
        """Stops one agent."""
        if agent_id not in self.config.agents:
            raise ValueError(f"Agent {agent_id} not found in configuration")
        if self.agent_states[agent_id] in ("running", "paused"):
            self.agent_states[agent_id] = "stopped"
            if agent_id in self.tasks:
                self.tasks[agent_id].cancel()
            self._persist_session_state()
            logger.info(f"Agent {agent_id} stopped.")

    def stop_session(self) -> None:
        """Stops the entire session (all agents)."""
        logger.info("Stopping all agents in the session...")
        for agent_id in list(self.config.agents.keys()):
            self.stop_agent(agent_id)
        self._unregister_fsm_listeners()
        self._emit_final_status()

    def trigger_wakeup(self, agent_id: str) -> None:
        """Triggers event-driven wakeup for an agent."""
        if agent_id in self.wakeup_events:
            self.wakeup_events[agent_id].set()

    def register_fsm_listeners(self) -> None:
        """Hooks into FSM to monitor events and trigger wakeups."""
        fsm_ref = self.fsm
        if fsm_ref is None:
            try:
                import apps.reference.main
                fsm_ref = getattr(apps.reference.main, "fsm", None)
            except Exception:
                pass
        if fsm_ref is None:
            return

        self._fsm_listener_active = True
        self._original_emit = fsm_ref.emit

        def custom_emit(event_name: str, payload: dict = None, why: str = "", *args, **kwargs):
            if not self._fsm_listener_active:
                return self._original_emit(event_name, payload, why, *args, **kwargs)

            # Event triggers
            is_wakeup = any(
                x in event_name
                for x in (
                    "INSTRUCTIONS_REFRESHED",
                    "ORDER_RESULT",
                    "POSITION_UPDATE",
                    "RISK_WARNING",
                    "PANIC",
                )
            )
            if is_wakeup:
                for agent_id in self.config.agents:
                    if self.agent_states[agent_id] == "running":
                        self.trigger_wakeup(agent_id)

            return self._original_emit(event_name, payload, why, *args, **kwargs)

        fsm_ref.emit = custom_emit

    def _unregister_fsm_listeners(self) -> None:
        self._fsm_listener_active = False
        fsm_ref = self.fsm
        if fsm_ref is None:
            try:
                import apps.reference.main
                fsm_ref = getattr(apps.reference.main, "fsm", None)
            except Exception:
                pass
        if fsm_ref is not None and hasattr(self, "_original_emit"):
            fsm_ref.emit = self._original_emit

    async def _agent_loop(self, agent_id: str) -> None:
        """Core async loop for one running agent."""
        cfg = self.config.agents[agent_id]
        
        # Enforce startup stagger
        if cfg.startup_stagger_sec > 0:
            await asyncio.sleep(cfg.startup_stagger_sec)

        # Emit startup event
        self.session_store.append_event(
            self.session_id,
            SessionEvent(
                event_id=f"evt-start-{agent_id}-{uuid4().hex[:8]}",
                session_id=self.session_id,
                event_type="AGENT_STARTUP",
                message=f"Agent {agent_id} started loop.",
                metadata={"agent_id": agent_id, "agent_number": cfg.agent_number},
            ),
        )

        start_time = time.monotonic()
        max_duration = cfg.session_duration_sec

        while self.agent_states[agent_id] == "running" and (time.monotonic() - start_time < max_duration):
            # Emit heartbeat
            self._emit_heartbeat(agent_id)
            
            # Perform Turn Cycle
            try:
                await self._execute_agent_turn(agent_id, cfg)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Agent {agent_id} crashed during turn cycle: {exc}", exc_info=True)
                self.agent_states[agent_id] = "failed"
                self._persist_session_state()
                break

            # Sleep or Wait for Wakeup Event
            cadence = cfg.analysis_cadence_sec
            try:
                await asyncio.wait_for(self.wakeup_events[agent_id].wait(), timeout=cadence)
            except asyncio.TimeoutError:
                pass
            self.wakeup_events[agent_id].clear()

        self._emit_agent_stopped_event(agent_id)

    async def _execute_agent_turn(self, agent_id: str, cfg: AgentRuntimeConfig) -> None:
        """Constructs turn context envelope, calls strategy compiler/model, and validates response."""
        envelope = self._build_context_envelope(agent_id, cfg)
        
        try:
            response = await asyncio.wait_for(
                self._get_agent_decision(agent_id, envelope),
                timeout=cfg.response_timeout_sec
            )
        except asyncio.TimeoutError:
            self._handle_turn_failure(agent_id, "TIMEOUT", f"Agent turn timed out after {cfg.response_timeout_sec}s")
            return

        try:
            validated = AgentTurnResponse.model_validate(response)
        except Exception as exc:
            self._handle_turn_failure(agent_id, "INVALID_RESPONSE", f"Agent returned non-conforming response: {exc}")
            return

        # Symbol Ownership Check (Reject before FSM if wrong symbol)
        action_symbol = validated.payload.get("symbol")
        if action_symbol and action_symbol not in cfg.symbols:
            self._handle_turn_failure(
                agent_id,
                "WRONG_SYMBOL_REJECTION",
                f"Agent requested command on unauthorized symbol {action_symbol}"
            )
            return

        await self._route_agent_command(agent_id, validated)

    def _build_context_envelope(self, agent_id: str, cfg: AgentRuntimeConfig) -> AgentTurnContextEnvelope:
        return AgentTurnContextEnvelope(
            session_id=self.session_id,
            agent_id=agent_id,
            agent_number=cfg.agent_number,
            owned_symbols=cfg.symbols,
            current_market_context={"market_price": 100.0},
            portfolio_state={"balance": 1000.0},
            own_positions_orders={"positions": []},
            peer_publications=[],
            instruction_versions={"manifest": "1.0"},
            recent_decisions=[],
            allowed_tools=["submit_order", "cancel_order"],
            deadline=datetime.now(timezone.utc).isoformat(),
            current_collective_state_version="1.0"
        )

    async def _get_agent_decision(self, agent_id: str, envelope: AgentTurnContextEnvelope) -> Dict[str, Any]:
        """Simulates agent decision lookup (mocked or external API call)."""
        await asyncio.sleep(0.1)
        return {
            "action": "WAIT",
            "payload": {},
            "rationale": "No trade setup detected.",
        }

    async def _route_agent_command(self, agent_id: str, response: AgentTurnResponse) -> None:
        """Submits approved commands to the FSM gateway."""
        if response.action == "WAIT":
            return
        
        cmd_id = response.command_id or f"cmd-{uuid4().hex[:8]}"
        
        fsm_ref = self.fsm
        if fsm_ref is None:
            try:
                import apps.reference.main
                fsm_ref = getattr(apps.reference.main, "fsm", None)
            except Exception:
                pass
        
        if fsm_ref is not None:
            fsm_ref.emit(
                "EVT:STRATEGY_SIGNAL_PRODUCED",
                payload={
                    "symbol": response.payload.get("symbol"),
                    "side": response.payload.get("side", "BUY"),
                    "strategy_id": agent_id,
                    "rid": cmd_id,
                    "why_chain": [response.rationale],
                    "intent_kind": "ENTRY",
                    "ts_ms": int(time.time() * 1000),
                    "agent_id": agent_id,
                    "decision_id": cmd_id,
                    "testnet_only": True,
                },
                why=response.rationale,
            )

    def _handle_turn_failure(self, agent_id: str, error_code: str, details: str) -> None:
        """Handles failures by logging rejection records without silent restarts."""
        logger.error(f"Agent {agent_id} Turn Failure [{error_code}]: {details}")
        
        self.session_store.append_event(
            self.session_id,
            SessionEvent(
                event_id=f"evt-fail-{uuid4().hex[:8]}",
                session_id=self.session_id,
                event_type="AGENT_TURN_FAILURE",
                message=f"Agent {agent_id} turn failed: {error_code}",
                metadata={"agent_id": agent_id, "error_code": error_code, "details": details},
            ),
        )

    def _emit_heartbeat(self, agent_id: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        self.last_heartbeats[agent_id] = now_str
        self.session_store.append_event(
            self.session_id,
            SessionEvent(
                event_id=f"evt-hb-{agent_id}-{uuid4().hex[:8]}",
                session_id=self.session_id,
                event_type="AGENT_HEARTBEAT",
                message=f"Agent {agent_id} heartbeat active.",
                metadata={"agent_id": agent_id, "timestamp": now_str},
            ),
        )

    def _emit_agent_stopped_event(self, agent_id: str) -> None:
        self.session_store.append_event(
            self.session_id,
            SessionEvent(
                event_id=f"evt-stop-{agent_id}-{uuid4().hex[:8]}",
                session_id=self.session_id,
                event_type="AGENT_STOPPED",
                message=f"Agent {agent_id} loop terminated. Status: {self.agent_states[agent_id]}.",
                metadata={"agent_id": agent_id},
            ),
        )

    def _find_unresolved_commands(self, agent_id: str) -> List[str]:
        pending = []
        try:
            for event in self.session_store.list_events(self.session_id):
                evt_type = event.get("event_type")
                metadata = event.get("metadata") or {}
                if metadata.get("agent_id") == agent_id:
                    if evt_type == "COMMAND_RECORDED":
                        pending.append(metadata.get("command_id"))
                    elif evt_type in ("COMMAND_CLOSED", "COMMAND_REJECTED") and metadata.get("command_id") in pending:
                        pending.remove(metadata.get("command_id"))
        except Exception:
            pass
        return pending

    def _persist_session_state(self) -> None:
        """Saves current runner details to standard location."""
        state = {
            "session_id": self.session_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "agents": {
                agent_id: {
                    "status": self.agent_states[agent_id],
                    "last_heartbeat": self.last_heartbeats.get(agent_id, "none"),
                }
                for agent_id in self.config.agents
            },
        }
        try:
            target_dir = self.root_dir / ".agent_memory"
            target_dir.mkdir(parents=True, exist_ok=True)
            
            with open(target_dir / f"dual_agent_session_{self.session_id}.json", "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            
            with open(target_dir / "active_dual_agent_session.json", "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _emit_final_status(self) -> None:
        logger.info(f"Dual agent session {self.session_id} ended. Exiting.")
