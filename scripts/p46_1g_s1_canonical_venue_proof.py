"""One bounded P46-1G-S1 Testnet proof with no harness-to-adapter fallback."""
from __future__ import annotations

import asyncio
import json
import os
import socket
import tempfile
import threading
import time
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from apps.reference.adapters.binance_adapter import BinanceAdapter
from apps.reference.bootstrap.async_runtime import AsyncLoopRuntime
from apps.reference.config.testnet_proof import load_p46_testnet_proof_config
from apps.reference.domains.execution_position.guards.leverage_service import (
    LeverageService,
)
from scripts.p46_1g_r_canonical_venue_proof import (
    P46_1G_R_ProofHarness,
    ROOT,
    TESTNET_BASE_URL,
    _abort_on_mainnet,
)
from scripts.p46_1g_testnet_preflight import run_read_only_preflight
from vfoundation.core.fsm_emit_compat import Message


class ObservedCanonicalHarness(P46_1G_R_ProofHarness):
    def __init__(
        self,
        root_dir: Path,
        *,
        proof_session_id: str,
        symbol: str,
        authoritative_equity: Decimal,
        reference_price: Decimal,
        target_notional: Decimal,
        operator_cap: Decimal,
    ) -> None:
        super().__init__(root_dir, proof_session_id=proof_session_id)
        self._authoritative_equity = authoritative_equity
        self._operator_cap = operator_cap
        self._adapter_submit_calls = 0
        self._async_dispatch_calls = 0
        self._opening_async_dispatch_calls = 0
        self._cleanup_async_dispatch_calls = 0
        self._adapter_cancel_calls = 0
        self._adapter_close_calls = 0
        self._opening_result: dict[str, Any] | None = None
        self._cleanup_result: Any = None
        self.emergency_containment_used = False
        self._opening_done = threading.Event()
        self._cleanup_done = threading.Event()
        self.execution_fsm.leverage_service = LeverageService(self.real_adapter)
        self.execution_fsm.is_live_execution = True

        spec = self.config.instruments[symbol]
        leverage = Decimal(str(spec.execution.target_leverage))
        fee_buffer = Decimal(str(spec.sizing.fee_buffer_fraction))
        margin_pct = target_notional / (
            authoritative_equity * (Decimal("1") - fee_buffer) * leverage
        )
        if margin_pct <= 0 or margin_pct > 1:
            raise RuntimeError("proof sizing margin_pct is outside (0, 1]")
        # Explicit test-only projection of p46_1g_testnet_proof.yaml into the
        # already validated temporary Pydantic config used by PositionQueries.
        spec.sizing.margin_pct = float(margin_pct)

        self.decision_fixture.latest_portfolio = {
            "equity": str(authoritative_equity),
            "positions": [],
            "ts_ms": int(time.time() * 1000),
        }
        self.decision_fixture.latest_portfolio_ref = (
            f"account:{proof_session_id}:testnet"
        )
        self.decision_fixture.symbol_states = {
            symbol: {
                "current_price": str(reference_price),
                "snapshot_ref": f"market:{proof_session_id}:testnet",
                "timestamp_ms": int(time.time() * 1000),
            }
        }
        self._seed_real_portfolio(authoritative_equity)

        self.async_runtime = AsyncLoopRuntime(name="P46S1CanonicalExecutionLoop")
        loop = self.async_runtime.start()
        self.execution_fsm.set_async_loop(loop)
        self._observe_async_dispatch()
        self._install_observers()

    def _observe_async_dispatch(self) -> None:
        original_submit = self.execution_fsm._submit_async

        def observed_submit(coro, loop=None):
            code = getattr(coro, "cr_code", None)
            if code is not None and code.co_name == "_execute_decision":
                self._async_dispatch_calls += 1
                frame = getattr(coro, "cr_frame", None)
                decision = frame.f_locals.get("decision") if frame is not None else None
                if getattr(decision, "verb", None) == "OPEN":
                    self._opening_async_dispatch_calls += 1
                else:
                    self._cleanup_async_dispatch_calls += 1
            return original_submit(coro, loop)

        self.execution_fsm._submit_async = observed_submit

    def _seed_real_portfolio(self, equity: Decimal) -> None:
        now_ms = int(time.time() * 1000)
        self.bus.emit("EVT:PORTFOLIO_STATE_UPDATED", {
            "ts": now_ms,
            "equity": str(equity),
            "equity_free_usdt": str(equity),
            "equity_cross_usdt": str(equity),
            "equity_ts": now_ms,
            "realized_pnl": "0",
            "unrealized_pnl": "0",
            "available_balance": str(equity),
            "open_positions_usd": "0",
            "open_positions_margin_usd": "0",
            "positions_by_side": {"long_margin": "0", "short_margin": "0"},
            "positions_last_ts_ms": now_ms,
            "positions": [],
        }, "p46_1g_s1_authoritative_account_snapshot")

    def _install_observers(self) -> None:
        adapter = self.real_adapter
        original_limit = adapter.place_limit_entry
        original_market = adapter.place_market_entry
        original_cancel = adapter.cancel_order
        original_close = adapter.place_market_reduce_only

        async def observed_limit(*args, **kwargs):
            self._adapter_submit_calls += 1
            result = await original_limit(*args, **kwargs)
            self._opening_result = dict(result)
            self._opening_done.set()
            return result

        async def observed_market(*args, **kwargs):
            self._adapter_submit_calls += 1
            result = await original_market(*args, **kwargs)
            self._opening_result = dict(result)
            self._opening_done.set()
            return result

        async def observed_cancel(*args, **kwargs):
            self._adapter_cancel_calls += 1
            result = await original_cancel(*args, **kwargs)
            self._cleanup_result = result
            self._cleanup_done.set()
            return result

        async def observed_close(*args, **kwargs):
            self._adapter_close_calls += 1
            result = await original_close(*args, **kwargs)
            self._cleanup_result = result
            self._cleanup_done.set()
            return result

        adapter.place_limit_entry = observed_limit
        adapter.place_market_entry = observed_market
        adapter.cancel_order = observed_cancel
        adapter.place_market_reduce_only = observed_close

    def send_tcp(self, payload: dict[str, Any]) -> None:
        endpoint = self.config.domains.shadow_telemetry.egress_to_main.ipc_commands_endpoint
        host_port = endpoint.removeprefix("tcp://")
        host, port_text = host_port.rsplit(":", 1)
        with socket.create_connection((host, int(port_text)), timeout=2) as sock:
            sock.sendall(
                (json.dumps(payload, separators=(",", ":")) + "\n").encode("ascii")
            )

    def dispatch_cleanup(self, *, symbol: str, order: dict[str, Any]) -> str:
        status = str(order.get("status") or "")
        filled_qty = Decimal(str(order.get("executedQty") or "0"))
        order_id = str(order.get("orderId") or "")
        if status in {"NEW", "PARTIALLY_FILLED"} and filled_qty == 0:
            decision = Message(
                op="DEC",
                verb="CANCEL_ORDER",
                src="p46_1g_s1_reconciliation",
                dst="execution_position",
                rid=f"cancel-{self.evidence.client_intent_id}",
                pld={"symbol": symbol, "order_id": order_id},
                why="p46_1g_s1_cancel_unfilled",
            )
            self.execution_fsm._process_flow_result(decision)
            return "canonical_cancel_unfilled"

        position_qty = self.async_runtime.run(
            self._position_amount(symbol), timeout=10.0
        )
        if position_qty == 0:
            return "venue_already_flat"
        close_side = "SELL" if position_qty > 0 else "BUY"
        decision = Message(
            op="DEC",
            verb="CLOSE",
            src="p46_1g_s1_reconciliation",
            dst="execution_position",
            rid=f"close-{self.evidence.client_intent_id}",
            pld={
                "symbol": symbol,
                "side": close_side,
                "qty": str(abs(position_qty)),
                "reduce_only": True,
                "idempotent_key": f"close-{self.evidence.client_intent_id}",
                "trigger": "CMD:CLOSE",
            },
            why="p46_1g_s1_close_filled",
        )
        self.execution_fsm._process_flow_result(decision)
        return "canonical_close_filled"

    async def _position_amount(self, symbol: str) -> Decimal:
        positions = await self.real_adapter.get_open_positions(symbol)
        for position in positions:
            if position.symbol == symbol:
                return Decimal(str(position.position_amount))
        return Decimal("0")

    def contain_after_failure(self, symbol: str) -> None:
        """Contain only this proof's venue state; direct calls are emergency-only."""
        try:
            if self._opening_result:
                order_id = int(self._opening_result["orderId"])
                order = self.async_runtime.run(
                    self.real_adapter.get_order(symbol, order_id), timeout=10.0
                )
                self.dispatch_cleanup(symbol=symbol, order=order)
                self._cleanup_done.wait(timeout=15.0)
            position = self.async_runtime.run(
                self._position_amount(symbol), timeout=10.0
            )
            proof_client_id = str(
                (self._opening_result or {}).get("clientOrderId") or ""
            )
            orders = self.async_runtime.run(
                self.real_adapter.get_open_orders_raw(symbol), timeout=10.0
            )
            proof_orders = [
                item for item in orders
                if proof_client_id and str(item.get("clientOrderId") or "") == proof_client_id
            ]
            if position == 0 and not proof_orders:
                return

            self.emergency_containment_used = True
            for item in proof_orders:
                self.async_runtime.run(
                    self.real_adapter.cancel_order(
                        symbol=symbol, order_id=str(item["orderId"])
                    ),
                    timeout=10.0,
                )
            if position != 0:
                self.async_runtime.run(
                    self.real_adapter.place_market_reduce_only(
                        symbol=symbol,
                        side="SELL" if position > 0 else "BUY",
                        quantity=str(abs(position)),
                        new_client_order_id=f"emg{uuid.uuid4().hex[:20]}",
                    ),
                    timeout=15.0,
                )
        except Exception:
            self.emergency_containment_used = True
            raise

    def stop(self) -> None:
        super().stop()
        try:
            self.async_runtime.run(self.real_adapter.aclose(), timeout=5.0)
        finally:
            self.async_runtime.stop()


