from typing import Tuple, Dict, Any

class AuroraSimEnv:
    """
    Gym-like Simulator для перетворення історичних логів у On-Policy середовище.
    """
    def __init__(self, historical_log: list):
        self.history = historical_log
        self.current_step = 0
        self.max_steps = len(historical_log)

    def reset(self) -> Dict[str, Any]:
        self.current_step = 0
        return self._get_observation()

    def _get_observation(self) -> Dict[str, Any]:
        if self.current_step < self.max_steps:
            return self.history[self.current_step]
        return {}

    def step(self, action: str) -> Tuple[Dict[str, Any], float, bool, dict]:
        """
        Крок симуляції. 
        action: дія поточного агента ('ALLOW', 'BLOCK')
        """
        if self.current_step >= self.max_steps:
            return {}, 0.0, True, {}

        current_event = self.history[self.current_step]
        
        # Симуляція реакції середовища на дію нашого агента (Reward Logic)
        reward = 0.0
        if action == "ALLOW":
            if current_event["is_toxic"]:
                reward = -10.0 # Stress Penalty
            else:
                reward = current_event["potential_pnl"]
        elif action == "BLOCK":
            if current_event["is_toxic"]:
                reward = 5.0 # Good Block Bonus
            else:
                reward = 0.0 # Missed profit (0.0)
                
        # Робимо крок у часі
        self.current_step += 1
        done = self.current_step >= self.max_steps
        next_obs = self._get_observation()
        
        return next_obs, reward, done, {}

if __name__ == "__main__":
    print("--- On-Policy World Simulator Test ---\n")
    
    # Імітація WAL журналу фічів та інтентів
    historical_log = [
        {"time": "10:00", "feature_x": 0.8, "is_toxic": False, "potential_pnl": 15.0, "historical_action": "ALLOW"},
        {"time": "10:05", "feature_x": -0.9, "is_toxic": True,  "potential_pnl": 0.0,  "historical_action": "ALLOW"}, # Old system failed to block
        {"time": "10:10", "feature_x": 0.5, "is_toxic": False, "potential_pnl": 5.0,   "historical_action": "BLOCK"}  # Old system falsely blocked
    ]
    
    env = AuroraSimEnv(historical_log)
    
    print("1. Replaying History (Old Policy):")
    env.reset()
    total_hist_reward = 0
    for event in historical_log:
        _, r, _, _ = env.step(event["historical_action"])
        total_hist_reward += r
    print(f"Historical Reward: {total_hist_reward:.2f} (Includes penalties from toxic events)")
    
    print("\n2. Simulating New Agent (On-Policy Rollout):")
    obs = env.reset()
    total_new_reward = 0
    done = False
    
    while not done:
        # Імітація кращого агента (розуміє, що feature_x < -0.5 означає toxic)
        action = "BLOCK" if obs.get("feature_x", 0) < -0.5 else "ALLOW"
        
        next_obs, r, done, _ = env.step(action)
        print(f"Time: {obs['time']} | Obs: {obs['feature_x']} | Agent Action: {action} | Reward: {r}")
        total_new_reward += r
        obs = next_obs
        
    print(f"\nNew Agent Reward: {total_new_reward:.2f}")
    if total_new_reward > total_hist_reward:
        print("\n✅ SUCCESS: Simulator successfully generated an On-Policy trajectory allowing the agent to break free from historical mistakes.")
    else:
        print("\n❌ FAILURE: Simulator logic failed.")
