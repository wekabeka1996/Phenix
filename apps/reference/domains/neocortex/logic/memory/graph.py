"""
Causal Transition Graph (Hippocampus)

Phase R1.5: "The Dreamer" - Offline Consolidation

Stores learned state transitions as a directed graph in SQLite.
Each node represents a cluster of latent states (z centroids).
Each edge represents observed transitions with associated actions and rewards.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    CausalGraph                              │
    │                                                             │
    │   ┌─────────┐       ┌─────────┐       ┌─────────┐          │
    │   │ Node A  │──a=0──│ Node B  │──a=1──│ Node C  │          │
    │   │ z_cent  │  r=+5 │ z_cent  │  r=-2 │ z_cent  │          │
    │   │ v=10    │       │ v=5     │       │ v=3     │          │
    │   └─────────┘       └─────────┘       └─────────┘          │
    │                                                             │
    │   SQLite: hippocampus.db                                   │
    │   - nodes: id, z_centroid (blob), visit_count, avg_value   │
    │   - edges: source_id, target_id, action, reward_mean, ...  │
    └─────────────────────────────────────────────────────────────┘

Use Cases:
1. Experience Consolidation: Raw episodes → Graph structure
2. Curiosity Bonus: Visit count determines exploration bonus
3. Planning: Graph traversal for look-ahead decisions
"""