async def read_preflight(proof_config) -> dict[str, Any]:
    _abort_on_mainnet(TESTNET_BASE_URL)
    adapter = BinanceAdapter(
        api_key=os.environ["BINANCE_TESTNET_API_KEY"],
        api_secret=os.environ["BINANCE_TESTNET_API_SECRET"],
        base_url=TESTNET_BASE_URL,
    )
    try:
        server_time = await adapter._server_time()
        balances = await adapter.get_account_balance()
        equity = None
        for balance in balances:
            if isinstance(balance, dict) and balance.get("asset") == "USDT":
                equity = Decimal(str(balance.get("balance") or "0"))
                break
        if equity is None or equity <= 0:
            raise RuntimeError("authoritative USDT equity is unavailable")

        positions = {
            item.symbol: Decimal(str(item.position_amount))
            for item in await adapter.get_open_positions()
        }
        target = Decimal(str(proof_config.exposure.target_notional_quote))
        cap = Decimal(str(proof_config.exposure.operator_max_notional_quote))
        ordered_symbols = [
            proof_config.symbol_selection.preferred_symbol,
            *(
                symbol for symbol in proof_config.symbol_selection.allowed_symbols
                if symbol != proof_config.symbol_selection.preferred_symbol
            ),
        ]
        clip_min = load_clip_min_notional()
        for symbol in ordered_symbols:
            if abs(positions.get(symbol, Decimal("0"))) > 0:
                continue
            if await adapter.get_open_orders_raw(symbol):
                continue
            ticker = await adapter.get_book_ticker(symbol)
            ask = Decimal(str(ticker["askPrice"]))
            spec = load_instrument(symbol)
            min_notional = Decimal(str(spec["min_notional"]))
            if min_notional > target or min_notional > cap:
                continue
            step_size = Decimal(str(spec["step_size"]))
            rounded_qty = (target / ask / step_size).to_integral_value(
                rounding="ROUND_DOWN"
            ) * step_size
            rounded_notional = rounded_qty * ask
            if rounded_qty < Decimal(str(spec["min_qty"])):
                continue
            if rounded_notional < max(min_notional, clip_min):
                continue
            return {
                "server_time_ms": server_time,
                "symbol": symbol,
                "equity": equity,
                "reference_price": ask,
                "target": target,
                "cap": cap,
                "preflight_rounded_quantity": rounded_qty,
                "preflight_rounded_notional": rounded_notional,
                "clip_min_notional": clip_min,
            }
        raise RuntimeError("no clean configured symbol satisfies the proof cap")
    finally:
        await adapter.aclose()


