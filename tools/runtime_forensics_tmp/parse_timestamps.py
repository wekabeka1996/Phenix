from datetime import datetime, timezone

def print_ts(ts_ms):
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    print(f"TS: {ts_ms} -> {dt.isoformat()}")

print_ts(1782039079831) # First shadow_critical
print_ts(1782846291315) # Last shadow_critical
print_ts(1782039599999) # First regime_confidence
print_ts(1782845999999) # Last regime_confidence
