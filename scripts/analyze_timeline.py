"""Analyze timeline from aurora_core.log."""
import re
from datetime import datetime

log_path = r'c:\Users\user\Music\Phenix\logs\aurora_core.log'
events = []

with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        # Parse timestamp and key events
        match = re.match(
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*?'
            r'(📊.*Tick|FEATURES_CALCULATED|WebSocket|Error.*-1021|periodic)',
            line
        )
        if match:
            ts_str = match.group(1)
            event = match.group(2)[:55]
            ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S,%f')
            events.append((ts, event))

print('=== Timeline Analysis ===')
print(f'Total key events: {len(events)}\n')

# Group by type
ticks = [(ts, ev) for ts, ev in events if 'Tick' in ev]
features = [(ts, ev) for ts, ev in events if 'FEATURES' in ev]

print(f'Tick events: {len(ticks)}')
print(f'Features events: {len(features)}')

# Calculate gaps between ticks
if len(ticks) > 1:
    print('\n=== Tick Gaps ===')
    gaps = []
    for i in range(1, min(10, len(ticks))):
        gap = (ticks[i][0] - ticks[i-1][0]).total_seconds()
        gaps.append(gap)
        print(f'{ticks[i-1][0].strftime("%H:%M:%S")} -> {ticks[i][0].strftime("%H:%M:%S")}: {gap:.1f}s')

    if gaps:
        print(f'\nAvg gap: {sum(gaps)/len(gaps):.1f}s')
        print(f'Max gap: {max(gaps):.1f}s')
        print(f'Min gap: {min(gaps):.1f}s')

# Show all events with gaps
print('\n=== All Events with Gaps > 5s ===')
prev_ts = None
for ts, event in events[:40]:
    gap_str = ''
    if prev_ts:
        delta = (ts - prev_ts).total_seconds()
        if delta > 5:
            gap_str = f' [GAP: {delta:.0f}s]'
    print(f'{ts.strftime("%H:%M:%S")} - {event}{gap_str}')
    prev_ts = ts
