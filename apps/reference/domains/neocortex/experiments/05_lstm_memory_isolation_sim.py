class DummyLSTMNetwork:
    """Імітація рекурентної мережі (LSTM/RNN). Мережа як чиста функція."""
    def forward(self, observation: float, hidden_state: float) -> float:
        # Спрощена логіка LSTM: частково зберігаємо минуле (0.5), додаємо нове спостереження
        new_hidden = 0.5 * hidden_state + observation
        return new_hidden

class BuggyActor:
    """Актор з глобальним станом пам'яті (Баг старих версій PPO)"""
    def __init__(self):
        self.network = DummyLSTMNetwork()
        self.global_hidden = 0.0 # Спільна пам'ять для ВСІХ активів

    def act(self, symbol: str, obs: float) -> float:
        # Пам'ять отруюється між викликами
        self.global_hidden = self.network.forward(obs, self.global_hidden)
        return self.global_hidden

class FixedActor:
    """Актор з ізольованою пам'яттю по інструментах (Правильна архітектура)"""
    def __init__(self):
        self.network = DummyLSTMNetwork()
        self.hidden_states = {"BTCUSDT": 0.0, "ETHUSDT": 0.0}

    def act(self, symbol: str, obs: float, done: bool = False) -> float:
        # 1. Episode Boundary (Обнулення пам'яті при завершенні епізоду)
        if done:
            self.hidden_states[symbol] = 0.0
            
        # 2. Causal Isolation (Ізольований стейт)
        current_hidden = self.hidden_states[symbol]
        
        # 3. Мережа - це чиста функція
        new_hidden = self.network.forward(obs, current_hidden)
        self.hidden_states[symbol] = new_hidden
        
        return new_hidden

if __name__ == "__main__":
    print("--- LSTM Memory Isolation Simulation ---\n")
    
    buggy_actor = BuggyActor()
    fixed_actor = FixedActor()
    
    print("[T=1] Нормальний ринок. BTC=1.0, ETH=1.0")
    print(f"Buggy BTC: {buggy_actor.act('BTCUSDT', 1.0):.2f} | Buggy ETH: {buggy_actor.act('ETHUSDT', 1.0):.2f}")
    print(f"Fixed BTC: {fixed_actor.act('BTCUSDT', 1.0):.2f} | Fixed ETH: {fixed_actor.act('ETHUSDT', 1.0):.2f}")
    
    print("\n[T=2] 💥 АНОМАЛІЯ НА BTC! BTC=100.0, ETH=0.0 (Флет)")
    print(f"Buggy BTC: {buggy_actor.act('BTCUSDT', 100.0):.2f} | Buggy ETH: {buggy_actor.act('ETHUSDT', 0.0):.2f}")
    print(f"Fixed BTC: {fixed_actor.act('BTCUSDT', 100.0):.2f} | Fixed ETH: {fixed_actor.act('ETHUSDT', 0.0):.2f}")
    
    print("\n--- Аналіз Отруєння Пам'яті ---")
    buggy_eth_memory = buggy_actor.global_hidden
    fixed_eth_memory = fixed_actor.hidden_states["ETHUSDT"]
    
    if buggy_eth_memory > 10.0 and fixed_eth_memory < 1.0:
        print("✅ SUCCESS: Causal Poisoning продемонстровано.")
        print(f"У старій архітектурі пам'ять ETH отруєна подією на BTC (Стейт ETH = {buggy_eth_memory:.2f} замість очікуваного 0.50).")
        print(f"У новій архітектурі (Словник станів) пам'ять ETH залишилась чистою (Стейт ETH = {fixed_eth_memory:.2f}).")
    
    print("\n[T=3] Episode Boundary. Епізод BTC закрито (done=True). BTC=0.0")
    # Buggy Actor не вміє обнуляти пам'ять
    buggy_actor.act('BTCUSDT', 0.0) 
    
    # Fixed Actor обнуляє пам'ять
    fixed_actor.act('BTCUSDT', 0.0, done=True)
    
    print(f"Buggy BTC після done=True: {buggy_actor.global_hidden:.2f} (Memory Leak!)")
    print(f"Fixed BTC після done=True: {fixed_actor.hidden_states['BTCUSDT']:.2f} (Clean Reset)")
