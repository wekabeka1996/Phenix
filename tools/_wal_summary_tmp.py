import json
from collections import Counter
from pathlib import Path

path = Path('ops/wal/2026-02-08.jsonl')

verbs = Counter()
reject_codes = Counter()
reject_whys = Counter()

counts = Counter()

# Normalize verb names: allow both "EVT:FOO" and "FOO"


def norm(v: str | None) -> str | None:
    if not v:
        return None
    return v.split(':', 1)[1] if v.startswith(('EVT:', 'CMD:', 'DEC:', 'UPD:')) and ':' in v else v


for line in path.open('r', encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue

    verb_raw = obj.get('verb')
    verb = norm(verb_raw)
    if verb:
        verbs[verb] += 1

    pld = obj.get('pld') or {}

    if verb == 'FEATURES_CALCULATED':
        tf = pld.get('tf_sec')
        if tf is not None:
            tf = int(tf)
            if tf == 0:
                counts['features_tf0'] += 1
            elif tf > 0:
                counts['features_tfpos'] += 1

    if verb == 'PROCESS_STRATEGY':
        counts['cmd_process_strategy'] += 1

    if verb == 'TRADE_INTENT_PROPOSED':
        counts['intent_proposed'] += 1

    if verb == 'TRADE_INTENT_REJECTED':
        counts['intent_rejected'] += 1
        code = pld.get('reason_code')
        why = pld.get('why')
        tf = pld.get('tf_sec')
        if code:
            reject_codes[str(code)] += 1
        if why:
            reject_whys[str(why)] += 1
        if tf is not None and int(tf) == 0:
            counts['intent_rejected_tf0'] += 1

    if verb in ('OPEN', 'CLOSE', 'CANCEL'):
        counts['cmd_open_close_cancel'] += 1

    if 'ORDER' in (verb or '') or verb in ('ORDER_SUBMITTED', 'ORDER_ACK', 'ORDER_REJECTED', 'ORDER_FILLED'):
        counts['orderish'] += 1

    if 'FILL' in (verb or '') or verb in ('FILL', 'TRADE_FILLED', 'POSITION_OPENED', 'POSITION_CLOSED'):
        counts['execish'] += 1

print('WAL:', path)
print('Top verbs:', verbs.most_common(20))
print('FEATURES tf0=', counts['features_tf0'],
      ' tf>0=', counts['features_tfpos'])
print('CMD:PROCESS_STRATEGY:', counts['cmd_process_strategy'])
print('TRADE_INTENT_PROPOSED:', counts['intent_proposed'])
print('TRADE_INTENT_REJECTED:',
      counts['intent_rejected'], ' tf0=', counts['intent_rejected_tf0'])
print('Top reject codes:', reject_codes.most_common(15))
print('Top reject why:', reject_whys.most_common(10))
print('CMD OPEN/CLOSE/CANCEL:', counts['cmd_open_close_cancel'])
print('Order-ish:', counts['orderish'])
print('Exec-ish:', counts['execish'])
