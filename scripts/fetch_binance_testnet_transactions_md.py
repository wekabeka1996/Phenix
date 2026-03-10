from _compat import execute, reexport

_TARGET = "diagnostics/fetch_binance_testnet_transactions_md.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
