from _compat import execute, reexport

_TARGET = "tmp/tmp_alpha_search_fee_adjusted_pnl.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
