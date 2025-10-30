"""
Snapshot Scheduler Domain

Periodically triggers snapshot creation for critical FSM domains (starting with position_tracking).
Saves snapshots to local storage as part of the Disaster Recovery protocol (Phase L4).
"""

import json
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict


logger = logging.getLogger(__name__)


class SnapshotScheduler:
    """
    FSM domain responsible for periodic snapshot creation and storage.

    Triggers snapshot generation every N seconds (default: 300s = 5 minutes)
    and saves results to the local snapshot directory (ops/snapshots/).

    Part of Phase L4 Disaster Recovery protocol.
    """

    def __init__(self, fsm: Any, config: Dict[str, Any]) -> None:
        """
        Initialize the snapshot scheduler.

        Args:
            fsm: FSM core instance with domain registry
            config: Configuration dictionary with:
                - interval_sec: Snapshot interval in seconds (default: 300)
                - snapshot_dir: Directory for snapshot storage (default: "ops/snapshots")
                - domains: List of domain names to snapshot (default: ["position_tracking"])
        """
        self.fsm = fsm
        self.config = config
        self.interval_sec = config.get("interval_sec", 300)  # 5 minutes default
        self.snapshot_dir = Path(config.get("snapshot_dir", "ops/snapshots"))
        self.target_domains = config.get("domains", ["position_tracking"])
        self._thread: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()

        # Create snapshot directory if it doesn't exist
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Track snapshot statistics
        self._snapshot_count = 0
        self._last_snapshot_time: datetime | None = None
        self._failed_snapshots = 0

        logger.info(
            f"SnapshotScheduler initialized. "
            f"Interval: {self.interval_sec}s, "
            f"Target domains: {self.target_domains}, "
            f"Storage: {self.snapshot_dir}"
        )

    def start(self) -> None:
        """Start the periodic snapshot task."""
        if self._thread is None and not self._running:
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self._thread.start()
            logger.info(f"SnapshotScheduler started. Interval: {self.interval_sec}s")

    def stop(self) -> None:
        """Stop the periodic snapshot task."""
        if self._thread and self._running:
            self._running = False
            self._stop_event.set()
            self._thread.join(timeout=5.0)
            self._thread = None
            logger.info(
                f"SnapshotScheduler stopped. "
                f"Total snapshots: {self._snapshot_count}, "
                f"Failed: {self._failed_snapshots}"
            )

    def _run_scheduler(self) -> None:
        """
        Main scheduler loop that triggers snapshots periodically.

        Runs until stopped or cancelled. Handles exceptions gracefully
        to ensure the scheduler continues even if individual snapshots fail.
        """
        logger.info("Snapshot scheduler loop starting...")

        try:
            while self._running:
                # Wait for interval or stop signal
                if self._stop_event.wait(timeout=self.interval_sec):
                    break  # Stop signal received

                if not self._running:
                    break

                logger.info("⏰ Triggering scheduled snapshot cycle...")
                self._create_snapshots()

        except Exception as e:
            logger.error(
                f"Unexpected error in snapshot scheduler loop: {e}", exc_info=True
            )

    def _create_snapshots(self) -> None:
        """
        Create snapshots for all target domains.

        Iterates through configured domains and attempts to create
        a snapshot for each. Failures are logged but don't stop the process.
        """
        for domain_name in self.target_domains:
            try:
                self._snapshot_domain(domain_name)
            except Exception as e:
                self._failed_snapshots += 1
                logger.error(
                    f"Failed to create snapshot for domain '{domain_name}': {e}",
                    exc_info=True,
                )

    def _snapshot_domain(self, domain_name: str) -> None:
        """
        Create snapshot for a specific domain.

        Args:
            domain_name: Name of the domain to snapshot (e.g., "position_tracking")

        Raises:
            Exception: If snapshot creation or saving fails
        """
        logger.debug(f"Creating snapshot for domain: {domain_name}")

        # Access domain from FSM core's domain registry
        # Note: In the current architecture, domains are stored as module-level variables
        # We need to access them through a registry pattern
        domain_instance = self._get_domain_instance(domain_name)

        if domain_instance is None:
            logger.warning(f"Domain '{domain_name}' not found in registry. Skipping.")
            return

        # Check if domain has get_snapshot method
        if not hasattr(domain_instance, "get_snapshot"):
            logger.warning(
                f"Domain '{domain_name}' does not implement get_snapshot(). Skipping."
            )
            return

        # Create snapshot
        snapshot_data = domain_instance.get_snapshot()

        # Save to file
        self._save_snapshot(domain_name, snapshot_data)

        # Update statistics
        self._snapshot_count += 1
        self._last_snapshot_time = datetime.now(timezone.utc)

        logger.info(
            f"✅ Successfully created snapshot #{self._snapshot_count} for '{domain_name}'"
        )

    def _get_domain_instance(self, domain_name: str) -> Any:
        """
        Retrieve domain instance from FSM registry.

        Args:
            domain_name: Name of the domain to retrieve

        Returns:
            Domain instance or None if not found
        """
        # Check if FSM has a domain registry
        if hasattr(self.fsm, "domains") and isinstance(self.fsm.domains, dict):
            return self.fsm.domains.get(domain_name)

        # Fallback: try to access as attribute
        if hasattr(self.fsm, domain_name):
            return getattr(self.fsm, domain_name)

        return None

    def _save_snapshot(self, domain_name: str, snapshot_data: Dict[str, Any]) -> None:
        """
        Save snapshot data to a JSON file.

        Args:
            domain_name: Name of the domain being snapshotted
            snapshot_data: Snapshot data dictionary (must be JSON-serializable)

        Raises:
            IOError: If file write fails
        """
        # Generate filename with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{domain_name}_{timestamp}.json"
        filepath = self.snapshot_dir / filename

        logger.debug(f"Saving snapshot to: {filepath}")

        try:
            # Write to file
            self._write_snapshot_file(filepath, snapshot_data)

            logger.info(
                f"💾 Snapshot saved: {filepath} ({filepath.stat().st_size} bytes)"
            )

        except IOError as e:
            logger.error(f"Failed to write snapshot to {filepath}: {e}")
            raise

    def _write_snapshot_file(
        self, filepath: Path, snapshot_data: Dict[str, Any]
    ) -> None:
        """
        Synchronous file write helper.

        Args:
            filepath: Path to snapshot file
            snapshot_data: Data to write
        """
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(snapshot_data, f, indent=2, ensure_ascii=False)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get snapshot scheduler statistics.

        Returns:
            Dictionary with scheduler stats
        """
        return {
            "running": self._running,
            "interval_sec": self.interval_sec,
            "snapshot_count": self._snapshot_count,
            "failed_snapshots": self._failed_snapshots,
            "last_snapshot_time": self._last_snapshot_time.isoformat()
            if self._last_snapshot_time
            else None,
            "target_domains": self.target_domains,
            "snapshot_dir": str(self.snapshot_dir),
        }
