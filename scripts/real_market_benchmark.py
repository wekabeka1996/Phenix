from _compat import execute, reexport

_TARGET = "benchmarks/real_market_benchmark.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())