def load_instrument(symbol: str) -> dict[str, Any]:
    import yaml

    data = yaml.safe_load(
        (ROOT / "config/aurora/instruments.yaml").read_text(encoding="utf-8")
    )
    return dict(data["instruments"][symbol])


def load_clip_min_notional() -> Decimal:
    import yaml

    data = yaml.safe_load(
        (ROOT / "config/aurora/trading.yaml").read_text(encoding="utf-8")
    )
    return Decimal(str(
        data["trading"]["risk"]["soft_limits"]["clip_min_notional_usdt"]
    ))


def run() -> dict[str, Any]:
    proof_config = load_p46_testnet_proof_config(
        ROOT / "config/aurora/p46_1g_testnet_proof.yaml"
    )
    preflight_gate = run_read_only_preflight(proof_config, os.environ)
    if not preflight_gate.allowed:
        raise RuntimeError(f"preflight rejected: {preflight_gate.reason_code}")
    preflight = asyncio.run(read_preflight(proof_config))
    session_id = f"p46-1g-s1-{uuid.uuid4().hex[:12]}"
    result: dict[str, Any] = {
        "session_id": session_id,
        "symbol": preflight["symbol"],
        "endpoint": preflight_gate.endpoint_host,
        "caller_quantity_present": False,
    }

    with tempfile.TemporaryDirectory(prefix="p46_1g_s1_") as tmp_dir:
        harness = ObservedCanonicalHarness(
            Path(tmp_dir),
            proof_session_id=session_id,
            symbol=preflight["symbol"],
            authoritative_equity=preflight["equity"],
            reference_price=preflight["reference_price"],
            target_notional=preflight["target"],
            operator_cap=preflight["cap"],
        )
        lease_id = harness._acquire_lease(preflight["symbol"])
        result["lease_id"] = lease_id
        harness.start()
        try:
            payload = harness._make_intent_payload(
                preflight["symbol"], lease_id, intent_id=harness.evidence.client_intent_id
            )
            response = harness._post_intent(payload)
            if response.status_code != 202:
                raise RuntimeError(f"V2 HTTP rejected: {response.status_code}")
            if not harness._opening_done.wait(
                timeout=proof_config.timeouts.submit_ack_timeout_sec
            ):
                raise RuntimeError("canonical adapter submit did not complete")
            command = harness.command_emissions[0][1]
            derived_qty = Decimal(str(command["qty"]))
            derived_notional = derived_qty * preflight["reference_price"]
            if derived_notional > preflight["cap"]:
                raise RuntimeError("derived notional exceeded operator cap")

            duplicate = harness._post_intent(payload)
            if duplicate.status_code not in (200, 202):
                raise RuntimeError("duplicate HTTP intent was not idempotent")
            if len(harness.command_emissions) != 1 or harness._adapter_submit_calls != 1:
                raise RuntimeError("duplicate intent caused another adapter submit")

            opening = dict(harness._opening_result or {})
            order_id = int(opening["orderId"])
            order = harness.async_runtime.run(
                harness.real_adapter.get_order(preflight["symbol"], order_id),
                timeout=proof_config.timeouts.venue_query_timeout_sec,
            )
            cleanup_path = harness.dispatch_cleanup(
                symbol=preflight["symbol"], order=order
            )
            if cleanup_path != "venue_already_flat" and not harness._cleanup_done.wait(
                timeout=proof_config.timeouts.flatten_timeout_sec
            ):
                raise RuntimeError("canonical cleanup did not complete")

            final_position = harness.async_runtime.run(
                harness._position_amount(preflight["symbol"]), timeout=10.0
            )
            final_orders = harness.async_runtime.run(
                harness.real_adapter.get_open_orders_raw(preflight["symbol"]),
                timeout=10.0,
            )
            result.update({
                "participant_id": f"{session_id}-main",
                "client_intent_id": harness.evidence.client_intent_id,
                "sizing_decision_id": command["sizing_decision_id"],
                "exposure_decision_id": (
                    command.get("exposure_decision_id")
                    or f"exposure:{harness.evidence.client_intent_id}"
                ),
                "exposure_decision_id_reconstructed": (
                    command.get("exposure_decision_id") is None
                ),
                "config_version": command["config_version"],
                "reference_price": str(preflight["reference_price"]),
                "target_notional": str(preflight["target"]),
                "operator_cap": str(preflight["cap"]),
                "derived_quantity": str(derived_qty),
                "derived_notional": str(derived_notional),
                "tcp_envelopes": harness.bridge.command_envelope_count,
                "command_handler_calls": len(harness.command_emissions),
                "async_dispatch_calls": harness._opening_async_dispatch_calls,
                "cleanup_async_dispatch_calls": harness._cleanup_async_dispatch_calls,
                "total_async_dispatch_calls": harness._async_dispatch_calls,
                "fsm_handle_calls": len(harness.fsm_ingress),
                "adapter_submit_calls": harness._adapter_submit_calls,
                "exchange_order_id": str(order_id),
                "opening_status": str(order.get("status") or ""),
                "duplicate_submit_count": harness._adapter_submit_calls - 1,
                "cleanup_path": cleanup_path,
                "adapter_cancel_calls": harness._adapter_cancel_calls,
                "adapter_close_calls": harness._adapter_close_calls,
                "final_position": str(final_position),
                "final_open_orders": len(final_orders),
                "reconciliation_divergence": 0 if final_position == 0 and not final_orders else 1,
                "emergency_containment_used": harness.emergency_containment_used,
            })
            if final_position != 0 or final_orders:
                raise RuntimeError("final venue reconciliation is not clean")
        except Exception:
            harness.contain_after_failure(preflight["symbol"])
            raise
        finally:
            harness.stop()
    return result


def main() -> int:
    evidence = run()
    print(json.dumps(evidence, sort_keys=True))
    success = (
        evidence["command_handler_calls"] == 1
        and evidence["fsm_handle_calls"] == 1
        and evidence["adapter_submit_calls"] == 1
        and evidence["duplicate_submit_count"] == 0
        and Decimal(evidence["final_position"]) == 0
        and evidence["final_open_orders"] == 0
        and evidence["reconciliation_divergence"] == 0
        and not evidence["emergency_containment_used"]
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
