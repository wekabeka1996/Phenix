import numpy as np
import pandas as pd
from typing import List, Optional

class ActionDecoderSim:
    """
    Симулятор декодера дій з гістерезисом.
    Конвертує Continuous [-1, 1] у Discrete FSM Commands.
    """
    def __init__(self, cooldown_ticks: int = 900, lower_threshold: float = -0.6, upper_threshold: float = 0.6):
        self.cooldown_ticks = cooldown_ticks
        self.lower_threshold = lower_threshold
        self.upper_threshold = upper_threshold
        
        self.current_state = "NORMAL"
        self.ticks_since_last_change = cooldown_ticks + 1 # Готовий до дій одразу
        self.commands_issued: List[dict] = []

    def decode(self, tick: int, trust_signal: float) -> Optional[str]:
        self.ticks_since_last_change += 1
        
        # Перевірка кулдауну
        if self.ticks_since_last_change < self.cooldown_ticks:
            return None # Агент заблокований гістерезисом

        command = None
        # Логіка порогів (Deadbands)
        if trust_signal < self.lower_threshold and self.current_state == "NORMAL":
            command = "CMD:SWITCH_TO_LOW_RISK_MODE"
            self.current_state = "LOW_RISK"
            self.ticks_since_last_change = 0
            
        elif trust_signal > self.upper_threshold and self.current_state == "LOW_RISK":
            command = "CMD:SWITCH_TO_NORMAL_MODE"
            self.current_state = "NORMAL"
            self.ticks_since_last_change = 0

        if command:
            self.commands_issued.append({
                "tick": tick,
                "trust_signal": trust_signal,
                "command": command
            })
            
        return command

if __name__ == "__main__":
    # Симулюємо 1 торговий день (86400 секунд = 86400 тіків)
    total_ticks = 86400
    
    # Генеруємо поведінку абсолютно нестабільного PPO агента (Білий шум)
    # Це найгірший сценарій (Worst-case scenario)
    np.random.seed(42)
    noisy_trust_signals = np.random.uniform(-1.0, 1.0, total_ticks)
    
    decoder = ActionDecoderSim(cooldown_ticks=900) # 15 хвилин кулдаун
    
    print("Starting simulation of noisy PPO agent (86400 ticks)...")
    
    for tick in range(total_ticks):
        decoder.decode(tick, noisy_trust_signals[tick])
        
    print("\n--- Simulation Results ---")
    print(f"Total raw network outputs: {total_ticks}")
    print(f"Total FSM commands explicitly issued: {len(decoder.commands_issued)}")
    
    if len(decoder.commands_issued) > 0:
        df = pd.DataFrame(decoder.commands_issued)
        print("\nSample of issued commands:")
        print(df.head(10))
        
        # Перевірка на Flip Storm
        min_distance = df['tick'].diff().min()
        print(f"\nMinimum time between commands: {min_distance} ticks (Target: >= {decoder.cooldown_ticks})")
        
        if min_distance >= decoder.cooldown_ticks:
            print("✅ SUCCESS: Hysteresis verified. Flip Storms are mathematically impossible.")
        else:
            print("❌ FAILURE: Flip Storm detected!")
    else:
        print("No commands issued (thresholds might be too strict).")
