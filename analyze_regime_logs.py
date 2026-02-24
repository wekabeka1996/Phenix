# -*- coding: utf-8 -*-
import re, os, sys, io
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
LOG_DIR  = "c:/Users/user/Music/Phenix/logs"
SYMBOLS  = ["BTCUSDT","ETHUSDT","SOLUSDT","DOGEUSDT","XRPUSDT"]
ALL_REGIMES = ["UNCERTAIN","LOW_VOLATILITY","HIGH_VOLATILITY","MEAN_REVERSION",
               "TREND_UP","TREND_DOWN","FLAT_LOW","FLAT_NORMAL","FLAT_HIGH"]

def parse_ts(s):
    try: return datetime.strptime(s, "%Y-%m-%d %H:%M:%S,%f")
    except: return None

def load_log(path):
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8", errors="replace") as f: return f.readlines()

def collect_files():
    base = os.path.join(LOG_DIR, "domain_regime_detector.log")
    files = [base] if os.path.exists(base) else []
    for i in range(1, 10):
        rotated = base + "." + str(i)
        if os.path.exists(rotated): files.append(rotated)
    return files

def print_sample(lines, label):
    sep = "=" * 72
    print("")
    print(sep)
    print("  " + label)
    print(sep)
    for i, l in enumerate(lines):
        print("  %4d: %s" % (i+1, l.rstrip()))

RE_TRANS = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+).*?"
    r"\[([A-Z]+USDT)\] Regime updated:\s*(\S+)\s*.\s*(\w+)\s*\(raw=(\w+),\s*confidence=([\d.]+)"
)

def parse_transitions(lines):
    trans = defaultdict(list)
    for line in lines:
        m = RE_TRANS.search(line)
        if not m: continue
        ts = parse_ts(m.group(1))
        if not ts: continue
        sym = m.group(2)
        frm = m.group(3).strip()
        to  = m.group(4).strip()
        cf  = float(m.group(6))
        if frm in ("", "None"): frm = "NONE"
        frm = frm.replace(chr(8709), "NONE").strip()
        trans[sym].append((ts, frm, to, cf))
    for s in trans: trans[s].sort(key=lambda x: x[0])
    return trans

def time_stats(evts):
    rs = defaultdict(float)
    rd = defaultdict(list)
    for i, (ts, frm, to, cf) in enumerate(evts):
        nxt = evts[i+1][0] if i+1 < len(evts) else evts[-1][0]
        dur = (nxt - ts).total_seconds()
        if dur > 0:
            rs[to] += dur
            rd[to].append(dur)
    return rs, rd

def calc_tpd(evts):
    if len(evts) < 2: return 0.0
    span = (evts[-1][0] - evts[0][0]).total_seconds() / 86400
    if span <= 0: return 0.0
    real = sum(1 for (_, f, _, _) in evts if f != "NONE")
    return real / span

def search_aux(path, keywords, maxn=50):
    if not os.path.exists(path): return []
    results = []
    kl = [k.lower() for k in keywords]
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if any(k in line.lower() for k in kl):
                results.append(line.rstrip())
    return results[:maxn]

