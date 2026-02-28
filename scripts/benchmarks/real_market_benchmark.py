import pandas as pd
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import matplotlib.pyplot as plt
from torch.distributions import Normal
import sys
import os

# ==========================================
# 0. DATA LOADING & PREPROCESSING
# ==========================================
def load_and_process_data(csv_path):
    df = pd.read_csv(csv_path)
    
    # Select Features (OHLCV + feats)
    feature_cols = [c for c in df.columns if 'feat_' in c] + ['open', 'high', 'low', 'close', 'volume']
    
    # Filter numeric only
    data = df[feature_cols].copy()
    
    # Fill NaN (compatible with newer pandas)
    data = data.ffill().fillna(0)
    
    # Normalize (Z-Score) -> Critical for Neural Networks
    data_norm = (data - data.mean()) / (data.std() + 1e-6)
    
    # Convert to Tensor
    tensor_data = torch.FloatTensor(data_norm.values)
    
    # Calculate Returns for Reward (Next Close - Current Close)
    # Shift -1 to align "Current State" with "Next Return"
    returns = df['close'].pct_change().shift(-1).fillna(0)
    tensor_returns = torch.FloatTensor(returns.values)
    
    print(f"Loaded Real Data: {tensor_data.shape} samples with {tensor_data.shape[1]} features.")
    return tensor_data, tensor_returns

# ==========================================
# 1. THE SOVIET TECHNOLOGY (SPECTRAL GATE)
# ==========================================
class SoftSpectralGate(nn.Module):
    def __init__(self, energy_threshold=0.90, scale_factor=10.0, epsilon=1e-5):
        super().__init__()
        self.energy_threshold = energy_threshold
        self.scale_factor = scale_factor
        self.epsilon = epsilon

    def forward(self, x):
        # x: [Batch, Seq, Features]
        orig_shape = x.shape
        if x.dim() > 2:
            x_flat = x.reshape(-1, x.size(-1))
        else:
            x_flat = x

        # Jittered Gram Matrix
        gram = torch.matmul(x_flat.t(), x_flat)
        gram += torch.eye(gram.shape[0], device=x.device) * self.epsilon

        # Eigendecomposition
        L, V = torch.linalg.eigh(gram)
        L = L.flip(0).clamp(min=1e-8)
        V = V.flip(1)

        # Cumulative Energy Thresholding
        total_e = L.sum()
        cum_e = torch.cumsum(L, dim=0)
        ratios = cum_e / total_e
        
        # Find cut-off index
        cut_idx = torch.nonzero(ratios >= self.energy_threshold)
        k = cut_idx[0].item() if len(cut_idx) > 0 else len(L)-1
        threshold_val = L[k]

        # Soft Sigmoid Gate
        mask = torch.sigmoid(self.scale_factor * (L - threshold_val))
        
        # Differentiable Projection
        P = V @ torch.diag(mask) @ V.t()
        x_purified = x_flat @ P
        
        return x_purified.view(orig_shape)

# ==========================================
# 2. THE GLADIATORS (AGENTS)
# ==========================================
class WesternModel(nn.Module):
    def __init__(self, input_dim, hidden_dim, action_dim):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.actor_mean = nn.Linear(hidden_dim, action_dim)
        self.actor_std = nn.Parameter(torch.zeros(1, action_dim))
        self.critic = nn.Linear(hidden_dim, 1)

    def forward(self, x):
        h, _ = self.lstm(x)
        last_h = h[:, -1, :]
        
        action_mean = self.actor_mean(last_h)
        action_std = self.actor_std.exp().expand_as(action_mean)
        value = self.critic(last_h)
        return action_mean, action_std, value

class SovietWesternModel(WesternModel):
    def __init__(self, input_dim, hidden_dim, action_dim):
        super().__init__(input_dim, hidden_dim, action_dim)
        # INSERTING THE SPECTRAL COMPONENT
        self.rectifier = SoftSpectralGate(energy_threshold=0.85, scale_factor=15.0)

    def forward(self, x):
        h, _ = self.lstm(x)
        
        # SPECTRAL RECTIFICATION
        h_clean = self.rectifier(h)
        
        # Stability: Clamp & Replace NaN
        h_clean = torch.clamp(h_clean, -10, 10)
        h_clean = torch.where(torch.isnan(h_clean), h, h_clean)
        
        last_h = h_clean[:, -1, :]
        
        action_mean = self.actor_mean(last_h)
        action_std = (self.actor_std.exp() + 0.1).expand_as(action_mean)  # Min std = 0.1
        value = self.critic(last_h)
        return action_mean, action_std, value

