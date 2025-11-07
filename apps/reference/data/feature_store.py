"""
Feature Store using DuckDB

Stores and retrieves historical features for alpha model training and backtesting.
Provides efficient time-series queries with configurable retention.
"""

import duckdb
import pandas as pd
import pyarrow as pa
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from threading import Lock
import json


@dataclass
class FeatureRecord:
    """Represents a single feature record."""

    timestamp: datetime
    symbol: str
    features: Dict[str, float]

    @classmethod
    def from_event_payload(cls, payload: Dict[str, Any]) -> 'FeatureRecord':
        """Create FeatureRecord from EVT:FEATURES_CALCULATED payload."""
        return cls(
            timestamp=pd.to_datetime(payload['ts'], unit='ms'),
            symbol=payload['symbol'],
            features={k: float(v) for k, v in payload['features'].items()}
        )


class FeatureStore:
    """
    DuckDB-based feature store for historical market features.

    Features:
    - Efficient time-series storage and retrieval
    - Configurable data retention (90-180 days)
    - Automatic cleanup of old data
    - Optimized queries for backtesting
    """

    def __init__(self, db_path: str = "data/features.db", retention_days: int = 90):
        """
        Initialize feature store.

        Args:
            db_path: Path to DuckDB database file
            retention_days: Number of days to retain data
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self.logger = logging.getLogger(
            f"{__name__}.{self.__class__.__name__}")
        self._lock = Lock()

        # Initialize database
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = duckdb.connect(str(self.db_path))
        try:
            # Create features table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS features (
                    timestamp TIMESTAMP NOT NULL,
                    symbol VARCHAR NOT NULL,
                    features JSON NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (timestamp, symbol)
                )
            """)

            # Create multi-timeframe aggregated features tables
            timeframes = ['5m', '15m', '1h', '4h']
            for tf in timeframes:
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS features_{tf} (
                        timestamp TIMESTAMP NOT NULL,
                        symbol VARCHAR NOT NULL,
                        features JSON NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (timestamp, symbol)
                    )
                """)

                conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_features_{tf}_timestamp
                    ON features_{tf} (timestamp)
                """)

                conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_features_{tf}_symbol_timestamp
                    ON features_{tf} (symbol, timestamp)
                """)

            # Create indexes for efficient queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_features_timestamp
                ON features (timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_features_symbol_timestamp
                ON features (symbol, timestamp)
            """)

            # Create metadata table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key VARCHAR PRIMARY KEY,
                    value VARCHAR
                )
            """)

            # Store retention policy
            conn.execute("""
                INSERT OR REPLACE INTO metadata (key, value)
                VALUES ('retention_days', ?)
            """, [str(self.retention_days)])
        finally:
            pass

        self.logger.info(f"Feature store initialized at {self.db_path}")

    def aggregate_timeframe(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> None:
        """
        Aggregate tick-level features into specified timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Target timeframe ('5m', '15m', '1h', '4h')
            start_time: Start time for aggregation (default: last aggregation time)
            end_time: End time for aggregation (default: now)
        """
        try:
            # Validate timeframe
            valid_timeframes = {'5m': '5 minutes', '15m': '15 minutes',
                                '1h': '1 hour', '4h': '4 hours'}
            if timeframe not in valid_timeframes:
                raise ValueError(
                    f"Invalid timeframe: {timeframe}. Must be one of {list(valid_timeframes.keys())}")

            end_time = end_time or datetime.now()
            start_time = start_time or (
                end_time - timedelta(days=1))  # Default to last 24h

            # Ensure times are timezone-naive for DuckDB
            if hasattr(end_time, 'tz'):
                end_time = end_time.replace(tzinfo=None)
            if hasattr(start_time, 'tz'):
                start_time = start_time.replace(tzinfo=None)

            interval = valid_timeframes[timeframe]

            # Compute a safety window to cover bucket alignment (avoid duplicates)
            bucket_map = {'5m': timedelta(minutes=5), '15m': timedelta(
                minutes=15), '1h': timedelta(hours=1), '4h': timedelta(hours=4)}
            bucket_delta = bucket_map.get(timeframe, timedelta(minutes=5))
            delete_start = (start_time - bucket_delta)
            delete_end = (end_time + bucket_delta)

            with self._lock, duckdb.connect(str(self.db_path)) as conn:
                # Clear existing aggregated data for this symbol and expanded time window
                conn.execute(f"""
                    DELETE FROM features_{timeframe}
                    WHERE symbol = ?
                      AND timestamp >= ?
                      AND timestamp <= ?
                """, [symbol, delete_start, delete_end])

                # Aggregate features using time_bucket
                query = f"""
                    INSERT INTO features_{timeframe}
                    SELECT
                        bucket_ts as timestamp,
                        symbol,
                        json_group_object(key, avg_value) as features,
                        CURRENT_TIMESTAMP as created_at
                    FROM (
                        SELECT
                            time_bucket('{interval}', timestamp) as bucket_ts,
                            symbol,
                            key,
                            avg(try_cast(value as DOUBLE)) as avg_value
                        FROM (
                            SELECT
                                timestamp,
                                symbol,
                                unnest(json_keys(features)) as key,
                                json_extract(features, '$."' || key || '"') as value
                            FROM features
                            WHERE symbol = ?
                              AND timestamp >= ?
                              AND timestamp <= ?
                        )
                        GROUP BY time_bucket('{interval}', timestamp), symbol, key
                    )
                    GROUP BY bucket_ts, symbol
                    ORDER BY bucket_ts
                """

                conn.execute(query, [symbol, start_time, end_time])

            self.logger.info(
                f"Aggregated {timeframe} features for {symbol} from {start_time} to {end_time}")

        except Exception as e:
            self.logger.error(
                f"Error aggregating {timeframe} features for {symbol}: {e}")
            raise

    def get_aggregated_features(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
        feature_names: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Retrieve aggregated features for a symbol and timeframe.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe ('5m', '15m', '1h', '4h')
            start_time: Start of time range
            end_time: End of time range
            feature_names: Specific features to retrieve (None for all)

        Returns:
            DataFrame with timestamp index and feature columns
        """
        try:
            # Validate timeframe
            valid_timeframes = ['5m', '15m', '1h', '4h']
            if timeframe not in valid_timeframes:
                raise ValueError(
                    f"Invalid timeframe: {timeframe}. Must be one of {valid_timeframes}")

            table_name = f"features_{timeframe}"

            with duckdb.connect(str(self.db_path)) as conn:
                query = f"""
                    SELECT timestamp, features
                    FROM {table_name}
                    WHERE symbol = ?
                      AND timestamp >= ?
                      AND timestamp <= ?
                    ORDER BY timestamp
                """

                rel = conn.execute(
                    query, [symbol, start_time, end_time])
                # Convert Arrow table to pandas DataFrame
                arrow_table = rel.df()
                df = arrow_table.to_pandas()

            if df.empty:
                self.logger.warning(
                    f"No aggregated {timeframe} features found for {symbol} between {start_time} and {end_time}")
                return pd.DataFrame()

            # Parse JSON features
            features_df = pd.json_normalize(df['features'].apply(json.loads))
            features_df['timestamp'] = df['timestamp']
            features_df.set_index('timestamp', inplace=True)

            # Filter specific features if requested
            if feature_names:
                available_features = [
                    col for col in features_df.columns if col in feature_names]
                if not available_features:
                    self.logger.warning(
                        f"None of requested features {feature_names} found")
                    return pd.DataFrame()
                features_df = features_df[available_features]

            # Convert string values to float
            for col in features_df.columns:
                features_df[col] = pd.to_numeric(
                    features_df[col], errors='coerce')

            self.logger.debug(
                f"Retrieved {len(features_df)} {timeframe} feature records for {symbol}")
            return features_df

        except Exception as e:
            self.logger.error(
                f"Error retrieving {timeframe} features for {symbol}: {e}")
            raise

    def aggregate_all_timeframes(
        self,
        symbol: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> None:
        """
        Aggregate tick-level features into all supported timeframes.

        Args:
            symbol: Trading symbol
            start_time: Start time for aggregation
            end_time: End time for aggregation
        """
        timeframes = ['5m', '15m', '1h', '4h']

        for tf in timeframes:
            try:
                self.aggregate_timeframe(symbol, tf, start_time, end_time)
                self.logger.info(f"Completed {tf} aggregation for {symbol}")
            except Exception as e:
                self.logger.error(
                    f"Failed to aggregate {tf} for {symbol}: {e}")
                continue

        self.logger.info(f"Completed all timeframe aggregations for {symbol}")

    def store_features(self, payload: Dict[str, Any]) -> None:
        """
        Store features from EVT:FEATURES_CALCULATED event.

        Args:
            payload: Event payload with ts, symbol, and features
        """
        try:
            record = FeatureRecord.from_event_payload(payload)

            with self._lock, duckdb.connect(str(self.db_path)) as conn:
                conn.execute("""
                    INSERT INTO features (timestamp, symbol, features)
                    VALUES (?, ?, ?)
                """, [
                    record.timestamp,
                    record.symbol,
                    json.dumps(record.features)
                ])

            self.logger.debug(
                f"Stored features for {record.symbol} at {record.timestamp}")

        except Exception as e:
            self.logger.error(f"Error storing features: {e}")
            raise

    def get_features(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        feature_names: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Retrieve features for a symbol within time range.

        Args:
            symbol: Trading symbol
            start_time: Start of time range
            end_time: End of time range
            feature_names: Specific features to retrieve (None for all)

        Returns:
            DataFrame with timestamp index and feature columns
        """
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                # Build query
                query = """
                    SELECT timestamp, features
                    FROM features
                    WHERE symbol = ?
                      AND timestamp >= ?
                      AND timestamp <= ?
                    ORDER BY timestamp
                """

                # Try multiple methods to retrieve data
                try:
                    rel = conn.execute(query, [symbol, start_time, end_time])
                    # Try arrow first
                    if hasattr(rel, 'arrow'):
                        arrow_table = rel.arrow()
                        df = arrow_table.to_pandas()
                    # Try df() method
                    elif hasattr(rel, 'df'):
                        df = rel.df()
                    # Try fetchdf() method
                    elif hasattr(rel, 'fetchdf'):
                        df = rel.fetchdf()
                    # Fallback: manually construct DataFrame
                    else:
                        # Get description and fetch all
                        if hasattr(rel, 'description'):
                            cols = [d[0] for d in rel.description]
                        else:
                            cols = None

                        if hasattr(rel, 'fetchall'):
                            rows = rel.fetchall()
                        else:
                            rows = []

                        if cols and rows:
                            df = pd.DataFrame(rows, columns=cols)
                        else:
                            df = pd.DataFrame()
                except Exception as e:
                    self.logger.debug(f"Failed to retrieve features: {e}")
                    df = pd.DataFrame()

            if df.empty:
                self.logger.warning(
                    f"No features found for {symbol} between {start_time} and {end_time}")
                return pd.DataFrame()

            # Parse JSON features
            features_df = pd.json_normalize(df['features'].apply(json.loads))
            features_df['timestamp'] = df['timestamp']
            features_df.set_index('timestamp', inplace=True)

            # Filter specific features if requested
            if feature_names:
                available_features = [
                    col for col in features_df.columns if col in feature_names]
                if not available_features:
                    self.logger.warning(
                        f"None of requested features {feature_names} found")
                    return pd.DataFrame()
                features_df = features_df[available_features]

            # Convert string values to float
            for col in features_df.columns:
                features_df[col] = pd.to_numeric(
                    features_df[col], errors='coerce')

            self.logger.debug(
                f"Retrieved {len(features_df)} feature records for {symbol}")
            return features_df

        except Exception as e:
            self.logger.error(f"Error retrieving features for {symbol}: {e}")
            raise

    def get_historical_data(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        include_ohlcv: bool = False
    ) -> pd.DataFrame:
        """
        Get historical data suitable for backtesting.

        Args:
            symbol: Trading symbol
            start_time: Start time
            end_time: End time
            include_ohlcv: Whether to include OHLCV data (placeholder for future)

        Returns:
            DataFrame with timestamp, symbol, and all features
        """
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                query = """
                    SELECT timestamp, symbol, features
                    FROM features
                    WHERE symbol = ?
                      AND timestamp >= ?
                      AND timestamp <= ?
                    ORDER BY timestamp
                """

                rel = conn.execute(
                    query, [symbol, start_time, end_time])
                # Convert Arrow table to pandas DataFrame
                arrow_table = rel.df()
                df = arrow_table.to_pandas()

            if df.empty:
                return pd.DataFrame()

            # Expand features
            features_df = pd.json_normalize(df['features'].apply(json.loads))
            result_df = pd.concat(
                [df[['timestamp', 'symbol']], features_df], axis=1)

            # Set timestamp as index
            result_df['timestamp'] = pd.to_datetime(result_df['timestamp'])
            result_df.set_index('timestamp', inplace=True)

            return result_df

        except Exception as e:
            self.logger.error(
                f"Error getting historical data for {symbol}: {e}")
            raise

    def cleanup_old_data(self) -> int:
        """
        Remove data older than retention period from all tables.

        Returns:
            Number of records deleted
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)

            with self._lock, duckdb.connect(str(self.db_path)) as conn:
                total_deleted = 0

                # Clean main features table
                result = conn.execute("""
                    DELETE FROM features
                    WHERE timestamp < ?
                """, [cutoff_date])
                row = result.fetchone()
                total_deleted += row[0] if row else 0

                # Clean aggregated tables
                timeframes = ['5m', '15m', '1h', '4h']
                for tf in timeframes:
                    result = conn.execute(f"""
                        DELETE FROM features_{tf}
                        WHERE timestamp < ?
                    """, [cutoff_date])
                    row = result.fetchone()
                    deleted = row[0] if row else 0
                    total_deleted += deleted
                    if deleted > 0:
                        self.logger.debug(
                            f"Cleaned {deleted} records from features_{tf}")

            if total_deleted > 0:
                self.logger.info(
                    f"Cleaned up {total_deleted} old feature records from all tables")

            return total_deleted

        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics for all tables.

        Returns:
            Dictionary with stats about stored data
        """
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                stats = {}

                # Main features table
                result = conn.execute(
                    "SELECT COUNT(*) FROM features")
                row = result.fetchone()
                total_records = row[0] if row else 0
                stats['features'] = {'total_records': total_records}

                # Aggregated tables
                timeframes = ['5m', '15m', '1h', '4h']
                for tf in timeframes:
                    result = conn.execute(
                        f"SELECT COUNT(*) FROM features_{tf}")
                    row = result.fetchone()
                    count = row[0] if row else 0
                    stats[tf] = {'total_records': count}

                # Records per symbol (from main table)
                rel = conn.execute("""
                    SELECT symbol, COUNT(*) as count,
                           MIN(timestamp) as earliest,
                           MAX(timestamp) as latest
                    FROM features
                    GROUP BY symbol
                    ORDER BY count DESC
                """)
                # Convert Arrow table to pandas DataFrame
                arrow_table = rel.df()
                symbol_stats = arrow_table.to_pandas()

                # Date range
                date_range_row = conn.execute("""
                    SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest
                    FROM features
                """).fetchone()

                # Retention info
                retention_row = conn.execute("""
                    SELECT value FROM metadata WHERE key = 'retention_days'
                """).fetchone()

                stats['summary'] = {
                    'symbols': symbol_stats.to_dict('records') if not symbol_stats.empty else [],
                    'date_range': {
                        'earliest': date_range_row[0].isoformat() if date_range_row and date_range_row[0] else None,
                        'latest': date_range_row[1].isoformat() if date_range_row and date_range_row[1] else None
                    },
                    'retention_days': int(retention_row[0]) if retention_row else self.retention_days,
                    'db_size_mb': self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
                }

            return stats

        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {}

    def optimize(self) -> None:
        """Optimize database performance."""
        try:
            with duckdb.connect(str(self.db_path)) as conn:
                conn.execute("VACUUM")
                conn.execute("ANALYZE features")

            self.logger.info("Database optimized")

        except Exception as e:
            self.logger.error(f"Error optimizing database: {e}")
            raise
