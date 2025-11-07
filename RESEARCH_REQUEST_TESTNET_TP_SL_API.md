# 🔬 RESEARCH REQUEST: Binance Futures TP/SL API Behavior on TestNet

**Objective**: Research and document the behavior of Take-Profit and Stop-Loss orders on Binance Futures TestNet, specifically focusing on error codes and edge cases that cause order rejection.

**Target**:
- Binance Futures TestNet API documentation
- GitHub issues and discussions
- Stack Overflow and trading forums
- Community reports from traders using TP/SL orders

---

## Problem Statement

When executing the following flow on **Binance Futures TestNet**:

1. **Entry Order**: Place MARKET order → FILL received ✅
2. **TP/SL Placement**: Immediately after entry, place TAKE_PROFIT_MARKET and STOP_MARKET with `closePosition=true`
3. **Issue**: Orders rejected with specific error codes

### Observed Error Codes

```
ERROR 1: -2021 "Order would immediately trigger"
- Meaning: Stop price is already passed (SL too close to current price, or TP price already reached)
- Scenario: Entry at 157.38, TP attempt at 159.0 fails if current price already > 159.0
- Frequency: ~60-70% of TP/SL placement attempts

ERROR 2: -4116 "ClientOrderId is duplicated"
- Meaning: Same newClientOrderId used twice
- Scenario: Retry logic sends same order ID multiple times
- Frequency: ~30-40% when system retries after first failure

ERROR 3: -4164 "Order would cause position to increase"
- Meaning: STOP_MARKET with wrong parameters for close
- Scenario: Quantity mismatch or wrong side specification
- Frequency: Rare (~5%)
```

---

## Research Questions

### 1. **API Documentation Questions**

**Q1.1**: In Binance Futures TestNet, what are the exact timing requirements for TP/SL orders after entry execution?
- Is there a minimum delay after MARKET FILL before TP/SL can be placed?
- Should TP/SL prices be validated against real-time price BEFORE submission?
- Does Binance testnet have different validation rules than mainnet?

**Q1.2**: Error `-2021 "Order would immediately trigger"` - what does "immediately" mean?
- Is it a real-time validation against current mark price?
- Does it validate against bid/ask spread?
- Is there a safety margin (e.g., TP must be X% above current price)?

**Q1.3**: For `TAKE_PROFIT_MARKET` and `STOP_MARKET` orders with `closePosition=true`:
- Should quantity be `origQty: "0"` (as testnet suggests)?
- What are valid `workingType` values? (MARK_PRICE vs CONTRACT_PRICE)
- Does `priceProtect=true` affect validation?

### 2. **Order Rejection Handling**

**Q2.1**: When TP/SL order is rejected with `-2021`:
- Should the system retry after a delay?
- Should it recalculate prices based on current market?
- Or should it abandon the TP/SL and let the position run unprotected?

**Q2.2**: Duplicate order ID (`-4116`):
- How long should we wait before reusing a `newClientOrderId`?
- Does testnet clean up order IDs faster than mainnet?
- What's the recommended strategy for retry with same order?

**Q2.3**: Error Recovery:
- Are there idempotency guarantees in Binance API?
- What happens if we don't receive response but order is actually created?
- How do we detect "ghost" orders that failed at submission but exist on exchange?

### 3. **TestNet vs MainNet Differences**

**Q3.1**: Are there known differences in TP/SL behavior between testnet and mainnet?
- Does testnet have stricter validation?
- Does testnet have slower order processing?
- Are error codes consistent?

**Q3.2**: Real-world trading scenarios:
- Do professional traders use TP/SL with `closePosition=true` or separate OCO orders?
- What's the industry-standard approach for bracket orders on Binance?
- Do traders add delays before TP/SL placement?

### 4. **Accumulation of Ghost Orders**

**Q4.1**: If TP/SL orders fail to create:
- Does Binance track them anywhere?
- Can we query failed orders?
- Should we maintain local retry queue?

**Q4.2**: Resource Management:
- If system reserves margin for failed TP/SL, when is it released?
- How long does testnet keep order history?
- What happens to open orders on reconnect?

---

## Expected Research Output

### For Each Error Code:
1. **Root Cause**: Why does Binance reject the order?
2. **Detection**: How to detect this error before/after submission?
3. **Prevention**: Best practices to avoid the error
4. **Recovery**: Recommended handling strategy
5. **Evidence**:
   - Official Binance documentation reference
   - GitHub issue or discussion link
   - Community forum link with solution
   - Code example from real traders

### Implementation Recommendations:
- Validated price calculation logic
- Retry strategy with exponential backoff
- Margin reservation cleanup on rejection
- Fallback strategies (e.g., use LIMIT orders instead of MARKET)
- Monitoring/alerting for rejection patterns

---

## Search Keywords for Research

### Binance Documentation:
- "TAKE_PROFIT_MARKET closePosition testnet"
- "Order would immediately trigger -2021"
- "Binance Futures bracket orders best practices"
- "newClientOrderId duplicate error -4116"
- "workingType MARK_PRICE validation"

### GitHub / Issues:
- binance/binance-spot-api-docs issues
- binance-connector-python issues
- ccxt issues (Binance futures)
- "TP/SL order rejected" "immediately trigger"

### Forums / Communities:
- reddit.com/r/algotrading "TP/SL Binance"
- Stack Overflow "binance futures API"
- Binance Developers Discord/Telegram
- Trading bot GitHub discussions

### Real-World Implementations:
- Search GitHub for `place_take_profit_market` implementations
- Look for error handling patterns in production trading bots
- Find margin management strategies in open-source traders

---

## Priority Research Order

**🔴 CRITICAL** (Must resolve):
1. Error `-2021` root cause and prevention
2. Margin reservation cleanup on rejection
3. Ghost order detection and cleanup

**🟡 HIGH** (Should understand):
4. TestNet vs MainNet differences
5. Industry-standard TP/SL placement patterns
6. Retry strategy best practices

**🟢 MEDIUM** (Nice to have):
7. Alternative order types (OCO vs bracket)
8. Performance optimization for TP/SL latency
9. Risk management strategies

---

## Expected Findings Format

```markdown
## Finding: Error -2021 "Order would immediately trigger"

### Root Cause
[Description from Binance docs or community]

### Reproduction
[Steps to reproduce]

### Prevention
[How to avoid this error]

### Recovery
[How to handle when it occurs]

### References
- Link to Binance documentation
- Link to GitHub issue/discussion
- Link to community forum discussion
- Code example

### Recommended Implementation
[Code pattern to use in production]
```

---

## Success Criteria

Research is complete when we can answer:
- ✅ Why do TP/SL orders fail on TestNet?
- ✅ How should we validate prices BEFORE submission?
- ✅ What's the best retry strategy?
- ✅ How should we clean up failed orders?
- ✅ What's the difference between TestNet and MainNet behavior?
- ✅ What do professional traders do in this scenario?

---

## Context for Model

**System**: Aurora/QuantumTraderX trading bot on Binance Futures
**Environment**: TestNet (hybrid_live_data_testnet_exec mode)
**Symbols**: ETHUSDT, SOLUSDT
**Pattern**: Entry (MARKET) → TP/SL (MARKET with closePosition=true)
**Issue**: ~60-70% of TP/SL placements fail with -2021, causing:
- Ghost orders accumulating in pending state
- Margin being reserved but never released
- Eventually blocking new trades when margin > limit

**Constraint**: Need production-grade solution that works on BOTH testnet and mainnet
