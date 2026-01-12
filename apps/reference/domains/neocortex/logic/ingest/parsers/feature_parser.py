"""
Feature Log Parser

Parses feature log entries from logs/features/*.log

Format:
    TIMESTAMP - MODULE - LEVEL - Calculated features for SYMBOL: {JSON}
    
Example:
    2026-01-09 12:58:42,585 - ...FeatureEngineering - INFO - Calculated features for SOLUSDT: {"obi": "-0.68...", ...}
"""

import re
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FeatureLogEntry:
    """Parsed feature log entry."""
    timestamp: float
    timestamp_str: str
    symbol: str
    features: Dict[str, float]
    raw_line: str


# Pattern: YYYY-MM-DD HH:MM:SS,mmm - MODULE - LEVEL - Calculated features for SYMBOL: {JSON}
FEATURE_LOG_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})'  # Timestamp
    r' - .+? - INFO - '  # Module and level
    r'Calculated features for ([A-Z0-9]+): '  # Symbol
    r'(\{.+\})$'  # JSON payload
)


def parse_feature_log_line(line: str, symbol: str = None) -> Optional[FeatureLogEntry]:
    """
    Parse a single feature log line.
    
    Supports two formats:
    1. Pure JSON: {"obi": "0.5", "tfi": "0.9", ...}
    2. Full log: TIMESTAMP - MODULE - INFO - Calculated features for SYMBOL: {JSON}
    
    Args:
        line: Raw log line
        symbol: Symbol name (used for pure JSON format)
        
    Returns:
        FeatureLogEntry if successful, None otherwise
    """
    line = line.strip()
    if not line:
        return None
    
    # Try pure JSON format first (new format in logs/features/*.log)
    if line.startswith('{'):
        try:
            import time
            raw_features = json.loads(line)
            
            # Convert string values to floats
            features = {}
            for key, value in raw_features.items():
                try:
                    features[key] = float(value)
                except (ValueError, TypeError):
                    features[key] = 0.0
            
            return FeatureLogEntry(
                timestamp=time.time(),  # Use current time for pure JSON
                timestamp_str="",
                symbol=symbol or "UNKNOWN",
                features=features,
                raw_line=line
            )
        except json.JSONDecodeError:
            pass
    
    # Try full log format (TIMESTAMP - MODULE - INFO - ...)
    match = FEATURE_LOG_PATTERN.match(line)
    if match:
        timestamp_str = match.group(1)
        parsed_symbol = match.group(2)
        json_str = match.group(3)
        
        try:
            # Parse timestamp
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
            timestamp = dt.timestamp()
            
            # Parse JSON features
            raw_features = json.loads(json_str)
            
            # Convert string values to floats
            features = {}
            for key, value in raw_features.items():
                try:
                    features[key] = float(value)
                except (ValueError, TypeError):
                    features[key] = 0.0
                    
            return FeatureLogEntry(
                timestamp=timestamp,
                timestamp_str=timestamp_str,
                symbol=parsed_symbol,
                features=features,
                raw_line=line
            )
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"Failed to parse feature log: {e}")
            return None
    
    return None


def parse_feature_log_file(file_path: str) -> list:
    """
    Parse an entire feature log file.
    
    Args:
        file_path: Path to log file
        
    Returns:
        List of FeatureLogEntry objects
    """
    entries = []
    with open(file_path, 'r') as f:
        for line in f:
            entry = parse_feature_log_line(line)
            if entry:
                entries.append(entry)
    return entries
