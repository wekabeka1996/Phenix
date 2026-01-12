"""
Neocortex Log Parsers

Parsers for different Aurora log formats:
- feature_parser: Feature logs from FeatureEngineering domain
- order_parser: Order lifecycle events (JSONL)
- core_parser: Core system events (text log)
"""

from .feature_parser import (
    FeatureLogEntry,
    parse_feature_log_line,
    parse_feature_log_file,
)

from .order_parser import (
    OrderLogEntry,
    OrderEventType,
    parse_order_log_line,
    parse_order_log_file,
)

from .core_parser import (
    CoreLogEntry,
    CoreEventType,
    parse_core_log_line,
    parse_core_log_file,
    extract_position_closes,
)

__all__ = [
    # Feature parser
    "FeatureLogEntry",
    "parse_feature_log_line",
    "parse_feature_log_file",
    # Order parser
    "OrderLogEntry",
    "OrderEventType",
    "parse_order_log_line",
    "parse_order_log_file",
    # Core parser
    "CoreLogEntry",
    "CoreEventType",
    "parse_core_log_line",
    "parse_core_log_file",
    "extract_position_closes",
]
