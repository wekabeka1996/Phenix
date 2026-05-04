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
def load_and_process_data(parquet_path):
    print(f"Loading {parquet_path}...")
    df = pd.read_parquet(parquet_path)
    
    print(f"Total shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()[:20]}...")  # First 20 cols
    
    # Select Features (feat_* columns + OHLCV)
    feature_cols = [c for c in df.columns if 'feat_' in c]
    ohlcv_cols = [c for c in ['open', 'high', 'low', 'close', 'volume'] if c in df.columns]
    feature_cols = feature_cols + ohlcv_cols
    
    print(f"Selected {len(feature_cols)} features for training")
    
    if len(feature_cols) == 0:
        # Fallback: use all numeric columns except timestamp
        feature_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if 'timestamp' in feature_cols:
            feature_cols.remove('timestamp')
        print(f"Using all numeric columns: {len(feature_cols)} features")
    
    # Filter numeric only
    data = df[feature_cols].copy()
    
    # Fill NaN
    data = data.ffill().fillna(0)
    
    # Normalize (Z-Score)
    data_norm = (data - data.mean()) / (data.std() + 1e-6)
    
    # Convert to Tensor
    tensor_data = torch.FloatTensor(data_norm.values)
    
    # Calculate Returns
    if 'close' in df.columns:
        returns = df['close'].pct_change().shift(-1).fillna(0)
    else:
        # Use first numeric column as price proxy
        price_col = df.select_dtypes(include=[np.number]).columns[0]
        returns = df[price_col].pct_change().shift(-1).fillna(0)
    
    tensor_returns = torch.FloatTensor(returns.values)
    
    print(f"✓ Loaded: {tensor_data.shape} samples with {tensor_data.shape[1]} features")
    return tensor_data, tensor_returns, len(df)

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
        orig_shape = x.shape
        if x.dim() > 2:
            x_flat = x.reshape(-1, x.size(-1))
        else:
            x_flat = x

        # Jittered Gram Matrix
        gram = torch.matmul(x_flat.t(), x_flat)
        gram += torch.eye(gram.shape[0], device=x.device) * self.epsilon

        # Eigendecomposition
        try:
            L, V = torch.linalg.eigh(gram)
        except RuntimeError:
            return x_flat.view(orig_shape)
        
        L = L.flip(0).clamp(min=1e-8)
        V = V.flip(1)

        # Cumulative Energy Thresholding
        total_e = L.sum()
        if total_e <= 0:
            return x_flat.view(orig_shape)
            
        cum_e = torch.cumsum(L, dim=0)
        ratios = cum_e / total_e
        
        cut_idx = torch.nonzero(ratios >= self.energy_threshold)
        k = cut_idx[0].item() if len(cut_idx) > 0 else len(L)-1
        threshold_val = L[k]

        mask = torch.sigmoid(self.scale_factor * (L - threshold_val))
        P = V @ torch.diag(mask) @ V.t()
        x_purified = x_flat @ P
        
        x_purified = torch.clamp(x_purified, -100, 100)
        x_purified = torch.where(torch.isnan(x_purified), x_flat, x_purified)
        
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
        self.rectifier = SoftSpectralGate(energy_threshold=0.85, scale_factor=15.0)

    def forward(self, x):
        h, _ = self.lstm(x)
        h_clean = self.rectifier(h)
        h_clean = torch.clamp(h_clean, -10, 10)
        h_clean = torch.where(torch.isnan(h_clean), h, h_clean)
        
        last_h = h_clean[:, -1, :]
        
        action_mean = self.actor_mean(last_h)
        action_std = (self.actor_std.exp() + 0.1).expand_as(action_mean)
        value = self.critic(last_h)
        return action_mean, action_std, value

