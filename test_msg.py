from vfoundation.core.protocol import Message

features_payload = {'symbol': 'BTC', 'features': {'price': 1000}}
msg = Message(op='EVT', verb='FEATURES_CALCULATED', src='test',
              dst='dm', pld=features_payload, rid='rid')
print(f'Type pld: {type(msg.pld)}')
print(f'Has attr pld: {hasattr(msg, "pld")}')
print(f'pld: {msg.pld}')
print(f'Is dict: {isinstance(msg.pld, dict)}')
print(f'Has feature: {hasattr(msg.pld, "features")}')
