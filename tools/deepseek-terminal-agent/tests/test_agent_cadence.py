from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError

from deepseek_terminal_agent.sessions.agent_cadence import (
    compute_stagger_offset,
    compute_next_refresh,
    should_refresh,
    create_sos_event,
    SOSEvent,
)


def test_compute_stagger_offset():
    # Valid agents 1 to 6
    assert compute_stagger_offset(1) == 0
    assert compute_stagger_offset(2) == 10
    assert compute_stagger_offset(3) == 20
    assert compute_stagger_offset(4) == 30
    assert compute_stagger_offset(5) == 40
    assert compute_stagger_offset(6) == 50

    # Wrap around for agents > 6
    assert compute_stagger_offset(7) == 0
    assert compute_stagger_offset(8) == 10
    assert compute_stagger_offset(12) == 50

    # Exception cases
    with pytest.raises(ValueError):
        compute_stagger_offset(0)
    with pytest.raises(ValueError):
        compute_stagger_offset(-5)


def test_compute_next_refresh():
    session_start = datetime(2026, 7, 9, 10, 0, 0, tzinfo=timezone.utc)

    # At session start (now = 10:00:00)
    now = session_start
    # Agent 1 (offset T+00): first refresh is T+60 (11:00:00) because T+00 is read at start
    assert compute_next_refresh(1, session_start, now) == datetime(
        2026, 7, 9, 11, 0, 0, tzinfo=timezone.utc
    )
    # Agent 2 (offset T+10): first refresh is T+10 (10:10:00)
    assert compute_next_refresh(2, session_start, now) == datetime(
        2026, 7, 9, 10, 10, 0, tzinfo=timezone.utc
    )
    # Agent 6 (offset T+50): first refresh is T+50 (10:50:00)
    assert compute_next_refresh(6, session_start, now) == datetime(
        2026, 7, 9, 10, 50, 0, tzinfo=timezone.utc
    )

    # In the middle of the interval (now = 10:15:00)
    now_mid = session_start + timedelta(minutes=15)
    # Agent 2 (offset T+10): first refresh (10:10) is in past, next is 11:10:00
    assert compute_next_refresh(2, session_start, now_mid) == datetime(
        2026, 7, 9, 11, 10, 0, tzinfo=timezone.utc
    )
    # Agent 6 (offset T+50): first refresh (10:50) is in future, next is 10:50:00
    assert compute_next_refresh(6, session_start, now_mid) == datetime(
        2026, 7, 9, 10, 50, 0, tzinfo=timezone.utc
    )


def test_should_refresh():
    now = datetime(2026, 7, 9, 11, 0, 0, tzinfo=timezone.utc)
    last_refresh = datetime(2026, 7, 9, 10, 0, 0, tzinfo=timezone.utc)
    next_scheduled = datetime(2026, 7, 9, 10, 50, 0, tzinfo=timezone.utc)

    # 1. SOS forces refresh
    assert should_refresh(now, last_refresh, sos_pending=True, next_scheduled=next_scheduled) is True

    # 2. Time reached/passed scheduled refresh
    assert should_refresh(now, last_refresh, sos_pending=False, next_scheduled=next_scheduled) is True

    # 3. Time not yet reached
    future_scheduled = datetime(2026, 7, 9, 11, 10, 0, tzinfo=timezone.utc)
    assert should_refresh(now, last_refresh, sos_pending=False, next_scheduled=future_scheduled) is False

    # 4. Fallback behavior (no next_scheduled provided)
    # now is 11:00:00, last_refresh is 10:00:00. Difference is exactly 60m. Should refresh.
    assert should_refresh(now, last_refresh, sos_pending=False) is True
    # now is 10:59:00. Difference is 59m. Should not refresh.
    assert should_refresh(now - timedelta(minutes=1), last_refresh, sos_pending=False) is False


def test_create_sos_event():
    ts = datetime(2026, 7, 9, 10, 30, 0, tzinfo=timezone.utc)
    event_dict = create_sos_event(
        agent_id="agent-6",
        reason="Extreme volatility detected in BTC/USD",
        market_snapshot_ref="snapshot://btc-usd-volatility-1030",
        timestamp=ts,
    )

    assert event_dict["agent_id"] == "agent-6"
    assert event_dict["reason"] == "Extreme volatility detected in BTC/USD"
    assert event_dict["market_snapshot_ref"] == "snapshot://btc-usd-volatility-1030"
    assert event_dict["timestamp"] == ts
    assert event_dict["active"] is True
    assert "sos_id" in event_dict

    # Check Pydantic validation on bad payload
    with pytest.raises(ValidationError):
        SOSEvent(agent_id="", reason="Valid", market_snapshot_ref="Valid")
    with pytest.raises(ValidationError):
        SOSEvent(agent_id="agent-6", reason="", market_snapshot_ref="Valid")
