import pandas as pd


def main() -> None:
    path = "data/processed/BTCUSDT/5m/2023-08_enriched.parquet"
    df = pd.read_parquet(path)

    # Normalize and sort
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.sort_values("open_time").reset_index(drop=True)

    # Target window (ms -> datetime)
    start_ms = 1692305000000
    end_ms = 1692310000000
    start_ts = pd.to_datetime(start_ms, unit="ms", utc=True)
    end_ts = pd.to_datetime(end_ms, unit="ms", utc=True)

    window = df[(df["open_time"] >= start_ts) & (df["open_time"] <= end_ts)].copy()
    window = window.reset_index(drop=True)

    # Continuity checks
    window["delta_t_ms"] = window["open_time"].diff().dt.total_seconds().mul(1000)
    window["pct_change_close"] = window["close"].pct_change().mul(100)
    window["gap_low_from_prev_close_pct"] = (
        (window["low"] - window["close"].shift(1)) / window["close"].shift(1)
    ).mul(100)

    gaps = window[window["delta_t_ms"] > 1000]
    large_moves = window[window["pct_change_close"].abs() > 1]
    large_gap_lows = window[window["gap_low_from_prev_close_pct"] < -1]

    # Find crash candidate: low near 24800 and previous close near 27600
    crash_candidates = window[
        (window["low"] <= 24850) & (window["close"].shift(1) >= 27000)
    ]

    if crash_candidates.empty:
        # fallback: any low <= 24850 within window
        crash_candidates = window[window["low"] <= 24850]

    if crash_candidates.empty:
        crash_index = None
    else:
        crash_index = crash_candidates.index[0]

    print("Window rows:", len(window))
    print("Window range:", window["open_time"].min(), "->", window["open_time"].max())
    print("Monotonic in window:", window["open_time"].is_monotonic_increasing)
    print("Duplicate timestamps in window:", window["open_time"].duplicated().sum())

    print("\nTime gaps > 1000ms:")
    print(gaps[["open_time", "delta_t_ms"]].head(20).to_string(index=False))

    print("\nLarge close pct_change (>1%):")
    print(large_moves[["open_time", "close", "pct_change_close"]].head(20).to_string(index=False))

    print("\nLarge low gap from prev close (<-1%):")
    print(
        large_gap_lows[["open_time", "low", "close", "gap_low_from_prev_close_pct"]]
        .head(20)
        .to_string(index=False)
    )

    if crash_index is None:
        print("\nNo crash candidate found in window.")
        return

    # Snippet around crash
    start_idx = max(crash_index - 5, 0)
    end_idx = min(crash_index + 6, len(window))
    snippet = window.loc[start_idx:end_idx - 1, [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "delta_t_ms",
        "pct_change_close",
        "gap_low_from_prev_close_pct",
    ]]

    print("\nCrash snippet (5 rows before/after):")
    print(snippet.to_string(index=False))

    # Duration and ticks during drop: from last close >= 27600 to crash row
    pre = window.loc[:crash_index]
    pre_candidates = pre[pre["close"] >= 27600]
    if not pre_candidates.empty:
        pre_idx = pre_candidates.index[-1]
        duration_ms = (
            window.loc[crash_index, "open_time"] - window.loc[pre_idx, "open_time"]
        ).total_seconds() * 1000
        ticks = crash_index - pre_idx
        print("\nDrop stats:")
        print("Start row time:", window.loc[pre_idx, "open_time"])
        print("Crash row time:", window.loc[crash_index, "open_time"])
        print("Duration (ms):", int(duration_ms))
        print("Ticks during drop:", int(ticks))
    else:
        print("\nDrop stats: No pre-crash close >= 27600 found in window.")


if __name__ == "__main__":
    main()
