import pandas as pd
from pathlib import Path
from datetime import date
from typing import Optional, Set

def _parse_date(s: str) -> date:
    return date.fromisoformat(s)

def load_recorder_data(
    recorder_dir: Path,
    start: Optional[date],
    end: Optional[date],
    symbols: Set[str],
    tf_sec: int,
) -> pd.DataFrame:
    out = []
    if not recorder_dir.exists():
        return pd.DataFrame()
        
    for day_dir in sorted([p for p in recorder_dir.iterdir() if p.is_dir()]):
        try:
            day = _parse_date(day_dir.name)
        except ValueError:
            continue
            
        if start and day < start: continue
        if end and day >= end: continue
        
        for sym in symbols:
            p = day_dir / f"{sym}_{tf_sec}.csv"
            if p.exists():
                df = pd.read_csv(p)
                if "symbol" not in df.columns:
                    df["symbol"] = sym
                out.append(df)
                
    if not out:
        return pd.DataFrame()
        
    df = pd.concat(out, ignore_index=True)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("Int64")
    if "tf_sec" in df.columns:
        df["tf_sec"] = pd.to_numeric(df["tf_sec"], errors="coerce").astype("Int64")
        df = df[df["tf_sec"] == tf_sec]
        
    # Ensure OHLC columns exist
    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            if col == "close":
                raise ValueError("CSV must contain 'close' column")
            df[col] = df["close"] # fallback
            
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return df
