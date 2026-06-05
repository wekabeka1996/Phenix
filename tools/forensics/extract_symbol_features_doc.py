"""Extract one symbol's feature-engineering rows into a compact document.

The output keeps only:
- time
- coin
- closed_bar
- features

It strips module paths and log levels from domain_feature_engineering.log.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = BASE / "logs" / "domain_feature_engineering.log"
DEFAULT_OUTPUT = BASE / "reports" / "btc_features_extract.md"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S,%f"


FEATURE_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
    r"\s+-\s+.+?\s+-\s+INFO\s+-\s+"
    r"Calculated features for (?P<symbol>[A-Z0-9_]+):\s+(?P<payload>\{.*\})\s*$"
)

BAR_CLOSED_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"
    r"\s+-\s+.+?\s+-\s+INFO\s+-\s+.*on_bar_closed: emitting bar-features for "
    r"(?P<symbol>[A-Z0-9_]+) tf_sec=(?P<tf_sec>\d+)\s*$"
)


@dataclass(frozen=True)
class BarClosedEvent:
    timestamp: datetime
    tf_sec: int


@dataclass(frozen=True)
class OutputRow:
    time_text: str
    coin: str
    closed_bar: str
    features: str


def _parse_timestamp(raw_value: str) -> datetime:
    return datetime.strptime(raw_value, TIMESTAMP_FORMAT)


def _format_time(timestamp: datetime, *, full_timestamp: bool) -> str:
    if full_timestamp:
        return timestamp.strftime(TIMESTAMP_FORMAT)[:-3]
    return timestamp.strftime("%H:%M:%S,%f")[:-3]


def _normalize_features(raw_payload: str) -> str:
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return raw_payload.strip()

    return json.dumps(parsed, ensure_ascii=True, separators=(", ", ": "))


def _escape_markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def extract_rows(
    input_path: Path,
    *,
    symbol: str,
    bar_close_window_ms: int,
    full_timestamp: bool,
) -> list[OutputRow]:
    rows: list[OutputRow] = []
    last_bar_closed_by_symbol: dict[str, BarClosedEvent] = {}

    with input_path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")

            bar_match = BAR_CLOSED_RE.match(line)
            if bar_match:
                bar_symbol = bar_match.group("symbol")
                last_bar_closed_by_symbol[bar_symbol] = BarClosedEvent(
                    timestamp=_parse_timestamp(bar_match.group("ts")),
                    tf_sec=int(bar_match.group("tf_sec")),
                )
                continue

            feature_match = FEATURE_LINE_RE.match(line)
            if not feature_match:
                continue

            row_symbol = feature_match.group("symbol")
            if row_symbol != symbol:
                continue

            feature_timestamp = _parse_timestamp(feature_match.group("ts"))
            closed_bar_value = "no"
            last_bar_closed = last_bar_closed_by_symbol.get(row_symbol)
            if last_bar_closed is not None:
                delta_ms = int(
                    (feature_timestamp - last_bar_closed.timestamp).total_seconds() * 1000
                )
                if 0 <= delta_ms <= bar_close_window_ms:
                    closed_bar_value = f"tf={last_bar_closed.tf_sec}"

            rows.append(
                OutputRow(
                    time_text=_format_time(
                        feature_timestamp,
                        full_timestamp=full_timestamp,
                    ),
                    coin=row_symbol,
                    closed_bar=closed_bar_value,
                    features=_normalize_features(feature_match.group("payload")),
                )
            )

    return rows


def render_markdown(rows: list[OutputRow]) -> str:
    lines = [
        "| time | coin | features | closed_bar |",
        "| --- | --- | --- | --- |",
    ]

    for row in rows:
        lines.append(
            "| "
            f"{_escape_markdown_cell(row.time_text)} | "
            f"{_escape_markdown_cell(row.coin)} | "
            f"{_escape_markdown_cell(row.features)} | "
            f"{_escape_markdown_cell(row.closed_bar)} |"
        )

    return "\n".join(lines) + "\n"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract one symbol's feature-engineering rows from "
            "domain_feature_engineering.log into a compact markdown document."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Source log file. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output markdown file. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        help="Symbol to extract. Default: BTCUSDT",
    )
    parser.add_argument(
        "--bar-close-window-ms",
        type=int,
        default=2000,
        help=(
            "Max delay between on_bar_closed and the matching feature row. "
            "Default: 2000"
        ),
    )
    parser.add_argument(
        "--full-timestamp",
        action="store_true",
        help="Keep full YYYY-MM-DD HH:MM:SS,mmm instead of time only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    input_path = args.input.expanduser()
    output_path = args.output.expanduser()

    if not input_path.exists():
        parser.error(f"Input log file does not exist: {input_path}")

    rows = extract_rows(
        input_path,
        symbol=args.symbol.upper(),
        bar_close_window_ms=args.bar_close_window_ms,
        full_timestamp=args.full_timestamp,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(rows), encoding="utf-8")

    print(
        f"Wrote {len(rows)} rows for {args.symbol.upper()} to {output_path}",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())