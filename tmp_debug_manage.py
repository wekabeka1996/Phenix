from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM
from vfoundation.core.protocol import Message
import traceback

m = ManageFlowFSM(config={'trading': {'execution': {'manage': {
                  'auto': True, 'brackets': {'enable': True}}}}})
fill_msg = Message(op='EVT', verb='TRADE_EXECUTED', src='adapter', dst='manage_flow', pld={
                   'symbol': 'BTCUSDT', 'orderId': '12345', 'side': 'BUY', 'qty': '0.001', 'price': '50000.0'})

m._on_fill(fill_msg)
try:
    res = m._place_brackets(fill_msg)
    print('res', res)
except Exception:
    traceback.print_exc()
    print('metrics', m._metrics)
print('state after', m.state)
print('position_qty', m.position_qty)
print('sl', m.sl_price, 'tp', m.tp_price)
