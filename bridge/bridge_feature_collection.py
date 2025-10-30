# feature_bridge_live.py
# Drop-in: LIVE features → obi, tfi (via aggTrade), delta_price (via mid-price), price
# Requirements: pip install python-dotenv websockets ujson unicorn-binance-websocket-api

import asyncio, json, os, time, decimal, collections
from typing import Dict, Optional
from dotenv import load_dotenv
from unicorn_binance_websocket_api import BinanceWebSocketApiManager

# ---------- Config ----------
LIVE_EXCHANGE = "binance.com"
BOOK_BUFFER = "book_buffer"
TRADE_BUFFER = "trade_buffer"
DP_MS_MAX_GAP = int(os.getenv("DP_MS_MAX_GAP", "2000"))  # max gap for delta_price, ms
TFI_WINDOW_SEC = float(os.getenv("TFI_WINDOW_SEC", "3.0"))  # rolling window for tfi


# ---------- Helper ----------
def now_ms() -> int:
    return int(time.time() * 1000)


def jwrite(path: str, obj: dict):
    print(f"Writing to {path}: {obj}")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------- Collector ----------
class LiveBridgeCollector:
    def __init__(self, symbols: list[str], out_dir: str = "logs"):
        load_dotenv()
        self.symbols = [s.upper() for s in symbols]
        self.last_tick: Dict[str, dict] = {}
        self.features_path = os.path.join(out_dir, "features.jsonl")
        os.makedirs(out_dir, exist_ok=True)

        # order-flow window for TFI: per symbol deque of (ts, signed_qty)
        self.flow = {s: collections.deque() for s in self.symbols}

        self.bwam = BinanceWebSocketApiManager(exchange=LIVE_EXCHANGE)

        # bookTicker: щоб мати B/A qty та ціни
        self.bwam.create_stream(
            channels=["bookTicker"],
            markets=[s.lower() for s in self.symbols],
            stream_label="BOOK",
            stream_buffer_name=BOOK_BUFFER,
        )
        # aggTrade: щоб адекватно оцінювати TFI (buyer-taker vs seller-taker)
        self.bwam.create_stream(
            channels=["aggTrade"],
            markets=[s.lower() for s in self.symbols],
            stream_label="TRADES",
            stream_buffer_name=TRADE_BUFFER,
        )

    def _tfi_from_window(self, symbol: str, now_ts: int) -> float:
        dq = self.flow[symbol]
        # drop old
        cutoff = now_ts - int(TFI_WINDOW_SEC * 1000)
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        pos = sum(q for _, q in dq if q > 0)
        neg = -sum(q for _, q in dq if q < 0)
        tot = pos + neg
        if tot <= 0:
            return 0.0
        return (pos - neg) / tot

    def _handle_book(self, data: dict):
        s = (data.get("s") or "").upper()
        if s not in self.symbols:
            return
        # bookTicker fields: b/B = best bid price/qty, a/A = best ask price/qty, E = event time
        b = float(data.get("b", 0.0))
        a = float(data.get("a", 0.0))
        Bq = float(data.get("B", 0.0))
        Aq = float(data.get("A", 0.0))
        ts = int(data.get("E", now_ms()))
        mid = (b + a) / 2.0 if b and a else (b or a or 0.0)

        prev = self.last_tick.get(s)
        self.last_tick[s] = {"mid": mid, "ts": ts, "Bq": Bq, "Aq": Aq}

        if prev is None:
            return

        # features
        depth = Bq + Aq
        obi = (Bq - Aq) / depth if depth > 0 else 0.0

        # delta_price vs mid
        dt = ts - prev["ts"]
        dp = (mid - prev["mid"]) if dt < DP_MS_MAX_GAP else 0.0

        tfi = self._tfi_from_window(s, ts)  # from aggTrade window

        rec = {
            "timestamp": time.time(),
            "symbol": s,
            "obi": float(obi),
            "tfi": float(tfi),
            "delta_price": float(dp),
            "price": float(mid),
        }
        jwrite(self.features_path, rec)

    def _handle_trade(self, data: dict):
        s = (data.get("s") or "").upper()
        if s not in self.symbols:
            return
        qty = float(data.get("q", 0.0))
        ts = int(data.get("E", now_ms()))
        # 'm' == True → buyer is maker → sell is taker → негативний знак
        sign = -1.0 if data.get("m", False) else +1.0
        self.flow[s].append((ts, sign * qty))

    def run(self, seconds: int = 30):
        print(f"Starting collection for {seconds} seconds...")
        end = time.time() + seconds
        while time.time() < end:
            # TRADES
            tmsg = self.bwam.pop_stream_data_from_stream_buffer(TRADE_BUFFER)
            if tmsg:
                if isinstance(tmsg, str):
                    tmsg = json.loads(tmsg)
                if (
                    isinstance(tmsg, dict)
                    and "data" in tmsg
                    and tmsg.get("stream", "").endswith("@aggTrade")
                ):
                    self._handle_trade(tmsg["data"])

            # BOOK
            bmsg = self.bwam.pop_stream_data_from_stream_buffer(BOOK_BUFFER)
            if bmsg:
                if isinstance(bmsg, str):
                    bmsg = json.loads(bmsg)
                if (
                    isinstance(bmsg, dict)
                    and "data" in bmsg
                    and bmsg.get("stream", "").endswith("@bookTicker")
                ):
                    self._handle_book(bmsg["data"])

            time.sleep(0.05)

        self.bwam.stop_manager_with_all_streams()
        print(f"Collection completed. Features saved to {self.features_path}")


def main():
    syms = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
    LiveBridgeCollector([s.strip() for s in syms if s.strip()]).run(seconds=5)


if __name__ == "__main__":
    main()
