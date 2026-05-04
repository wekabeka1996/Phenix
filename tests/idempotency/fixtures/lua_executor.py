"""
Embedded Lua script executor for testing Redis idempotency with atomic guarantees.

Emulates Lua script execution using Python with threading.Lock for atomicity.
This solves the problem where fakeredis doesn't support EVAL/EVALSHA commands.
"""

import json
import threading
from typing import Any, Dict, List


class LuaExecutor:
    """
    Emulate Redis Lua script execution with atomic guarantees.

    Uses threading.Lock to ensure atomicity (equivalent to Lua's single-threaded execution).
    """

    def __init__(self, client: Any) -> None:
        """Initialize with fake Redis client."""
        self.client = client
        self._lock = threading.Lock()
        self._scripts: Dict[str, str] = {}  # SHA → script name

    def register_script(self, sha: str, name: str) -> None:
        """Register Lua script SHA to name mapping."""
        self._scripts[sha] = name

    def evalsha(self, sha: str, numkeys: int, *keys_and_args: str) -> List[str]:
        """
        Execute Lua script by SHA with atomic guarantees.

        Args:
            sha: Script identifier (maps to RESERVE/CONFIRM/RELEASE)
            numkeys: Number of KEYS[] arguments
            keys_and_args: KEYS[1..numkeys] followed by ARGV[1..]

        Returns:
            [status, detail] matching real Lua script format
        """
        script_name = self._scripts.get(sha, "unknown")

        if script_name == "reserve":
            return self._execute_reserve(numkeys, *keys_and_args)
        elif script_name == "confirm":
            return self._execute_confirm(numkeys, *keys_and_args)
        elif script_name == "release":
            return self._execute_release(numkeys, *keys_and_args)
        else:
            raise ValueError(f"Unknown script SHA: {sha}")

    def _execute_reserve(self, numkeys: int, *args: str) -> List[str]:
        """
        Execute RESERVE script atomically.

        Lua-style convention:
        - KEYS[1] = args[0]
        - ARGV[1] = args[numkeys + 0]
        - ARGV[2] = args[numkeys + 1]
        - etc.

        For RESERVE:
        - KEYS[1] = redis_key
        - ARGV[1] = owner
        - ARGV[2] = payload_digest
        - ARGV[3] = ttl_ms (string)
        - ARGV[4] = ts_ns (string)

        Returns: [status, detail]
        """
        with self._lock:  # Atomic block
            key = args[0]  # KEYS[1]
            owner = args[numkeys]  # ARGV[1] (after numkeys KEYs)
            payload_digest = args[numkeys + 1]  # ARGV[2]
            ttl_ms = int(args[numkeys + 2])  # ARGV[3]
            ts_ns = args[numkeys + 3]  # ARGV[4]

            exists = self.client.exists(key)

            if not exists:
                # NEW: create record
                record = {
                    "owner": owner,
                    "payload_digest": payload_digest,
                    "status": "HELD",
                    "ts_ns": ts_ns,
                    "lease_ms": ttl_ms,
                }
                self.client.set(key, json.dumps(record))
                self.client.pexpire(key, ttl_ms)
                return ["NEW", str(ttl_ms)]

            # Record exists - check for conflicts
            raw = self.client.get(key)
            if not raw:
                # Race: key deleted between EXISTS and GET
                return self._execute_reserve(numkeys, *args)

            record = json.loads(raw)

            if record.get("owner") != owner:
                # EXTERN_OWNER
                return ["EXTERN_OWNER", record.get("owner", "unknown")]

            if record.get("payload_digest") == payload_digest:
                # DUPLICATE_SAME (idempotent no-op)
                return ["DUPLICATE_SAME", str(record.get("lease_ms", ttl_ms))]

            # DUPLICATE_CONFLICT (different payload)
            return ["DUPLICATE_CONFLICT", record.get("payload_digest", "unknown")]

    def _execute_confirm(self, numkeys: int, *args: str) -> List[str]:
        """
        Execute CONFIRM script atomically.

        For CONFIRM:
        - KEYS[1] = redis_key
        - ARGV[1] = final_status
        - ARGV[2] = meta_json
        - ARGV[3] = ts_ns

        Returns: ["OK"] or ["MISSING"]
        """
        with self._lock:  # Atomic block
            key = args[0]  # KEYS[1]
            final_status = args[numkeys]  # ARGV[1]
            meta_json = args[numkeys + 1]  # ARGV[2]
            ts_ns = args[numkeys + 2]  # ARGV[3]

            exists = self.client.exists(key)
            if not exists:
                return ["MISSING"]

            # Update record
            raw = self.client.get(key)
            if not raw:
                return ["MISSING"]

            record = json.loads(raw)
            record["status"] = "CONFIRMED"
            record["final_status"] = final_status
            if meta_json and meta_json != "":
                record["meta"] = json.loads(meta_json)
            record["confirm_ts_ns"] = ts_ns

            self.client.set(key, json.dumps(record))
            return ["CONFIRMED"]

    def _execute_release(self, numkeys: int, *args: str) -> List[str]:
        """
        Execute RELEASE script atomically.

        For RELEASE:
        - KEYS[1] = redis_key
        - ARGV[1] = owner

        Returns: ["RELEASED"] or ["MISSING"] or ["ERROR", "owner mismatch"]
        """
        with self._lock:  # Atomic block
            key = args[0]  # KEYS[1]
            owner = args[numkeys]  # ARGV[1]

            exists = self.client.exists(key)
            if not exists:
                return ["MISSING"]

            # Check owner
            raw = self.client.get(key)
            if not raw:
                return ["MISSING"]

            record = json.loads(raw)
            if record.get("owner") != owner:
                return ["ERROR", "owner mismatch"]

            # Delete key
            self.client.delete(key)
            return ["RELEASED"]
