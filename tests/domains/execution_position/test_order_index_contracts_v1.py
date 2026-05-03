import pytest
import time
from apps.reference.domains.execution_position.state.order_index import OrderIndex, OrderRef

@pytest.fixture
def index():
    return OrderIndex(ttl_sec=1)

def test_order_index_upsert_and_get(index):
    """Upsert and retrieve by RID."""
    ref = index.upsert_from_open(
        rid="r1", idempotent_key="k1", clientOrderId="c1", 
        symbol="BTCUSDT", side="BUY", order_type="MARKET"
    )
    assert ref.rid == "r1"
    assert index.get(rid="r1") == ref
    assert index.get(clientOrderId="c1") == ref

def test_order_index_attach_exchange_id(index):
    """Correlate exchange ID."""
    index.upsert_from_open(
        rid="r1", idempotent_key="k1", clientOrderId="c1", 
        symbol="BTCUSDT", side="BUY", order_type="MARKET"
    )
    ref = index.attach_exchange_id(clientOrderId="c1", exchangeOrderId="e1")
    assert ref is not None
    assert ref.exchangeOrderId == "e1"
    assert index.get(exchangeOrderId="e1") == ref

def test_order_index_get_none(index):
    """Return None for unknown IDs."""
    assert index.get(rid="unknown") is None
    assert index.get() is None

def test_order_index_mark_terminal_and_expire(index):
    """Marking terminal should allow expiration."""
    ref = index.upsert_from_open(
        rid="r1", idempotent_key="k1", clientOrderId="c1", 
        symbol="BTCUSDT", side="BUY", order_type="MARKET"
    )
    index.mark_terminal(ref)
    count = index.expire()
    assert count == 1
    assert index.get(rid="r1") is None

def test_order_index_ttl_expire(index):
    """Expire based on TTL."""
    ref = index.upsert_from_open(
        rid="r1", idempotent_key="k1", clientOrderId="c1", 
        symbol="BTCUSDT", side="BUY", order_type="MARKET"
    )
    # Fast forward time or wait (since fixture has 1s)
    time.sleep(1.1)
    count = index.expire()
    assert count == 1
    assert index.get(rid="r1") is None

def test_order_index_upsert_existing(index):
    """Updating existing RID."""
    ref1 = index.upsert_from_open(
        rid="r1", idempotent_key="k1", clientOrderId=None, 
        symbol="BTCUSDT", side="BUY", order_type="MARKET"
    )
    ref2 = index.upsert_from_open(
        rid="r1", idempotent_key="k1", clientOrderId="c2", 
        symbol="BTCUSDT", side="BUY", order_type="MARKET"
    )
    assert ref1 == ref2
    assert ref2.clientOrderId == "c2"
    assert index.get(clientOrderId="c2") == ref2
