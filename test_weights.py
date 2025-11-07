from vfoundation.config import AppConfig
cfg = AppConfig()
sw = cfg.trading.decision.signal_weights
print(f'Type: {type(sw)}')
print(f'Has to_dict: {hasattr(sw, "to_dict")}')
print(f'Dict: {sw.__dict__}')
print(f'Has model_dump: {hasattr(sw, "model_dump")}')
if hasattr(sw, 'model_dump'):
    print(f'model_dump: {sw.model_dump()}')
print(f'In check: {"obi" in sw}')
