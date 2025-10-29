"""Type protocols for Redis client."""

from typing import Any, Optional, Protocol, TypedDict


class RecordTD(TypedDict, total=False):
    """TypedDict for idempotency record structure."""
    owner: str
    payload_digest: str
    status: str
    ts_ns: str
    lease_ms: int
    result: Optional[str]


class RedisClientProtocol(Protocol):
    """Protocol for Redis client (sync operations)."""
    
    def ping(self) -> Any:
        """Ping Redis server."""
        ...
    
    def script_load(self, script: str) -> str:
        """Load Lua script, return SHA."""
        ...
    
    def evalsha(self, sha: str, numkeys: int, *keys_and_args: Any) -> Any:
        """Execute Lua script by SHA."""
        ...
    
    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> Any:
        """Execute Lua script directly."""
        ...
    
    def set(self, key: str, value: Any, px: Optional[int] = None) -> Any:
        """Set key-value with optional expiry."""
        ...
    
    def get(self, key: str) -> Any:
        """Get value by key."""
        ...
    
    def exists(self, *keys: str) -> int:
        """Check if keys exist."""
        ...
    
    def delete(self, *keys: str) -> int:
        """Delete keys."""
        ...
    
    def pexpire(self, key: str, milliseconds: int) -> Any:
        """Set key expiration in milliseconds."""
        ...