# ==========================================
# 3. REAL MARKET ENVIRONMENT
# ==========================================
class RealMarketEnv:
    def __init__(self, data, returns, seq_len=None):
        self.data = data
        self.returns = returns
        if seq_len is None:
            seq_len = max(5, min(20, len(data) // 10))
        self.seq_len = seq_len
        self.idx = 0
        self.max_steps = max(1, len(data) - self.seq_len - 1)

    def reset(self):
        self.idx = 0
        return self._get_obs()

    def _get_obs(self):
        window = self.data[self.idx : self.idx + self.seq_len]
        if len(window) < self.seq_len:
            pad = torch.zeros(self.seq_len - len(window), window.shape[1])
            window = torch.cat([window, pad], dim=0)
        return window.unsqueeze(0)

    def step(self, action):
        idx_ret = self.idx + self.seq_len
        if idx_ret < len(self.returns):
            next_ret = self.returns[idx_ret]
        else:
            next_ret = 0.0
        reward = action * next_ret * 100.0
        
        self.idx += 1
        done = self.idx >= self.max_steps
        
        next_obs = self._get_obs() if not done else torch.zeros_like(self._get_obs())
        return next_obs, reward, done

# ==========================================
# 4. TRAINING ENGINE
# ==========================================
def train_on_real_data(agent_name, model, data, returns, episodes=50, verbose=True):
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    rewards_history = []
    
    if verbose:
        print(f"\n--- Training {agent_name} ---")
    
    if len(data) < 5:
        if verbose:
            print(f"  WARNING: Only {len(data)} samples, skipping")
        return [0.0] * episodes
    
    for ep in range(episodes):
        env = RealMarketEnv(data, returns)
        state = env.reset()
        done = False
        total_reward = 0
        step_count = 0
        
        while not done and step_count < len(data) - 2:
            mu, std, val = model(state)
            
            # Aggressive NaN protection
            mu = torch.where(torch.isnan(mu), torch.zeros_like(mu), mu)
            mu = torch.where(torch.isinf(mu), torch.zeros_like(mu), mu)
            mu = torch.clamp(mu, -5, 5)
            
            std = torch.where(torch.isnan(std), torch.ones_like(std) * 0.5, std)
            std = torch.clamp(std, 0.05, 5)
            
            val = torch.clamp(val, -100, 100)
            
            dist = Normal(mu, std)
            action = dist.sample()
            action_clipped = torch.clamp(action, -1.0, 1.0)
            
            next_state, reward, done = env.step(action_clipped.item())
            
            log_prob = dist.log_prob(action)
            advantage = reward - val.item()
            loss = -log_prob * advantage + 0.5 * F.mse_loss(val, torch.tensor([[reward]]))
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            total_reward += reward
            state = next_state
            step_count += 1
            
        rewards_history.append(total_reward)
        if verbose and (ep+1) % 10 == 0:
            print(f"  Episode {ep+1}: Total Profit = {total_reward:.4f} bps")
            
    return rewards_history

# ==========================================
# 5. EXECUTION ON BTCUSDT HISTORICAL DATA
# ==========================================
if __name__ == "__main__":
    parquet_path = 'data/processed/BTCUSDT/5m/2023-05_enriched.parquet'
    
    if not os.path.exists(parquet_path):
        print(f"❌ File not found: {parquet_path}")
        sys.exit(1)
    
    # Load Data
    data, returns, sample_count = load_and_process_data(parquet_path)
    
    INPUT_DIM = data.shape[1]
    HIDDEN_DIM = 128
    ACTION_DIM = 1
    
    print(f"\n{'='*70}")
    print("BTCUSDT 5-minute Candles (May 2023) - Soviet vs Western Bot")
    print(f"{'='*70}\n")
    
    # Initialize models
    print("Initializing models...")
    western_bot = WesternModel(INPUT_DIM, HIDDEN_DIM, ACTION_DIM)
    soviet_bot = SovietWesternModel(INPUT_DIM, HIDDEN_DIM, ACTION_DIM)
    
    # Train
    w_rewards = train_on_real_data("Western Bot", western_bot, data, returns, episodes=50)
    s_rewards = train_on_real_data("Soviet-Western Bot", soviet_bot, data, returns, episodes=50)
    
    # Results
    print("\n" + "="*70)
    print("FINAL RESULTS")
    print("="*70)
    
    w_last5 = np.mean(w_rewards[-5:])
    s_last5 = np.mean(s_rewards[-5:])
    
    print(f"\nWestern Bot (Baseline):")
    print(f"  Final 5-ep avg: {w_last5:.4f} bps")
    print(f"  All-time best:  {np.max(w_rewards):.4f} bps")
    print(f"  All-time worst: {np.min(w_rewards):.4f} bps")
    
    print(f"\nSoviet-Western Bot (Spectral):")
    print(f"  Final 5-ep avg: {s_last5:.4f} bps")
    print(f"  All-time best:  {np.max(s_rewards):.4f} bps")
    print(f"  All-time worst: {np.min(s_rewards):.4f} bps")
    
    advantage = s_last5 - w_last5
    advantage_pct = (advantage / abs(w_last5)) * 100 if w_last5 != 0 else 0
    win_rate = sum(1 for w, s in zip(w_rewards, s_rewards) if s > w) / len(w_rewards) * 100
    
    print(f"\n🏆 SOVIET ADVANTAGE:")
    print(f"  Absolute:      {advantage:+.4f} bps")
    print(f"  Relative:      {advantage_pct:+.2f}%")
    print(f"  Win Rate:      {win_rate:.1f}%")
    
    # ==========================================
    # PLOTTING
    # ==========================================
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    
    # Plot 1: Reward trajectories
    ax1 = axes[0]
    ax1.plot(w_rewards, label='Western Bot (Baseline)', linestyle='--', color='gray', linewidth=2)
    ax1.plot(s_rewards, label='Soviet-Western Bot (Spectral)', color='red', linewidth=2.5)
    ax1.set_xlabel('Episode')
    ax1.set_ylabel('Cumulative Profit (bps)')
    ax1.set_title('BTCUSDT 5-min (May 2023) - Training Trajectory')
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Cumulative advantage
    ax2 = axes[1]
    advantages = np.array(s_rewards) - np.array(w_rewards)
    cumsum_adv = np.cumsum(advantages)
    colors = ['green' if adv > 0 else 'red' for adv in advantages]
    ax2.bar(range(len(advantages)), advantages, color=colors, alpha=0.6, label='Per-Episode Advantage')
    ax2.plot(cumsum_adv, color='darkgreen', linewidth=2, label='Cumulative Advantage')
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.set_xlabel('Episode')
    ax2.set_ylabel('Soviet Advantage (bps)')
    ax2.set_title('Soviet-Western Advantage Over Training')
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('btcusdt_benchmark_results.png', dpi=150, bbox_inches='tight')
    print(f"\n✓ Plot saved as btcusdt_benchmark_results.png")
    
    # Save report
    with open('btcusdt_benchmark_report.txt', 'w') as f:
        f.write("="*70 + "\n")
        f.write("HISTORICAL REAL MARKET BENCHMARK\n")
        f.write("BTCUSDT 5-minute Candles (May 2023)\n")
        f.write("="*70 + "\n\n")
        
        f.write("DATASET STATISTICS:\n")
        f.write(f"  Total Samples: {sample_count:,}\n")
        f.write(f"  Features: {INPUT_DIM}\n")
        f.write(f"  Timeframe: 5 minutes\n\n")
        
        f.write("WESTERN BOT (Baseline LSTM):\n")
        f.write(f"  Final 5-ep Avg: {w_last5:.4f} bps\n")
        f.write(f"  Best Episode:  {np.max(w_rewards):.4f} bps\n")
        f.write(f"  Worst Episode: {np.min(w_rewards):.4f} bps\n")
        f.write(f"  Mean Profit:   {np.mean(w_rewards):.4f} bps\n")
        f.write(f"  Std Dev:       {np.std(w_rewards):.4f}\n\n")
        
        f.write("SOVIET-WESTERN BOT (LSTM + Spectral):\n")
        f.write(f"  Final 5-ep Avg: {s_last5:.4f} bps\n")
        f.write(f"  Best Episode:  {np.max(s_rewards):.4f} bps\n")
        f.write(f"  Worst Episode: {np.min(s_rewards):.4f} bps\n")
        f.write(f"  Mean Profit:   {np.mean(s_rewards):.4f} bps\n")
        f.write(f"  Std Dev:       {np.std(s_rewards):.4f}\n\n")
        
        f.write("COMPARATIVE ANALYSIS:\n")
        f.write(f"  Absolute Advantage: {advantage:+.4f} bps\n")
        f.write(f"  Relative Advantage: {advantage_pct:+.2f}%\n")
        f.write(f"  Soviet Win Rate:    {win_rate:.1f}%\n")
    
    print("✓ Report saved as btcusdt_benchmark_report.txt")
    
    plt.show()
