import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Event:
    pld: dict
    why: str = ""


class MiniFSM:
    def __init__(self) -> None:
        self._listeners: dict[str, list] = {}
        self.emitted: list[tuple[str, dict, str]] = []

    def listen(self, event_name: str, handler):
        self._listeners.setdefault(event_name, []).append(handler)

    def emit(self, event_name: str, payload: dict, why: str | None = None, data_ref=None):
        self.emitted.append((event_name, payload, why or ""))
        evt = Event(pld=payload, why=why or "")
        for handler in list(self._listeners.get(event_name, [])):
            handler(evt)


def test_mr_receives_forwarded_tick_and_logs_bar(tmp_path: Path, capsys):
    # Ensure env vars used by YAML interpolation exist (dummy values for tests)
    os.environ.setdefault("BINANCE_FUTURES_API_KEY_LIVE", "dummy")
    os.environ.setdefault("BINANCE_FUTURES_API_SECRET_LIVE", "dummy")
    os.environ.setdefault("BINANCE_FUTURES_BASE_URL_LIVE", "https://example.com")
    os.environ.setdefault("BINANCE_TESTNET_API_KEY", "dummy")
    os.environ.setdefault("BINANCE_TESTNET_API_SECRET", "dummy")

    from apps.reference.config_loader import ConfigLoader
    from apps.reference.domains.decision_making.mean_reversion_handler import MeanReversionHandler

    fsm = MiniFSM()
    cfg = ConfigLoader().load_config()

    mr = MeanReversionHandler(fsm=fsm, config=cfg)
    assert mr.is_symbol_enabled("DOGEUSDT")

    # Redirect bar logger outputs into tmp_path (avoid writing into repo logs/)
    assert mr.bar_logger is not None
    mr.bar_logger.log_dir = str(tmp_path)
    mr.bar_logger.tsv_path = str(tmp_path / f"bars_{mr.timeframe_sec}s.tsv")
    mr.bar_logger.jsonl_path = str(tmp_path / f"bars_{mr.timeframe_sec}s.jsonl")
    mr.bar_logger._init_tsv_header()

    mr.register()

    base_ts = 1_700_000_000_000
    ticks = [
        base_ts,
        base_ts + 60_000,
        base_ts + 120_000,
        base_ts + 180_001,  # cross 180s boundary
    ]

    for ts in ticks:
        fsm.emit(
            "EVT:MARKET_TICK_FORWARDED",
            payload={
                "symbol": "DOGEUSDT",
                "ts": ts,
                "price": "0.1000",
                "buy_volume": "0",
                "sell_volume": "0",
                "bid_size": "1",
                "ask_size": "1",
            },
            why="test_tick_forwarded",
        )

    # Prove MR tick-path progressed.
    # Equivalent evidence (DoD): MR prints a tap JSON line with `source=bar_closed` when a bar is completed.
    out = capsys.readouterr().out
    assert '"source": "bar_closed"' in out
    assert '"symbol": "DOGEUSDT"' in out
    assert '"tf_sec": 180' in out

    # Optional: TSV exists (header-only is acceptable for this smoke test).
    tsv_path = Path(mr.bar_logger.tsv_path)
    assert tsv_path.exists()