def main():
    SEP = "=" * 72
    print(SEP)
    print("  REGIME DETECTION LOG ANALYZER")
    print("  Run at: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print(SEP)

    files = collect_files()
    print("")
    print("[FILES FOUND]")
    for f in files:
        sz = os.path.getsize(f)
        print("  %-45s %10d bytes" % (os.path.basename(f), sz))

    all_lines = []
    for f in files:
        ls = load_log(f)
        print("  Loaded %d lines from %s" % (len(ls), os.path.basename(f)))
        all_lines.extend(ls)
    total = len(all_lines)
    print("")
    print("  Total lines: %d" % total)

    # --- Section 1: First 100 lines ---
    print_sample(all_lines[:100], "FIRST 100 LINES OF domain_regime_detector.log")

    # --- Section 2: Middle 100 lines ---
    mid = total // 2
    print_sample(all_lines[mid-50:mid+50], "MIDDLE 100 LINES (around line %d)" % mid)

    # --- Section 3: Pattern search ---
    print("")
    print(SEP)
    print("  REGIME KEYWORD OCCURRENCES")
    print(SEP)
    for regime in ALL_REGIMES:
        n = sum(1 for l in all_lines if regime in l)
        bar = "#" * min(n // 2, 55)
        print("  %-22s: %5d  %s" % (regime, n, bar))

    # --- Section 4: Transitions ---
    trans = parse_transitions(all_lines)

    print("")
    print(SEP)
    print("  PER-SYMBOL TRANSITION HISTORY")
    print(SEP)
    for sym in SYMBOLS:
        evts = trans.get(sym, [])
        print("")
        print("  [%s]  Total transitions: %d" % (sym, len(evts)))
        if not evts:
            print("    (no data)")
            continue
        print("  %4s  %-22s  %-18s  %-18s  %6s  %10s" % ("#","Timestamp","From","To","Conf","Next In"))
        print("  " + "-"*4 + "  " + "-"*22 + "  " + "-"*18 + "  " + "-"*18 + "  " + "-"*6 + "  " + "-"*10)
        for i, (ts, frm, to, cf) in enumerate(evts):
            if i+1 < len(evts):
                d = (evts[i+1][0] - ts).total_seconds()
                ds = "%.0fm" % (d/60) if d < 7200 else "%.1fh" % (d/3600)
            else:
                ds = "(last)"
            print("  %4d  %-22s  %-18s  %-18s  %6.3f  %10s" % (
                i+1, ts.strftime("%Y-%m-%d %H:%M:%S"), frm, to, cf, ds))


    # --- Section 5: Statistics ---
    print("")
    print(SEP)
    print("  REGIME TIME STATISTICS")
    print(SEP)
    for sym in SYMBOLS:
        evts = trans.get(sym, [])
        if not evts:
            print("")
            print("  [%s]  No data." % sym)
            continue
        rs, rd = time_stats(evts)
        total_s = sum(rs.values())
        tpday = calc_tpd(evts)
        first_ts, last_ts = evts[0][0], evts[-1][0]
        span_h = (last_ts - first_ts).total_seconds() / 3600
        unc_pct = rs.get("UNCERTAIN", 0) / total_s * 100 if total_s else 0
        print("")
        print("  [%s]" % sym)
        print("    Period   : %s -> %s  (%.1fh)" % (
            first_ts.strftime("%Y-%m-%d %H:%M"),
            last_ts.strftime("%Y-%m-%d %H:%M"), span_h))
        print("    Transitions: %d total  |  %.2f/day" % (len(evts), tpday))
        print("    >>> %% time in UNCERTAIN: %.1f%%" % unc_pct)
        print("    " + "-"*22 + "  " + "-"*7 + "  " + "-"*8 + "  " + "-"*8 + "  " + "-"*8 + "  " + "-"*4)
        print("    %-22s  %7s  %8s  %8s  %8s  %4s" % ("Regime","Time%%","AvgDur","MinDur","MaxDur","N"))
        print("    " + "-"*22 + "  " + "-"*7 + "  " + "-"*8 + "  " + "-"*8 + "  " + "-"*8 + "  " + "-"*4)
        for regime in sorted(rs.keys()):
            s = rs[regime]; d = rd[regime]
            pct = s / total_s * 100 if total_s else 0
            avg = sum(d) / len(d) / 60 if d else 0
            mn  = min(d) / 60 if d else 0
            mx  = max(d) / 60 if d else 0
            print("    %-22s  %6.1f%%  %6.1fm  %6.1fm  %6.1fm  %4d" % (
                regime, pct, avg, mn, mx, len(d)))

    # --- Cross-symbol table ---
    print("")
    print(SEP)
    print("  CROSS-SYMBOL %% TIME IN EACH REGIME")
    print(SEP)
    sym_rs = {}; all_r = set()
    for sym in SYMBOLS:
        evts = trans.get(sym, [])
        if evts:
            rs, _ = time_stats(evts)
            sym_rs[sym] = rs
            all_r.update(rs.keys())
    header = "  %-22s" % "Regime" + "".join("  %10s" % s for s in SYMBOLS)
    print(header)
    print("  " + "-"*22 + "".join("  " + "-"*10 for _ in SYMBOLS))
    for regime in sorted(all_r):
        vals = []
        for sym in SYMBOLS:
            rs2 = sym_rs.get(sym, {})
            tot = sum(rs2.values())
            vals.append("%.1f%%" % (rs2.get(regime,0)/tot*100) if tot else "   -")
        row = "  %-22s" % regime + "".join("  %10s" % v for v in vals)
        print(row)


    # --- Transitions per day ---
    print("")
    print(SEP)
    print("  TRANSITIONS PER DAY")
    print(SEP)
    for sym in SYMBOLS:
        evts = trans.get(sym, [])
        t = calc_tpd(evts) if evts else 0
        real = sum(1 for (_, f, _, _) in evts if f != "NONE")
        print("  %-12s: %5.2f/day  (%d real transitions)" % (sym, t, real))

    # --- Confidence per regime ---
    print("")
    print(SEP)
    print("  AVERAGE CONFIDENCE PER REGIME")
    print(SEP)
    for sym in SYMBOLS:
        evts = trans.get(sym, [])
        if not evts: continue
        cb = defaultdict(list)
        for (_, _, to, cf) in evts: cb[to].append(cf)
        print("")
        print("  [%s]" % sym)
        for r in sorted(cb):
            v = cb[r]
            print("    %-22s: avg=%.4f  min=%.4f  max=%.4f  n=%d" % (
                r, sum(v)/len(v), min(v), max(v), len(v)))

    # --- Hysteresis events ---
    hre = re.compile(r"\[([A-Z]+USDT)\] Hysteresis: stable regime transition (\w+) -> (\w+)")
    hc = defaultdict(lambda: defaultdict(int))
    for line in all_lines:
        m = hre.search(line)
        if m: hc[m.group(1)][(m.group(2), m.group(3))] += 1
    print("")
    print(SEP)
    print("  HYSTERESIS CONFIRMED TRANSITIONS")
    print(SEP)
    for sym in SYMBOLS:
        if sym not in hc:
            print("  %s: (none)" % sym)
            continue
        print("")
        print("  [%s]" % sym)
        for (fr, t), cnt in sorted(hc[sym].items()):
            print("    %-22s -> %-22s: %3dx" % (fr, t, cnt))

    # --- Aurora core log ---
    kw = ["regime","UNCERTAIN","LOW_VOLATILITY","HIGH_VOLATILITY","MEAN_REVERSION",
          "TREND_UP","TREND_DOWN","FLAT_LOW","FLAT_NORMAL","FLAT_HIGH"]
    for logname in ["aurora_core.log", "event_chain.log"]:
        path = os.path.join(LOG_DIR, logname)
        hits = search_aux(path, kw)
        print("")
        print(SEP)
        print("  %s - Regime entries (max 50)" % logname.upper())
        print(SEP)
        if hits:
            print("  Found %d matching lines:" % len(hits))
            for l in hits: print("  " + l)
        else:
            print("  " + path)
            print("  (no matches or file not found)")

    # --- Log directory listing ---
    print("")
    print(SEP)
    print("  LOG DIRECTORY CONTENTS")
    print(SEP)
    try:
        for fname in sorted(os.listdir(LOG_DIR)):
            fp = os.path.join(LOG_DIR, fname)
            if os.path.isfile(fp):
                print("  %-50s %12d bytes" % (fname, os.path.getsize(fp)))
    except Exception as e:
        print("  Error: " + str(e))

    print("")
    print(SEP)
    print("  ANALYSIS COMPLETE")
    print(SEP)
    print("")


if __name__ == "__main__":
    main()

