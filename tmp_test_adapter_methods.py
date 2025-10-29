from vfoundation.adapters.binance_adapter import BinanceAdapter
print('BinanceAdapter methods:')
for name in ('_request','quantize_quantity','place_market_entry'):
    print(name, hasattr(BinanceAdapter, name))
