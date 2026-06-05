import json
import time
import pandas as pd
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List

class NeocortexStateAggregatorSim:
    """
    Симулятор State Aggregator для Експерименту 0.1.
    Доводить можливість побудови fixed-tick MDP з асинхронного WAL-журналу.
    """
    def __init__(self, tick_interval_ms: int = 1000):
        self.tick_interval_ms = tick_interval_ms
        self.current_tick_ms = None
        
        # Внутрішній стан (Словник)
        self.state: Dict[str, Any] = {
            "tick_ms": 0,
            "regime_detected_count": 0,
            "suppressed_count": 0,
            "last_mark_price": None,
            "last_unrealized_pnl_pct": None,
            "portfolio_fresh": False,
            "features_fresh": False,
            "regime_fresh": False,
            "active_mode": None
        }
        
        self.snapshots: List[Dict[str, Any]] = []

    def _process_event(self, event: dict):
        """Оновлює стан на основі отриманої асинхронної події."""
        event_type = event.get("event_type", "")
        
        if event_type == "POSITION_POLICY_SIDECAR_MODE_ACTIVE":
            self.state["active_mode"] = event.get("mode")
            
        elif event_type == "POSITION_POLICY_SIDECAR_SUPPRESSED":
            self.state["suppressed_count"] += 1
            
        elif event_type == "REGIME_DETECTED":
            self.state["regime_detected_count"] += 1

        # Оновлюємо ризик-метрики, якщо вони є у снепшоті
        if "position_snapshot" in event and event["position_snapshot"]:
            ps = event["position_snapshot"]
            if "mark_price" in ps:
                self.state["last_mark_price"] = float(ps["mark_price"])
            if "unrealized_pnl_pct" in ps:
                self.state["last_unrealized_pnl_pct"] = float(ps["unrealized_pnl_pct"])

        # Оновлюємо прапорці "свіжості" (наскільки система довіряє своїм доменам)
        if "freshness_snapshot" in event and event["freshness_snapshot"]:
            fs = event["freshness_snapshot"]
            self.state["portfolio_fresh"] = fs.get("portfolio_fresh", False)
            self.state["features_fresh"] = fs.get("features_fresh", False)
            self.state["regime_fresh"] = fs.get("regime_fresh", False)

    def _flush_snapshot(self):
        """Замикає тік і записує зліпок поточного стану."""
        self.state["tick_ms"] = self.current_tick_ms
        self.snapshots.append(self.state.copy())
        
        # Скидаємо лічильники, що працюють в межах одного тіку
        self.state["suppressed_count"] = 0
        self.state["regime_detected_count"] = 0

    def run_simulation(self, filepath: Path) -> pd.DataFrame:
        """Проганяє історичний лог і будує Time Series DataFrame."""
        if not filepath.exists():
            print(f"Error: Log file not found at {filepath}")
            return pd.DataFrame()

        start_time = time.perf_counter()
        processed_lines = 0

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    ts_ms = event.get("ts_ms")
                    
                    if not ts_ms:
                        continue
                        
                    # Ініціалізація годинника першою подією
                    if self.current_tick_ms is None:
                        self.current_tick_ms = (ts_ms // self.tick_interval_ms) * self.tick_interval_ms

                    # Якщо подія належить майбутньому тіку, закриваємо всі тіки до неї
                    while ts_ms >= self.current_tick_ms + self.tick_interval_ms:
                        self._flush_snapshot()
                        self.current_tick_ms += self.tick_interval_ms

                    # Оновлюємо стан подією з поточного тіку
                    self._process_event(event)
                    processed_lines += 1

                except json.JSONDecodeError:
                    pass
                    
        # Записуємо останній тік
        if self.current_tick_ms is not None:
            self._flush_snapshot()

        end_time = time.perf_counter()
        
        df = pd.DataFrame(self.snapshots)
        print(f"--- Simulation Complete ---")
        print(f"Lines processed: {processed_lines}")
        print(f"Total MDP states (ticks) generated: {len(df)}")
        print(f"Processing time: {end_time - start_time:.4f} seconds")
        print(f"Latency per state: {((end_time - start_time) / len(df)) * 1000:.2f} ms")
        
        return df

if __name__ == "__main__":
    # Запуск на семплі логів
    log_path = Path(r"C:\Users\user\Music\Phenix\tmp_phase2_debug\trade_lifecycle.jsonl")
    
    aggregator = NeocortexStateAggregatorSim(tick_interval_ms=1000) # 1 секунда тік
    df_states = aggregator.run_simulation(log_path)
    
    if not df_states.empty:
        print("\nHead of State Tensor DataFrame:")
        print(df_states.head())
        print("\nMissing values (NaN) per column:")
        print(df_states.isna().sum())
        print("\nSimulation SUCCESS: System provides causal density for MDP formulation.")
