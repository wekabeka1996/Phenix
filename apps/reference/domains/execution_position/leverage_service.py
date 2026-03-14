"""
TASK47c-B: LeverageService for leverage/margin verification.

Provides L0 verification/setting of leverage and margin mode before order execution.
Implements idempotency window to avoid redundant API calls.
"""
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol

from apps.reference.shared.types import NormalizedRejectReasons


LOG = logging.getLogger(__name__)


class LeverageAdapterProtocol(Protocol):
    """Protocol for leverage/margin adapter methods."""

    async def get_current_leverage(self, symbol: str) -> int:
        """Get current leverage for symbol from exchange."""
        ...

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for symbol on exchange. Returns True on success."""
        ...

    async def get_margin_mode(self, symbol: str) -> str:
        """Get current margin mode ('isolated' or 'cross') for symbol."""
        ...

    async def set_margin_mode(self, symbol: str, mode: str) -> bool:
        """Set margin mode for symbol on exchange. Returns True on success."""
        ...


@dataclass
class VerifyResult:
    """Result of leverage/margin verification.

    Provides detailed context for debugging and NRR mapping.
    """
    ok: bool
    actual_leverage: Optional[int]
    actual_margin_mode: Optional[str]  # "isolated" | "cross" | None
    expected_leverage: int
    expected_margin_mode: str  # "isolated" | "cross"
    why: str  # Max 80 chars, human-readable reason
    error_code: Optional[str]  # NRR code for reject mapping


@dataclass
class _IdempotencyEntry:
    """Internal cache entry for idempotency."""
    leverage: int
    margin_mode: str
    timestamp: float


class LeverageService:
    """Service for verifying and setting leverage/margin mode on exchange.

    TASK47c-B: L0 integration point for execution_position.

    Features:
    - verify(): Check current exchange settings match expected
    - set_and_verify(): Set margin mode + leverage, then verify
    - Idempotency window: Skip redundant set calls within window_sec
    - Fail-closed: Any adapter error → reject order

    Usage:
        service = LeverageService(adapter, clock=time.time, idempotency_window_sec=60)
        result = await service.verify(symbol, expected_leverage, expected_margin_mode)
        if not result.ok:
            reject_order(reason=result.error_code, why=result.why)
    """

    def __init__(
        self,
        adapter: Any,  # LeverageAdapterProtocol, but accept any for flexibility
        clock: Callable[[], float] = time.time,
        idempotency_window_sec: int = 60,
    ):
        """Initialize LeverageService.

        Args:
            adapter: Exchange adapter with leverage/margin methods
            clock: Time source for idempotency (default: time.time)
            idempotency_window_sec: Skip redundant sets within this window
        """
        self._adapter = adapter
        self._clock = clock
        self._idempotency_window_sec = idempotency_window_sec
        self._idempotency_cache: Dict[str, _IdempotencyEntry] = {}

    async def verify(
        self,
        symbol: str,
        expected_leverage: int,
        expected_margin_mode: str,
    ) -> VerifyResult:
        """Verify current exchange settings match expected values.

        Always calls exchange to get current values (no caching on verify).
        Fail-closed: Any adapter error → VerifyResult(ok=False, error_code=LEVERAGE_VERIFY_FAILED)

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            expected_leverage: Expected leverage (1-125)
            expected_margin_mode: Expected margin mode ("isolated" or "cross")

        Returns:
            VerifyResult with ok=True if match, ok=False with error details otherwise
        """
        try:
            actual_leverage = await self._adapter.get_current_leverage(symbol)
        except Exception as e:
            LOG.error(
                f"LEVERAGE_SERVICE: get_current_leverage failed for {symbol}: {e}")
            return VerifyResult(
                ok=False,
                actual_leverage=None,
                actual_margin_mode=None,
                expected_leverage=expected_leverage,
                expected_margin_mode=expected_margin_mode,
                why=f"Failed to get leverage: {str(e)[:50]}",
                error_code=NormalizedRejectReasons.LEVERAGE_VERIFY_FAILED,
            )

        try:
            actual_margin_mode = await self._adapter.get_margin_mode(symbol)
        except Exception as e:
            LOG.error(
                f"LEVERAGE_SERVICE: get_margin_mode failed for {symbol}: {e}")
            return VerifyResult(
                ok=False,
                actual_leverage=actual_leverage,
                actual_margin_mode=None,
                expected_leverage=expected_leverage,
                expected_margin_mode=expected_margin_mode,
                why=f"Failed to get margin mode: {str(e)[:50]}",
                error_code=NormalizedRejectReasons.LEVERAGE_VERIFY_FAILED,
            )

        # Check leverage match
        if actual_leverage != expected_leverage:
            return VerifyResult(
                ok=False,
                actual_leverage=actual_leverage,
                actual_margin_mode=actual_margin_mode,
                expected_leverage=expected_leverage,
                expected_margin_mode=expected_margin_mode,
                why=f"Leverage mismatch: actual={actual_leverage}, expected={expected_leverage}",
                error_code=NormalizedRejectReasons.LEVERAGE_MISMATCH,
            )

        # Check margin mode match (normalize to lowercase)
        actual_mode_norm = actual_margin_mode.lower() if actual_margin_mode else None
        expected_mode_norm = expected_margin_mode.lower()

        if actual_mode_norm != expected_mode_norm:
            return VerifyResult(
                ok=False,
                actual_leverage=actual_leverage,
                actual_margin_mode=actual_margin_mode,
                expected_leverage=expected_leverage,
                expected_margin_mode=expected_margin_mode,
                why=f"Margin mode mismatch: actual={actual_margin_mode}, expected={expected_margin_mode}",
                error_code=NormalizedRejectReasons.MARGIN_MODE_MISMATCH,
            )

        # All good
        return VerifyResult(
            ok=True,
            actual_leverage=actual_leverage,
            actual_margin_mode=actual_margin_mode,
            expected_leverage=expected_leverage,
            expected_margin_mode=expected_margin_mode,
            why="OK",
            error_code=None,
        )

    async def set_and_verify(
        self,
        symbol: str,
        expected_leverage: int,
        expected_margin_mode: str,
    ) -> VerifyResult:
        """Set leverage and margin mode on exchange, then verify.

        Idempotent: If same values were set within idempotency_window_sec,
        skip set calls and just verify.

        Order of operations:
        1. Check idempotency cache
        2. Set margin mode (if not cached or expired)
        3. Set leverage (if not cached or expired)
        4. Update cache
        5. Verify settings took effect

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            expected_leverage: Leverage to set (1-125)
            expected_margin_mode: Margin mode to set ("isolated" or "cross")

        Returns:
            VerifyResult with ok=True if successful, ok=False with error details otherwise
        """
        now = self._clock()

        # Check idempotency cache
        cached = self._idempotency_cache.get(symbol)
        skip_set = False

        if cached is not None:
            age = now - cached.timestamp
            same_values = (
                cached.leverage == expected_leverage
                and cached.margin_mode.lower() == expected_margin_mode.lower()
            )
            if age < self._idempotency_window_sec and same_values:
                LOG.debug(
                    f"LEVERAGE_SERVICE: Idempotent skip for {symbol} "
                    f"(age={age:.1f}s < {self._idempotency_window_sec}s)"
                )
                skip_set = True

        if not skip_set:
            # Set margin mode first (required before setting leverage on Binance)
            try:
                await self._adapter.set_margin_mode(symbol, expected_margin_mode)
            except Exception as e:
                LOG.error(
                    f"LEVERAGE_SERVICE: set_margin_mode failed for {symbol}: {e}")
                return VerifyResult(
                    ok=False,
                    actual_leverage=None,
                    actual_margin_mode=None,
                    expected_leverage=expected_leverage,
                    expected_margin_mode=expected_margin_mode,
                    why=f"Failed to set margin mode: {str(e)[:50]}",
                    error_code=NormalizedRejectReasons.MARGIN_MODE_SET_FAILED,
                )

            # Set leverage
            try:
                await self._adapter.set_leverage(symbol, expected_leverage)
            except Exception as e:
                LOG.error(
                    f"LEVERAGE_SERVICE: set_leverage failed for {symbol}: {e}")
                return VerifyResult(
                    ok=False,
                    actual_leverage=None,
                    actual_margin_mode=expected_margin_mode,  # Margin was set
                    expected_leverage=expected_leverage,
                    expected_margin_mode=expected_margin_mode,
                    why=f"Failed to set leverage: {str(e)[:50]}",
                    error_code=NormalizedRejectReasons.LEVERAGE_SET_FAILED,
                )

            # Update idempotency cache
            self._idempotency_cache[symbol] = _IdempotencyEntry(
                leverage=expected_leverage,
                margin_mode=expected_margin_mode,
                timestamp=now,
            )

        # Verify settings took effect
        return await self.verify(symbol, expected_leverage, expected_margin_mode)
