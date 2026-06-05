"""Phase 9.0 validation: Determinism proof for close-submission contour."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from typing import Any

import pytest

from apps.reference.domains.execution_position.flows.close.close_replay_determinism import (
    DeterminismProof,
    deterministic_close_bridge,
    deterministic_close_submission,
    hash_normalized,
)
from vfoundation.core.protocol import Message


def _cmd_close_message(
    *,
    rid: str,
    symbol: str,
    qty: str | None = None,
    idempotent_key: str | None = None,
    reason: str = "manual_close",
) -> Message:
    """Helper to create CMD:CLOSE messages."""
    payload: dict[str, object] = {
        "symbol": symbol,
        "reason": reason,
    }
    if qty is not None:
        payload["qty"] = qty
    if idempotent_key is not None:
        payload["idempotent_key"] = idempotent_key
    return Message(
        op="CMD",
        verb="CLOSE",
        src="decision_making",
        dst="execution_position",
        rid=rid,
        pld=payload,
        why=reason,
    )


class TestCloseBridgeDeterminism:
    """Prove that bridge derivation is deterministic."""

    @pytest.mark.parametrize(
        "test_case",
        [
            {
                "name": "full_close_long",
                "symbol": "BTCUSDT",
                "qty": None,
                "idempotent_key": "idem-bridge-1",
            },
            {
                "name": "full_close_short",
                "symbol": "ETHUSDT",
                "qty": None,
                "idempotent_key": "idem-bridge-2",
            },
            {
                "name": "partial_close",
                "symbol": "SOLUSDT",
                "qty": "0.5",
                "idempotent_key": "idem-bridge-3",
            },
            {
                "name": "various_symbols",
                "symbol": "XRPUSDT",
                "qty": "0.1",
                "idempotent_key": "idem-bridge-4",
            },
        ],
    )
    def test_bridge_repeated_derivation_identical_output(self, test_case: dict[str, Any]) -> None:
        """Run bridge derivation 5 times with identical input; assert all outputs hash identically."""
        cmd_close = _cmd_close_message(
            rid=f"RID-{test_case['name']}",
            symbol=test_case["symbol"],
            qty=test_case.get("qty"),
            idempotent_key=test_case.get("idempotent_key"),
        )

        proof = DeterminismProof(f"bridge_{test_case['name']}")

        for run_id in range(5):
            payload, error = deterministic_close_bridge(cmd_close)

            # Normalize and hash the output
            if payload is not None:
                output_dict = payload.model_dump()
                output_hash = hash_normalized(output_dict)
                error_hash = None
            else:
                output_hash = hash_normalized({"error": error})
                error_hash = error

            input_hash = hash_normalized(cmd_close.pld)
            proof.add_run(run_id, input_hash, output_hash, error_hash)

        assert proof.verdict(
        ) == "PROVEN_DETERMINISTIC", f"Bridge derivation is not deterministic: {proof.to_dict()}"

    def test_bridge_same_rid_different_idempotent_keys_produce_different_outputs(self) -> None:
        """Verify that different idempotent keys produce different DEC:CLOSE payloads."""
        msg1 = _cmd_close_message(
            rid="RID-SAME",
            symbol="BTCUSDT",
            idempotent_key="idem-1",
        )
        msg2 = _cmd_close_message(
            rid="RID-SAME",
            symbol="BTCUSDT",
            idempotent_key="idem-2",
        )

        payload1, _ = deterministic_close_bridge(msg1)
        payload2, _ = deterministic_close_bridge(msg2)

        assert payload1 is not None and payload2 is not None
        # Different idempotent keys must produce different DEC:CLOSE payloads
        # (identity must be preserved)
        hash1 = hash_normalized(payload1.model_dump())
        hash2 = hash_normalized(payload2.model_dump())
        assert hash1 != hash2, "Different idempotent keys should produce different outputs"

    def test_bridge_invalid_symbol_fails_closed(self) -> None:
        """Verify that invalid symbol input fails gracefully (no guessing)."""
        msg = Message(
            op="CMD",
            verb="CLOSE",
            src="decision_making",
            dst="execution_position",
            rid="RID-INVALID",
            pld={},  # Empty payload: no symbol
            why="test",
        )

        payload, error = deterministic_close_bridge(msg)

        assert payload is None
        assert error is not None
        assert "symbol" in error.lower() or "close" in error.lower()


class TestCloseSubmissionDeterminism:
    """Prove that submission derivation is deterministic."""

    @pytest.mark.parametrize(
        "test_case",
        [
            {
                "name": "full_long",
                "symbol": "BTCUSDT",
                "position_amt": Decimal("1.5"),
                "requested_qty": None,
                "idempotent_key": "idem-sub-1",
            },
            {
                "name": "full_short",
                "symbol": "ETHUSDT",
                "position_amt": Decimal("-2.0"),
                "requested_qty": None,
                "idempotent_key": "idem-sub-2",
            },
            {
                "name": "partial_long",
                "symbol": "SOLUSDT",
                "position_amt": Decimal("5.0"),
                "requested_qty": Decimal("2.5"),
                "idempotent_key": "idem-sub-3",
            },
            {
                "name": "partial_short",
                "symbol": "XRPUSDT",
                "position_amt": Decimal("-10.0"),
                "requested_qty": Decimal("3.0"),
                "idempotent_key": "idem-sub-4",
            },
        ],
    )
    def test_submission_repeated_derivation_identical_output(self, test_case: dict[str, Any]) -> None:
        """Run submission derivation 5 times with identical inputs; assert all outputs hash identically."""
        payload_dict = {
            "symbol": test_case["symbol"],
            "idempotent_key": test_case["idempotent_key"],
        }

        proof = DeterminismProof(f"submission_{test_case['name']}")

        for run_id in range(5):
            payload, error = deterministic_close_submission(
                payload_dict,
                position_amt=test_case["position_amt"],
                requested_qty=test_case.get("requested_qty"),
                idempotent_key=test_case["idempotent_key"],
                symbol=test_case["symbol"],
            )

            if payload is not None:
                output_dict = payload.model_dump()
                output_hash = hash_normalized(output_dict)
                error_hash = None
            else:
                output_hash = hash_normalized({"error": error})
                error_hash = error

            input_hash = hash_normalized({
                "position_amt": str(test_case["position_amt"]),
                "requested_qty": str(test_case.get("requested_qty")) if test_case.get("requested_qty") else None,
                "symbol": test_case["symbol"],
                "idempotent_key": test_case["idempotent_key"],
            })
            proof.add_run(run_id, input_hash, output_hash, error_hash)

        assert proof.verdict(
        ) == "PROVEN_DETERMINISTIC", f"Submission derivation is not deterministic: {proof.to_dict()}"

    def test_submission_position_sign_determines_side(self) -> None:
        """Verify that position sign deterministically determines side."""
        dec_payload = {"symbol": "BTCUSDT", "idempotent_key": "idem-sign"}

        # Long position -> SELL
        long_sub, _ = deterministic_close_submission(
            dec_payload,
            position_amt=Decimal("1.0"),
            idempotent_key="idem-sign",
            symbol="BTCUSDT",
        )
        assert long_sub is not None
        assert long_sub.side == "SELL"

        # Short position -> BUY
        short_sub, _ = deterministic_close_submission(
            dec_payload,
            position_amt=Decimal("-1.0"),
            idempotent_key="idem-sign",
            symbol="BTCUSDT",
        )
        assert short_sub is not None
        assert short_sub.side == "BUY"

    def test_submission_zero_position_fails_closed(self) -> None:
        """Verify that zero position fails gracefully (no guessing)."""
        payload, error = deterministic_close_submission(
            {"symbol": "BTCUSDT", "idempotent_key": "idem-zero"},
            position_amt=Decimal("0"),
            idempotent_key="idem-zero",
            symbol="BTCUSDT",
        )

        assert payload is None
        assert error is not None


class TestEndToEndBridgePlusSubmission:
    """Prove bridge + submission together form a deterministic contour."""

    def test_full_close_path_deterministic_long_position(self) -> None:
        """Full bridge + submission for long position close."""
        cmd_close = _cmd_close_message(
            rid="RID-FULL-LONG",
            symbol="BTCUSDT",
            qty=None,
            idempotent_key="idem-full-long",
        )
        position_amt = Decimal("2.0")

        # Run the complete path twice
        results: list[tuple[str, str]] = []

        for _ in range(2):
            # Stage 1: Bridge
            bridge_payload, bridge_error = deterministic_close_bridge(
                cmd_close)
            assert bridge_payload is not None and bridge_error is None
            bridge_dict = bridge_payload.model_dump()
            bridge_hash = hash_normalized(bridge_dict)

            # Stage 2: Submission
            submission_payload, submission_error = deterministic_close_submission(
                bridge_dict,
                position_amt=position_amt,
                idempotent_key="idem-full-long",
                symbol="BTCUSDT",
            )
            assert submission_payload is not None and submission_error is None
            submission_dict = submission_payload.model_dump()
            submission_hash = hash_normalized(submission_dict)

            results.append((bridge_hash, submission_hash))

        # Both runs should produce identical hashes
        assert results[0] == results[1], "End-to-end path is not deterministic"

    def test_full_close_path_deterministic_short_partial(self) -> None:
        """Full bridge + submission for short position partial close."""
        cmd_close = _cmd_close_message(
            rid="RID-PARTIAL-SHORT",
            symbol="ETHUSDT",
            qty="1.5",
            idempotent_key="idem-partial-short",
        )
        position_amt = Decimal("-5.0")
        requested_qty = Decimal("1.5")

        # Run twice and compare hashes
        results: list[tuple[str, str]] = []

        for _ in range(2):
            bridge_payload, _ = deterministic_close_bridge(cmd_close)
            assert bridge_payload is not None
            bridge_hash = hash_normalized(bridge_payload.model_dump())

            submission_payload, _ = deterministic_close_submission(
                bridge_payload.model_dump(),
                position_amt=position_amt,
                requested_qty=requested_qty,
                idempotent_key="idem-partial-short",
                symbol="ETHUSDT",
            )
            assert submission_payload is not None
            submission_hash = hash_normalized(submission_payload.model_dump())

            results.append((bridge_hash, submission_hash))

        # All results must match
        assert results[0] == results[1], "Partial close path is not deterministic"


class TestDeterminismProof:
    """Unit tests for the DeterminismProof container."""

    def test_proof_container_tracks_matches(self) -> None:
        """Verify proof container correctly tracks determinism verdict."""
        proof = DeterminismProof("test")

        proof.add_run(1, "input1", "output_a", None)
        assert proof.verdict() == "PROVEN_DETERMINISTIC"

        proof.add_run(2, "input1", "output_a", None)
        assert proof.verdict() == "PROVEN_DETERMINISTIC"

        proof.add_run(3, "input1", "output_b", None)  # Mismatch
        assert proof.verdict() == "INDETERMINATE_NONDETERMINISTIC"

    def test_hash_normalized_stable(self) -> None:
        """Verify that hashing is stable (same input -> same hash)."""
        value = {"symbol": "BTCUSDT", "qty": "1.5", "idem": "key1"}
        hash1 = hash_normalized(value)
        hash2 = hash_normalized(value)
        assert hash1 == hash2

    def test_hash_normalized_decimal(self) -> None:
        """Verify that Decimal values are hashed stably."""
        # Note: Decimal("1.5") and Decimal("1.50") are equal but may have different representations
        # We normalize by converting to string, so we use the same Decimal value
        value1 = {"qty": Decimal("1.5")}
        value2 = {"qty": Decimal("1.5")}
        hash1 = hash_normalized(value1)
        hash2 = hash_normalized(value2)
        assert hash1 == hash2
