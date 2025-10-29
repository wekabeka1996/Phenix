# Binance API Keys Setup Guide

## Overview

Aurora Core requires Binance Futures API credentials to execute trades. For testnet deployment, you need **testnet-specific API keys** that work only on Binance Futures Testnet.

⚠️ **IMPORTANT**: Never use mainnet API keys for testnet, and vice versa. Testnet keys only work on testnet.binancefuture.com.

## Getting Testnet API Keys

### Step 1: Create Binance Testnet Account
1. Go to [Binance Futures Testnet](https://testnet.binancefuture.com/)
2. Register/Login with your Binance account
3. Complete any required verification steps

### Step 2: Generate API Keys
1. In the testnet dashboard, click on **API Management** (left sidebar)
2. Click **Create API Key**
3. Set permissions:
   - ✅ **Enable Futures** (required for futures trading)
   - ✅ **Enable Spot & Margin Trading** (recommended)
   - ❌ **Perm_R_Orders** (read-only orders - optional)
   - ❌ **Perm_W_Orders** (place orders - will be enabled)
   - ❌ **Perm_W_Withdrawals** (withdrawals - keep disabled for security)
4. Complete 2FA verification
5. **Save your API Key and Secret immediately** - they won't be shown again!

### Step 3: Get Testnet USDT
1. In testnet dashboard, go to **Wallet** → **Futures Wallet**
2. Click **Transfer** to get test USDT from spot wallet
3. Transfer some test USDT to your futures account for trading

## Environment Variables Setup

### Option 1: .env File (Recommended)

Create a `.env` file in the project root (copy from `.env.example`):

```bash
# Testnet Configuration
USE_TESTNET=true
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret_here

# Read-only keys (optional, for account monitoring)
BINANCE_RO_API_KEY=your_readonly_api_key_here
BINANCE_RO_API_SECRET=your_readonly_api_secret_here

# Logging
LOG_LEVEL=INFO
TRADING_ENV=testnet
```

### Option 2: System Environment Variables

Set environment variables in your system:

**Windows (PowerShell):**
```powershell
$env:USE_TESTNET="true"
$env:BINANCE_TESTNET_API_KEY="your_testnet_api_key_here"
$env:BINANCE_TESTNET_API_SECRET="your_testnet_api_secret_here"
$env:LOG_LEVEL="INFO"
$env:TRADING_ENV="testnet"
```

**Linux/macOS:**
```bash
export USE_TESTNET=true
export BINANCE_TESTNET_API_KEY="your_testnet_api_key_here"
export BINANCE_TESTNET_API_SECRET="your_testnet_api_secret_here"
export LOG_LEVEL=INFO
export TRADING_ENV=testnet
```

## Security Best Practices

### 🔐 API Key Security
- **Never commit API keys to version control**
- **Use separate keys for testnet and mainnet**
- **Restrict API key permissions** (disable withdrawals)
- **Regenerate keys regularly**
- **Monitor API key usage** in Binance dashboard

### 🔐 Environment File Security
- Add `.env` to `.gitignore`
- Set file permissions to read-only for your user only
- Never share `.env` files
- Use different `.env` files for different environments

### 🔐 Network Security
- Use HTTPS for all API communications (handled automatically)
- Enable 2FA on your Binance account
- Monitor account activity regularly

## Verification

After setup, verify your configuration:

```bash
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Test configuration loading
python -c "from apps.reference.config_loader import ConfigLoader; c = ConfigLoader(); config = c.load_config(); print('✅ Config loaded successfully'); print(f'USE_TESTNET: {config.use_testnet}'); print(f'API_KEY configured: {bool(config.binance_api_key)}')"
```

Expected output:
```
✅ Config loaded successfully
USE_TESTNET: True
API_KEY configured: True
```

## Troubleshooting

### "Required environment variable 'BINANCE_TESTNET_API_KEY' is not set"
- Check that `.env` file exists in project root
- Verify variable names match exactly (case-sensitive)
- Ensure no extra spaces around `=`
- Restart your terminal/command prompt after setting system variables

### "API credentials not found in environment, falling back to shadow mode"
- Same as above - check environment variable setup
- Verify you're using the correct variable names for testnet vs mainnet

### "Invalid API key" errors
- Verify you copied the API key correctly (no extra characters)
- Ensure you're using testnet keys on testnet.binancefuture.com
- Check that Futures trading is enabled for the API key

## Switching Between Testnet and Mainnet

**For Testnet (Development/Safe):**
```bash
USE_TESTNET=true
# Use BINANCE_TESTNET_API_KEY/SECRET
```

**For Mainnet (Real Trading/Dangerous):**
```bash
USE_TESTNET=false
# Use BINANCE_MAINNET_API_KEY/SECRET
# ⚠️ ENSURE FUTURES TRADING ENABLED AND SUFFICIENT BALANCE!
```

Always double-check `USE_TESTNET=true` before running in development!</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\secrets.md