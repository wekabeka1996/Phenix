import pandas as pd

class RewardSimulator:
    def __init__(self, alpha=1.0, beta=5.0, gamma=10.0):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

    def calculate_reward(self, agent_action: str, market_event: dict) -> float:
        """
        Розраховує нагороду для конкретної дії агента та події на ринку.
        agent_action: 'ALLOW' або 'BLOCK'
        """
        reward = 0.0
        event_type = market_event["type"]
        potential_pnl = market_event["pnl"]

        if agent_action == "ALLOW":
            if event_type == "TOXIC":
                # Агент пропустив небезпеку. 
                # PnL немає (бо система сама заблокувала хард-лімітом), але є стрес-штраф.
                reward -= self.gamma
            else:
                # Звичайний трейд (може бути плюс або мінус)
                reward += self.alpha * potential_pnl
        elif agent_action == "BLOCK":
            if event_type == "TOXIC":
                # Агент превентивно заблокував небезпеку. Отримує бонус.
                reward += self.beta
            else:
                # Агент заблокував звичайний сигнал. 
                # Він пропускає PnL (можливий прибуток або збиток), нагорода = 0.
                reward += 0.0 
                
        return reward

if __name__ == "__main__":
    # Налаштування симуляції
    sim = RewardSimulator(alpha=1.0, beta=5.0, gamma=10.0)
    
    # Сценарій ринку
    market_scenario = [
        {"id": 1, "type": "GOOD", "pnl": 20.0},
        {"id": 2, "type": "BAD", "pnl": -5.0},
        {"id": 3, "type": "TOXIC", "pnl": 0.0} # PnL 0, бо система блокує виконання
    ]
    
    # Поведінка агентів
    agents = {
        "Passive": ["ALLOW", "ALLOW", "ALLOW"],
        "Reward_Hacker": ["BLOCK", "BLOCK", "BLOCK"],
        "Adaptive_Controller": ["ALLOW", "ALLOW", "BLOCK"]
    }
    
    results = []
    
    print("--- Reward Decomposition Simulation ---\n")
    for agent_name, actions in agents.items():
        cumulative_reward = 0.0
        agent_history = []
        
        for i, event in enumerate(market_scenario):
            action = actions[i]
            r = sim.calculate_reward(action, event)
            cumulative_reward += r
            agent_history.append(r)
            
        results.append({
            "Agent": agent_name,
            "Trade_1 (Good)": agent_history[0],
            "Trade_2 (Bad)": agent_history[1],
            "Trade_3 (Toxic)": agent_history[2],
            "Total_Reward": cumulative_reward
        })
        
    df = pd.DataFrame(results)
    print(df.to_string(index=False))
    
    print("\n--- Analysis ---")
    adaptive_score = df[df["Agent"] == "Adaptive_Controller"]["Total_Reward"].values[0]
    hacker_score = df[df["Agent"] == "Reward_Hacker"]["Total_Reward"].values[0]
    passive_score = df[df["Agent"] == "Passive"]["Total_Reward"].values[0]
    
    if adaptive_score > hacker_score and adaptive_score > passive_score:
        print("✅ SUCCESS: Multi-objective reward successfully aligns agent incentives.")
        print("The Adaptive Controller outperforms both the Passive system and the Reward Hacker.")
    else:
        print("❌ FAILURE: Reward function incentives are misaligned.")
