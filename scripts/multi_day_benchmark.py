from _compat import execute, reexport

_TARGET = "benchmarks/multi_day_benchmark.py"

if __name__ == "__main__":
    execute(_TARGET)
else:
    reexport(_TARGET, globals())

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
        try:
            L, V = torch.linalg.eigh(gram)
        except RuntimeError:
            # Fallback: return identity projection if eigh fails
            return x_flat.view(orig_shape)

        L = L.flip(0).clamp(min=1e-8)
        V = V.flip(1)

        # Cumulative Energy Thresholding
        total_e = L.sum()
        if total_e <= 0:
            return x_flat.view(orig_shape)

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

        # Final safety check
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
        # INSERTING THE SPECTRAL COMPONENT
        self.rectifier = SoftSpectralGate(
            energy_threshold=0.85, scale_factor=15.0)

    def forward(self, x):
        h, _ = self.lstm(x)

        # SPECTRAL RECTIFICATION
        h_clean = self.rectifier(h)

        # Stability: Clamp & Replace NaN
        h_clean = torch.clamp(h_clean, -10, 10)
        h_clean = torch.where(torch.isnan(h_clean), h, h_clean)

        last_h = h_clean[:, -1, :]

        action_mean = self.actor_mean(last_h)
        action_std = (self.actor_std.exp() +
                      0.1).expand_as(action_mean)  # Min std = 0.1
        value = self.critic(last_h)
        return action_mean, action_std, value

# ==========================================
# 3. REAL MARKET ENVIRONMENT
# ==========================================


