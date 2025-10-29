# Aurora Core FSM

Federated State Machine system for algorithmic trading on Binance Futures.

## Quick Start

1. **Setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Binance API credentials
   ```

2. **Choose trading environment:**
   - **Testnet** (recommended): `USE_TESTNET=true` in `.env`
   - **Mainnet** (real money): `USE_TESTNET=false` in `.env`

3. **Run the system:**
   ```bash
   python apps/reference/main.py
   ```

## Environment Configuration

### Testnet (Safe Development)
```bash
USE_TESTNET=true
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_API_SECRET=your_testnet_secret
```

### Mainnet (Real Trading)
```bash
USE_TESTNET=false
BINANCE_MAINNET_API_KEY=your_mainnet_key
BINANCE_MAINNET_API_SECRET=your_mainnet_secret
```

## Features

- **Real Order Book Data**: Uses Binance depth streams for accurate market data
- **Testnet/Mainnet Support**: Automatic switching based on `USE_TESTNET`
- **Centralized Configuration**: YAML + environment variables
- **Event-Driven Architecture**: FSM-based component communication

## Architecture

- `market_data`: Real-time Binance order book feeds
- `feature_engineering`: Technical indicators from market data
- `risk_management`: Position risk assessment
- `position_tracking`: Portfolio state management
- `decision_making`: Trade signal generation

## Configuration Files

- `config/aurora/trading.yaml`: Trading parameters
- `config/aurora/system.yaml`: System settings
- `.env`: Environment-specific secrets