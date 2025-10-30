# Testnet Monitoring Metrics

**RID:** `AURORA_TESTNET_PREP_V1`
**Purpose:** Define key metrics to monitor during testnet operation

## Activity Metrics

### Trading Activity
- **Orders Placed:** Total number of entry/exit orders executed per hour
- **Order Fill Rate:** Percentage of orders that receive fills (target: >95%)
- **Intent Generation:** Number of TRADE_INTENT_PROPOSED events per hour
- **Position Changes:** Number of positions opened/closed per session

### System Activity
- **API Calls:** Total Binance API calls per minute
- **WebSocket Messages:** Market data messages received per second
- **FSM Transitions:** State transitions per minute across all domains
- **Event Emissions:** EVT:* events emitted per minute

## Performance Metrics

### Latency Metrics
- **Order Placement Latency:** Time from DEC:OPEN to Binance confirmation (target: <500ms)
- **Fill Latency:** Time from order placement to fill confirmation (target: <2000ms)
- **Signal Processing:** Time from market tick to trade intent (target: <100ms)
- **FSM Processing:** Time for state transitions (target: <50ms)

### Resource Metrics
- **CPU Usage:** System CPU utilization (target: <70%)
- **Memory Usage:** RAM consumption (target: <1GB)
- **Disk I/O:** Log file writes per minute
- **Network I/O:** Bandwidth usage for API/WebSocket

## Reliability Metrics

### Error Metrics
- **API Error Rate:** Percentage of failed Binance API calls (target: <5%)
- **FSM Error Rate:** Percentage of failed state transitions (target: <1%)
- **WebSocket Disconnects:** Number of reconnection events per hour (target: <6)
- **TTL Timeouts:** Orders timing out before execution (target: 0)

### Circuit Breaker Metrics
- **Circuit State:** Current state (CLOSED/OPEN/HALF_OPEN)
- **Open Events:** Number of times circuit opened per day
- **Recovery Time:** Average time to recover from OPEN state
- **Failure Patterns:** Most common failure reasons

## Financial Metrics

### PnL Metrics
- **Realized PnL:** Cumulative profit/loss from closed positions
- **Unrealized PnL:** Current open position profit/loss
- **Win Rate:** Percentage of profitable trades (target: >50%)
- **Profit Factor:** Gross profit / Gross loss ratio

### Risk Metrics
- **Max Drawdown:** Largest peak-to-valley decline (target: <10%)
- **VaR (95%):** Value at Risk estimate for current positions
- **Position Size:** Average position size as % of account
- **Leverage Usage:** Current leverage vs maximum allowed

## Market Data Quality Metrics

### Data Quality
- **Data Lag:** Age of latest market data (target: <1000ms)
- **Sequence Gaps:** Missing sequence numbers in order book updates
- **Price Anomalies:** Invalid or outlier price observations
- **Volume Anomalies:** Unusual volume spikes or gaps

### Connectivity Metrics
- **WebSocket Uptime:** Percentage of time WebSocket connected (target: >99%)
- **Reconnection Frequency:** Number of reconnections per hour
- **Message Loss:** Estimated percentage of lost WebSocket messages
- **API Availability:** Binance API response success rate

## Observability Metrics

### Logging Metrics
- **Log Volume:** Number of log entries per minute
- **Error Log Rate:** Percentage of ERROR level logs (target: <5%)
- **Warning Log Rate:** Percentage of WARNING level logs (target: <10%)
- **Debug Coverage:** Percentage of operations with debug traces

### Debug API Metrics
- **API Uptime:** Debug API availability (if implemented)
- **Request Rate:** Debug API requests per minute
- **Response Time:** Average debug API response time
- **Error Rate:** Debug API error responses

## Alert Thresholds

### Critical Alerts (Immediate Action Required)
- Circuit Breaker OPEN for >5 minutes
- API Error Rate >20%
- WebSocket disconnected for >10 minutes
- System CPU >90% or Memory >2GB
- Financial loss >5% of account in single trade

### Warning Alerts (Monitor Closely)
- Order placement latency >2000ms
- Fill rate <90%
- WebSocket reconnections >10 per hour
- Data lag >2000ms
- Single trade loss >2% of account

### Info Alerts (Track Trends)
- Daily PnL summary
- Weekly performance statistics
- System resource usage trends
- Market condition changes

## Monitoring Tools

### Built-in Monitoring
- **Aurora Logs:** `logs/aurora_core.log` (JSON format)
- **Debug API:** `/debug/{rid}`, `/metrics` (if implemented)
- **FSM Events:** EVT:* event emissions
- **Circuit Breaker:** State change logs

### External Monitoring
- **Binance Dashboard:** Order status, positions, balance
- **System Tools:** `top`, `htop`, `iostat`, `netstat`
- **Log Analysis:** `grep`, `awk`, custom log parsers

### Dashboard Setup
1. **Real-time Dashboard:** Web interface showing key metrics
2. **Alert System:** Email/SMS notifications for threshold breaches
3. **Historical Tracking:** Database storage for trend analysis
4. **Reporting:** Daily/weekly performance reports

## Success Criteria

### Operational Success
- System runs for 24+ hours without manual intervention
- All orders execute within expected latency bounds
- No critical errors or system crashes
- Circuit breaker remains CLOSED >95% of time

### Performance Success
- Average order placement latency <500ms
- Fill rate >95%
- API error rate <5%
- WebSocket uptime >99%

### Financial Success
- Positive daily PnL (not required for technical testing)
- No catastrophic losses (>10% drawdown)
- Risk metrics within acceptable bounds
- Position management working correctly

## Data Collection

### Automated Collection
```python
# Example metrics collection (to be implemented)
metrics = {
    'timestamp': datetime.now(),
    'orders_placed': count_orders_last_hour(),
    'api_errors': count_api_errors_last_hour(),
    'avg_latency': calculate_avg_order_latency(),
    'pnl_realized': get_realized_pnl(),
    'circuit_state': get_circuit_breaker_state()
}
```

### Manual Checks
- Daily log review for anomalies
- Weekly performance analysis
- Monthly system health assessment
- Ad-hoc debugging for issues

## Continuous Improvement

### Metric Review
- Weekly review of all metrics
- Identify performance bottlenecks
- Adjust alert thresholds based on observed behavior
- Add new metrics as needed

### System Tuning
- Optimize configuration based on observed performance
- Implement performance improvements
- Enhance error handling based on failure patterns
- Update monitoring based on operational experience</content>
<parameter name="filePath">c:\Users\job11\Music\Olimp_v1\docs\TESTNET_MONITORING.md