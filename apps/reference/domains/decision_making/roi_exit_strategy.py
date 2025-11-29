"""
ROI Exit Strategy (Decision Making).

Monitors portfolio state and triggers CMD:CLOSE when a position's ROI exceeds the target.
Acts as the "Commander" for strategic exits, while Execution Position acts as the "Soldier".
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional, List

from pydantic import ValidationError
from vfoundation.core.protocol import Message
from apps.reference.domains.decision_making.schemas import PortfolioStatePayload, PositionData

LOG = logging.getLogger(__name__)


class ROIExitStrategy:
    """
    Monitors open positions and emits CMD:CLOSE if ROI target is met.
    """

    def __init__(self, target_roi_pct: float = 50.0):
        """
        Args:
            target_roi_pct: Target ROI as a percentage (e.g., 50.0 for 50%).
        """
        # Convert percentage to decimal (50.0 -> 0.50)
        self.target_roi_decimal = Decimal(str(target_roi_pct)) / Decimal("100")
        self._metrics: Dict[str, int] = {
            "roi_close_commands_total": 0,
            "roi_checks_total": 0,
            "validation_errors": 0,
        }

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process EVT:PORTFOLIO_STATE_UPDATED events.

        Returns:
            CMD:CLOSE message if target ROI is met for any position.
            Note: Currently returns only the FIRST close command if multiple positions hit target.
            In a real system, this might need to return a list or emit multiple events.
        """
        if msg.op != "EVT" or msg.verb != "PORTFOLIO_STATE_UPDATED":
            return None

        try:
            payload = PortfolioStatePayload(**(msg.pld or {}))
        except ValidationError as e:
            LOG.warning(f"[ROIExit] Validation error for payload: {e}")
            self._metrics["validation_errors"] += 1
            return None

        for pos in payload.positions:
            cmd = self._check_position_roi(pos, msg)
            if cmd:
                return cmd

        return None

    def _check_position_roi(self, pos: PositionData, trigger_msg: Message) -> Optional[Message]:
        """Check ROI for a single position and generate CMD:CLOSE if needed."""
        self._metrics["roi_checks_total"] += 1
        
        try:
            if pos.positionAmt == 0:
                return None

            if pos.entryPrice <= 0:
                return None

            # Calculate Initial Margin = (Notional Value) / Leverage
            # Notional Value = abs(amt) * entry_price
            initial_margin = (abs(pos.positionAmt) * pos.entryPrice) / pos.leverage

            if initial_margin == 0:
                return None

            # ROI = Unrealized PnL / Initial Margin
            roi = pos.unRealizedProfit / initial_margin

            # Check if ROI meets target
            if roi >= self.target_roi_decimal:
                LOG.info(
                    f"[ROIExit] Triggering CLOSE for {pos.symbol}: ROI {roi:.2%} >= {self.target_roi_decimal:.2%} "
                    f"(PnL: {pos.unRealizedProfit}, Margin: {initial_margin:.2f})"
                )
                self._metrics["roi_close_commands_total"] += 1
                
                return Message(
                    op="CMD",
                    verb="CLOSE",
                    src="decision_making",
                    dst="execution_position",
                    rid=trigger_msg.rid,  # Correlate with the update event
                    why=f"roi_target_met_{roi:.2f}",
                    pld={
                        "symbol": pos.symbol,
                        "reason": "ROI_TARGET_MET",
                        "roi": float(roi),
                        "target_roi": float(self.target_roi_decimal),
                        "reduce_only": True
                    }
                )

        except (InvalidOperation, ValueError, TypeError) as e:
            LOG.warning(f"[ROIExit] Error calculating ROI for {pos.symbol}: {e}")
        
        return None

    def get_metrics(self) -> Dict[str, int]:
        return self._metrics.copy()