class RealMarketEnv:
    def __init__(self, data, returns, seq_len=None):
        self.data = data
        self.returns = returns
        # Adaptive seq_len: min(10, max(3, len(data)//4))
        if seq_len is None:
            seq_len = max(3, min(10, len(data) // 4))
        self.seq_len = seq_len
        self.idx = 0
        self.max_steps = len(data) - self.seq_len - 1

    def reset(self):
        self.idx = 0
        return self._get_obs()

    def _get_obs(self):
        # Sliding Window
        window = self.data[self.idx: self.idx + self.seq_len]
        # Pad if not enough data
        if len(window) < self.seq_len:
            pad = torch.zeros(self.seq_len - len(window), window.shape[1])
            window = torch.cat([window, pad], dim=0)
        return window.unsqueeze(0)  # [1, Seq, Feat]

    def step(self, action):
        idx_ret = self.idx + self.seq_len
        if idx_ret < len(self.returns):
            next_ret = self.returns[idx_ret]
        else:
            next_ret = 0.0  # Terminal state reward
        reward = action * next_ret * 100.0

        self.idx += 1
        done = self.idx >= self.max_steps

        next_obs = self._get_obs() if not done else torch.zeros_like(self._get_obs())
        return next_obs, reward, done

# ==========================================
# 4. TRAINING ENGINE
# ==========================================


def train_on_real_data(agent_name, model, data, returns, episodes=30, verbose=False):
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    rewards_history = []

    if verbose:
        print(f"\n--- Training {agent_name} ---")

    # Skip training if too little data
    if len(data) < 5:
        if verbose:
            print(f"  WARNING: Only {len(data)} samples, skipping training")
        return [0.0] * episodes

    for ep in range(episodes):
        env = RealMarketEnv(data, returns)  # Adaptive seq_len
        state = env.reset()
        done = False
        total_reward = 0
        step_count = 0

        while not done and step_count < len(data) - 2:
            mu, std, val = model(state)

            # Safety checks for NaN/Inf - VERY aggressive
            mu = torch.where(torch.isnan(mu), torch.zeros_like(mu), mu)
            mu = torch.where(torch.isinf(mu), torch.zeros_like(mu), mu)
            mu = torch.clamp(mu, -5, 5)

            std = torch.where(torch.isnan(
                std), torch.ones_like(std) * 0.5, std)
            std = torch.clamp(std, 0.05, 5)

            val = torch.clamp(val, -100, 100)

            dist = Normal(mu, std)
            action = dist.sample()

            # Clamp action to [-1, 1]
            action_clipped = torch.clamp(action, -1.0, 1.0)

            next_state, reward, done = env.step(action_clipped.item())

            # PPO-style loss (simplified)
            log_prob = dist.log_prob(action)
            advantage = reward - val.item()

            loss = -log_prob * advantage + 0.5 * \
                F.mse_loss(val, torch.tensor([[reward]]))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_reward += reward
            state = next_state
            step_count += 1

        rewards_history.append(total_reward)
        if verbose and (ep+1) % 5 == 0:
            print(f"  Episode {ep+1}: Total Profit = {total_reward:.4f} bps")

    return rewards_history


# ==========================================
# 5. MULTI-DAY EXECUTION
# ==========================================
if __name__ == "__main__":
    # Date range
    start_date = datetime(2026, 1, 12)
    end_date = datetime(2026, 1, 18)

    # Collect all available dates
    dates = []
    current = start_date
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        csv_path = f'data/recorder/{date_str}/DOGEUSDT_900.csv'
        if os.path.exists(csv_path):
            dates.append(date_str)
        current += timedelta(days=1)

    print(f"Found {len(dates)} dates with data: {dates}\n")

    # Storage for results
    all_western_rewards = {}
    all_soviet_rewards = {}

    INPUT_DIM = None
    HIDDEN_DIM = 64
    ACTION_DIM = 1

    # Process each date
    for date_str in dates:
        csv_path = f'data/recorder/{date_str}/DOGEUSDT_900.csv'
        print(f"📊 Processing {date_str}...")

        # Load data
        data, returns, sample_count = load_and_process_data(csv_path)
        print(
            f"   Loaded {sample_count} samples with {data.shape[1]} features")

        if INPUT_DIM is None:
            INPUT_DIM = data.shape[1]

        # Initialize models
        western_bot = WesternModel(INPUT_DIM, HIDDEN_DIM, ACTION_DIM)
        soviet_bot = SovietWesternModel(INPUT_DIM, HIDDEN_DIM, ACTION_DIM)

        # Train (quiet mode)
        w_rewards = train_on_real_data(
            "Western", western_bot, data, returns, episodes=20, verbose=False)
        s_rewards = train_on_real_data(
            "Soviet", soviet_bot, data, returns, episodes=20, verbose=False)

        # Store results
        all_western_rewards[date_str] = np.mean(w_rewards[-5:])
        all_soviet_rewards[date_str] = np.mean(s_rewards[-5:])

        print(f"   Western Bot: {all_western_rewards[date_str]:.4f} bps")
        print(f"   Soviet Bot:  {all_soviet_rewards[date_str]:.4f} bps")
        print(
            f"   Advantage:   {all_soviet_rewards[date_str] - all_western_rewards[date_str]:+.4f} bps\n")

    # ==========================================
    # AGGREGATE ANALYSIS
    # ==========================================
    print("\n" + "="*70)
    print("MULTI-DAY AGGREGATE RESULTS (2026-01-12 to 2026-01-18)")
    print("="*70)

    dates_sorted = sorted(all_western_rewards.keys())
    western_values = [all_western_rewards[d] for d in dates_sorted]
    soviet_values = [all_soviet_rewards[d] for d in dates_sorted]

    print(f"\nWestern Bot (Baseline):")
    print(f"  Mean Profit:   {np.mean(western_values):.4f} bps")
    print(f"  Std Dev:       {np.std(western_values):.4f}")
    print(
        f"  Min/Max:       {np.min(western_values):.4f} / {np.max(western_values):.4f}")

    print(f"\nSoviet-Western Bot (Spectral):")
    print(f"  Mean Profit:   {np.mean(soviet_values):.4f} bps")
    print(f"  Std Dev:       {np.std(soviet_values):.4f}")
    print(
        f"  Min/Max:       {np.min(soviet_values):.4f} / {np.max(soviet_values):.4f}")

    advantage_mean = np.mean(soviet_values) - np.mean(western_values)
    advantage_pct = (advantage_mean / abs(np.mean(western_values))
                     ) * 100 if np.mean(western_values) != 0 else 0

    print(f"\n🏆 SOVIET ADVANTAGE:")
    print(f"  Absolute:      {advantage_mean:+.4f} bps")
    print(f"  Relative:      {advantage_pct:+.2f}%")

    win_rate = sum(1 for w, s in zip(western_values, soviet_values)
                   if s > w) / len(dates_sorted) * 100
    print(f"  Win Rate:      {win_rate:.1f}%")

    # ==========================================
    # PLOTTING
    # ==========================================
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))

    # Plot 1: Daily comparison
    ax1 = axes[0]
    x = np.arange(len(dates_sorted))
    width = 0.35
    ax1.bar(x - width/2, western_values, width,
            label='Western Bot (Baseline)', color='gray', alpha=0.7)
    ax1.bar(x + width/2, soviet_values, width,
            label='Soviet-Western Bot (Spectral)', color='red', alpha=0.8)
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Avg Profit (bps)')
    ax1.set_title(
        'Daily Profit Comparison: DOGEUSDT 15m (2026-01-12 to 2026-01-18)')
    ax1.set_xticks(x)
    ax1.set_xticklabels(dates_sorted, rotation=45)
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')

    # Plot 2: Cumulative advantage
    ax2 = axes[1]
    advantages = [s - w for s, w in zip(soviet_values, western_values)]
    colors = ['green' if adv > 0 else 'red' for adv in advantages]
    ax2.bar(x, advantages, color=colors, alpha=0.7)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.set_xlabel('Date')
    ax2.set_ylabel('Soviet Advantage (bps)')
    ax2.set_title('Daily Soviet-Western Advantage')
    ax2.set_xticks(x)
    ax2.set_xticklabels(dates_sorted, rotation=45)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig('multi_day_benchmark_results.png',
                dpi=150, bbox_inches='tight')
    print(f"\n✓ Plot saved as multi_day_benchmark_results.png")
    plt.show()

    # Save detailed report
    with open('multi_day_benchmark_report.txt', 'w') as f:
        f.write("="*70 + "\n")
        f.write("MULTI-DAY REAL MARKET BENCHMARK REPORT\n")
        f.write("DOGEUSDT 15m Candles (2026-01-12 to 2026-01-18)\n")
        f.write("="*70 + "\n\n")

        f.write("DAILY RESULTS:\n")
        f.write("-"*70 + "\n")
        for date, w_val, s_val in zip(dates_sorted, western_values, soviet_values):
            adv = s_val - w_val
            f.write(
                f"{date}: Western={w_val:>7.4f} bps | Soviet={s_val:>7.4f} bps | Adv={adv:>+7.4f} bps\n")

        f.write("\n" + "="*70 + "\n")
        f.write("AGGREGATE STATISTICS:\n")
        f.write("-"*70 + "\n")
        f.write(f"Western Bot Mean:     {np.mean(western_values):.4f} bps\n")
        f.write(f"Western Bot Std:      {np.std(western_values):.4f}\n")
        f.write(f"Soviet Bot Mean:      {np.mean(soviet_values):.4f} bps\n")
        f.write(f"Soviet Bot Std:       {np.std(soviet_values):.4f}\n")
        f.write(f"\nAbsolute Advantage:   {advantage_mean:+.4f} bps\n")
        f.write(f"Relative Advantage:   {advantage_pct:+.2f}%\n")
        f.write(f"Soviet Win Rate:      {win_rate:.1f}%\n")

    print("✓ Report saved as multi_day_benchmark_report.txt")