# ==========================================
# 3. REAL MARKET ENVIRONMENT
# ==========================================
class RealMarketEnv:
    def __init__(self, data, returns, seq_len=10):
        self.data = data
        self.returns = returns
        self.seq_len = seq_len
        self.idx = 0
        self.max_steps = len(data) - seq_len - 1

    def reset(self):
        self.idx = 0
        return self._get_obs()

    def _get_obs(self):
        # Sliding Window
        window = self.data[self.idx : self.idx + self.seq_len]
        return window.unsqueeze(0) # [1, Seq, Feat]

    def step(self, action):
        # Action is scalar [-1, 1] (Position size: Short to Long)
        # Reward = Action * Next_Period_Return * 100 (bps)
        
        next_ret = self.returns[self.idx + self.seq_len]
        reward = action * next_ret * 100.0
        
        # Penalize indecision or excessive flipping (optional, kept simple here)
        # reward -= 0.01 * abs(action) 
        
        self.idx += 1
        done = self.idx >= self.max_steps
        
        next_obs = self._get_obs() if not done else torch.zeros_like(self._get_obs())
        return next_obs, reward, done

# ==========================================
# 4. TRAINING ENGINE
# ==========================================
def train_on_real_data(agent_name, model, data, returns, episodes=30):
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    rewards_history = []
    
    print(f"\n--- Training {agent_name} on DOGEUSDT ---")
    
    for ep in range(episodes):
        env = RealMarketEnv(data, returns, seq_len=10)
        state = env.reset()
        done = False
        total_reward = 0
        
        while not done:
            mu, std, val = model(state)
            
            # Safety checks for NaN/Inf
            mu = torch.clamp(mu, -10, 10)
            std = torch.clamp(std, 0.01, 10)
            
            dist = Normal(mu, std)
            action = dist.sample()
            
            # Clamp action to [-1, 1]
            action_clipped = torch.clamp(action, -1.0, 1.0)
            
            next_state, reward, done = env.step(action_clipped.item())
            
            # PPO-style loss (simplified)
            log_prob = dist.log_prob(action)
            advantage = reward - val.item()
            
            loss = -log_prob * advantage + 0.5 * F.mse_loss(val, torch.tensor([[reward]]))
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            total_reward += reward
            state = next_state
            
        rewards_history.append(total_reward)
        if (ep+1) % 5 == 0:
            print(f"Episode {ep+1}: Total Profit = {total_reward:.4f} bps")
            
    return rewards_history

# ==========================================
# 5. EXECUTION
# ==========================================
if __name__ == "__main__":
    # Determine CSV path
    csv_path = 'data/recorder/2026-01-14/DOGEUSDT_900.csv'
    
    # Check if file exists
    if not os.path.exists(csv_path):
        print(f"❌ Error: {csv_path} not found.")
        print(f"Current directory: {os.getcwd()}")
        print("\nPlease ensure DOGEUSDT_900.csv exists at the specified path.")
        sys.exit(1)
    
    # Load Data
    data, returns = load_and_process_data(csv_path)
    
    INPUT_DIM = data.shape[1]
    HIDDEN_DIM = 64
    ACTION_DIM = 1
    
    # 1. Initialize Rivals
    western_bot = WesternModel(INPUT_DIM, HIDDEN_DIM, ACTION_DIM)
    soviet_bot = SovietWesternModel(INPUT_DIM, HIDDEN_DIM, ACTION_DIM)
    
    # 2. Fight!
    w_rewards = train_on_real_data("Western Bot", western_bot, data, returns)
    s_rewards = train_on_real_data("Soviet-Western Bot", soviet_bot, data, returns)
    
    # 3. Plot Results
    plt.figure(figsize=(10, 6))
    plt.plot(w_rewards, label='Western Bot (Baseline)', linestyle='--', color='gray')
    plt.plot(s_rewards, label='Soviet-Western Bot (Spectral)', color='red', linewidth=2)
    plt.title('Real Market A/B Test: DOGEUSDT (15m)')
    plt.xlabel('Episodes')
    plt.ylabel('Cumulative Profit (bps)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig('real_market_benchmark_results.png', dpi=150, bbox_inches='tight')
    print("\n✓ Plot saved as real_market_benchmark_results.png")
    plt.show()

    # Final Stats
    print("\n[VERDICT]")
    print(f"Western Bot Avg Profit: {np.mean(w_rewards[-5:]):.4f}")
    print(f"Soviet Bot Avg Profit:  {np.mean(s_rewards[-5:]):.4f}")
    print(f"Advantage: {np.mean(s_rewards[-5:]) - np.mean(w_rewards[-5:]):.4f} bps")