import sqlite3
import logging
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the causal graph."""
    id: int
    z_centroid: np.ndarray
    visit_count: int = 1
    avg_value: float = 0.0
    created_at: float = 0.0


@dataclass
class GraphEdge:
    """A directed edge in the causal graph."""
    source_id: int
    target_id: int
    action: int  # 0=LONG, 1=SHORT, 2=FLAT
    reward_mean: float = 0.0
    reward_var: float = 0.0
    count: int = 1


class CausalGraph:
    """
    SQLite-backed causal transition graph.
    
    Stores state-action-reward-state' transitions for:
    - Long-term memory consolidation
    - Exploration (curiosity via visit counts)
    - Planning (graph traversal)
    
    Thread-safe for single-writer, multi-reader scenarios.
    """
    
    # Distance threshold for "same node" clustering
    DEFAULT_CLUSTER_RADIUS = 0.5
    
    def __init__(
        self,
        db_path: Path,
        latent_dim: int,
        cluster_radius: float = DEFAULT_CLUSTER_RADIUS
    ):
        """
        Initialize the causal graph.
        
        Args:
            db_path: Path to SQLite database file
            latent_dim: Dimension of latent vectors (z)
            cluster_radius: Euclidean distance threshold for node clustering
        """
        self.db_path = Path(db_path)
        self.latent_dim = latent_dim
        self.cluster_radius = cluster_radius
        
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
        
        # Cache for node centroids (loaded on demand)
        self._node_cache: Dict[int, np.ndarray] = {}
        self._cache_valid = False
        
        logger.info(f"CausalGraph initialized: {db_path} (dim={latent_dim})")
    
    def _init_db(self):
        """Create tables if they don't exist."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    z_centroid BLOB NOT NULL,
                    visit_count INTEGER DEFAULT 1,
                    avg_value REAL DEFAULT 0.0,
                    created_at REAL DEFAULT 0.0
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    source_id INTEGER NOT NULL,
                    target_id INTEGER NOT NULL,
                    action INTEGER NOT NULL,
                    reward_mean REAL DEFAULT 0.0,
                    reward_var REAL DEFAULT 0.0,
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (source_id, target_id, action),
                    FOREIGN KEY (source_id) REFERENCES nodes(id),
                    FOREIGN KEY (target_id) REFERENCES nodes(id)
                )
            """)
            
            # Index for faster lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_edges_source 
                ON edges(source_id)
            """)
            
            conn.commit()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _load_node_cache(self):
        """Load all node centroids into memory for fast nearest-neighbor."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT id, z_centroid FROM nodes")
            self._node_cache.clear()
            
            for row in cursor:
                z = np.frombuffer(row["z_centroid"], dtype=np.float32)
                self._node_cache[row["id"]] = z
            
            self._cache_valid = True
            logger.debug(f"Loaded {len(self._node_cache)} nodes into cache")
    
    def get_closest_node(self, z: np.ndarray) -> Tuple[Optional[int], float]:
        """
        Find the closest existing node to the given latent vector.
        
        Uses simple Euclidean distance. For large graphs (>10k nodes),
        consider upgrading to FAISS or Annoy.
        
        Args:
            z: Latent vector (1D numpy array)
            
        Returns:
            Tuple of (node_id, distance). If no nodes exist, returns (None, inf).
        """
        if not self._cache_valid:
            self._load_node_cache()
        
        if not self._node_cache:
            return None, float('inf')
        
        z = np.asarray(z, dtype=np.float32).flatten()
        
        min_dist = float('inf')
        closest_id = None
        
        for node_id, centroid in self._node_cache.items():
            dist = np.linalg.norm(z - centroid)
            if dist < min_dist:
                min_dist = dist
                closest_id = node_id
        
        return closest_id, min_dist
    
    def find_or_create_node(
        self, 
        z: np.ndarray, 
        value: float = 0.0,
        timestamp: float = 0.0
    ) -> int:
        """
        Find existing node within cluster radius, or create new one.
        
        Args:
            z: Latent vector
            value: Value estimate for this state
            timestamp: Creation timestamp
            
        Returns:
            Node ID (existing or newly created)
        """
        z = np.asarray(z, dtype=np.float32).flatten()
        
        closest_id, dist = self.get_closest_node(z)
        
        if closest_id is not None and dist <= self.cluster_radius:
            # Update existing node (incremental centroid + visit count)
            self._update_node(closest_id, z, value)
            return closest_id
        else:
            # Create new node
            return self._create_node(z, value, timestamp)
    
    def _create_node(
        self, 
        z: np.ndarray, 
        value: float = 0.0,
        timestamp: float = 0.0
    ) -> int:
        """Create a new node and return its ID."""
        z_blob = z.astype(np.float32).tobytes()
        
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO nodes (z_centroid, visit_count, avg_value, created_at)
                VALUES (?, 1, ?, ?)
                """,
                (z_blob, value, timestamp)
            )
            node_id = cursor.lastrowid
            conn.commit()
        
        # Update cache
        self._node_cache[node_id] = z.copy()
        
        logger.debug(f"Created node {node_id} (value={value:.3f})")
        return node_id
    
    def _update_node(self, node_id: int, z: np.ndarray, value: float):
        """
        Update node with new observation (incremental averaging).
        
        Centroid update: c_new = (c_old * n + z) / (n + 1)
        Value update: v_new = (v_old * n + value) / (n + 1)
        """
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT z_centroid, visit_count, avg_value FROM nodes WHERE id = ?",
                (node_id,)
            ).fetchone()
            
            if row is None:
                return
            
            old_z = np.frombuffer(row["z_centroid"], dtype=np.float32)
            n = row["visit_count"]
            old_value = row["avg_value"]
            
            # Incremental averaging
            new_z = (old_z * n + z) / (n + 1)
            new_value = (old_value * n + value) / (n + 1)
            
            conn.execute(
                """
                UPDATE nodes 
                SET z_centroid = ?, visit_count = ?, avg_value = ?
                WHERE id = ?
                """,
                (new_z.astype(np.float32).tobytes(), n + 1, new_value, node_id)
            )
            conn.commit()
        
        # Update cache
        self._node_cache[node_id] = new_z
    
    def add_transition(
        self,
        z_t: np.ndarray,
        action: int,
        reward: float,
        z_next: np.ndarray,
        value_t: float = 0.0,
        value_next: float = 0.0,
        timestamp: float = 0.0
    ):
        """
        Add a state transition to the graph.
        
        Creates/updates nodes and edges as needed.
        
        Args:
            z_t: Current latent state
            action: Action taken (0=LONG, 1=SHORT, 2=FLAT)
            reward: Reward received
            z_next: Next latent state
            value_t: Value estimate for z_t
            value_next: Value estimate for z_next
            timestamp: Transition timestamp
        """
        # Find or create nodes
        node_t = self.find_or_create_node(z_t, value_t, timestamp)
        node_next = self.find_or_create_node(z_next, value_next, timestamp)
        
        # Update edge
        self._update_edge(node_t, node_next, action, reward)
    
    def _update_edge(
        self, 
        source_id: int, 
        target_id: int, 
        action: int, 
        reward: float
    ):
        """
        Update or create edge with new transition data.
        
        Uses Welford's online algorithm for running variance.
        """
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT reward_mean, reward_var, count 
                FROM edges 
                WHERE source_id = ? AND target_id = ? AND action = ?
                """,
                (source_id, target_id, action)
            ).fetchone()
            
            if row is None:
                # Create new edge
                conn.execute(
                    """
                    INSERT INTO edges (source_id, target_id, action, reward_mean, reward_var, count)
                    VALUES (?, ?, ?, ?, 0.0, 1)
                    """,
                    (source_id, target_id, action, reward)
                )
            else:
                # Update existing edge (Welford's algorithm)
                old_mean = row["reward_mean"]
                old_var = row["reward_var"]
                n = row["count"]
                
                new_n = n + 1
                delta = reward - old_mean
                new_mean = old_mean + delta / new_n
                delta2 = reward - new_mean
                new_var = old_var + delta * delta2
                
                conn.execute(
                    """
                    UPDATE edges 
                    SET reward_mean = ?, reward_var = ?, count = ?
                    WHERE source_id = ? AND target_id = ? AND action = ?
                    """,
                    (new_mean, new_var, new_n, source_id, target_id, action)
                )
            
            conn.commit()
    
    def get_node(self, node_id: int) -> Optional[GraphNode]:
        """Get node by ID."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ?",
                (node_id,)
            ).fetchone()
            
            if row is None:
                return None
            
            return GraphNode(
                id=row["id"],
                z_centroid=np.frombuffer(row["z_centroid"], dtype=np.float32),
                visit_count=row["visit_count"],
                avg_value=row["avg_value"],
                created_at=row["created_at"]
            )
    
    def get_outgoing_edges(self, node_id: int) -> List[GraphEdge]:
        """Get all outgoing edges from a node."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM edges WHERE source_id = ?",
                (node_id,)
            )
            
            return [
                GraphEdge(
                    source_id=row["source_id"],
                    target_id=row["target_id"],
                    action=row["action"],
                    reward_mean=row["reward_mean"],
                    reward_var=row["reward_var"],
                    count=row["count"]
                )
                for row in cursor
            ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        with self._get_conn() as conn:
            node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            total_visits = conn.execute("SELECT SUM(visit_count) FROM nodes").fetchone()[0] or 0
            
            return {
                "node_count": node_count,
                "edge_count": edge_count,
                "total_visits": total_visits,
                "db_path": str(self.db_path),
                "cache_size": len(self._node_cache)
            }
    
    def prune_low_count_edges(self, min_count: int = 2):
        """
        Remove edges with count below threshold.
        
        This keeps the graph sparse and focused on reliable transitions.
        
        Args:
            min_count: Minimum transition count to keep edge
        """
        with self._get_conn() as conn:
            result = conn.execute(
                "DELETE FROM edges WHERE count < ?",
                (min_count,)
            )
            deleted = result.rowcount
            conn.commit()
            
        if deleted > 0:
            logger.info(f"Pruned {deleted} low-count edges (min_count={min_count})")
        
        return deleted
    
    def prune_orphan_nodes(self):
        """Remove nodes with no edges (isolated)."""
        with self._get_conn() as conn:
            result = conn.execute("""
                DELETE FROM nodes 
                WHERE id NOT IN (SELECT DISTINCT source_id FROM edges)
                AND id NOT IN (SELECT DISTINCT target_id FROM edges)
            """)
            deleted = result.rowcount
            conn.commit()
        
        if deleted > 0:
            self._cache_valid = False  # Invalidate cache
            logger.info(f"Pruned {deleted} orphan nodes")
        
        return deleted
    
    def close(self):
        """Close database connections and clear cache."""
        self._node_cache.clear()
        self._cache_valid = False
        logger.info("CausalGraph closed")
