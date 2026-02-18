"""
The Dreamer - Offline Consolidation Module

Phase R1.5: Background process for experience consolidation.

Takes raw episodes from EpisodicBuffer and structures them into
the CausalGraph (hippocampus). Runs periodically to avoid
blocking the main inference loop.

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                         Dreamer                              │
    │                                                              │
    │   Input: List[Episode]                                       │
    │      │                                                       │
    │      ▼                                                       │
    │   ┌────────────────────────────────────┐                    │
    │   │ For each episode:                   │                    │
    │   │   1. Encode features → z            │                    │
    │   │   2. Build transitions (z,a,r,z')   │                    │
    │   │   3. Add to CausalGraph             │                    │
    │   └────────────────────────────────────┘                    │
    │      │                                                       │
    │      ▼                                                       │
    │   Prune (remove weak edges)                                  │
    │      │                                                       │
    │      ▼                                                       │
    │   Output: Updated hippocampus.db                             │
    └──────────────────────────────────────────────────────────────┘

Runs in worker process to leverage GPU for encoding.
"""

import logging
import time
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DreamEpisode:
    """
    Simplified episode structure for dreaming.
    
    Contains already-encoded latent states to avoid re-encoding.
    """
    symbol: str
    timestamp: float
    z_sequence: List[np.ndarray]  # Latent states
    actions: List[int]  # Actions taken (0=LONG, 1=SHORT, 2=FLAT)
    rewards: List[float]  # Rewards received
    values: List[float]  # Value estimates
    
    @property
    def length(self) -> int:
        return len(self.z_sequence)


class Dreamer:
    """
    Offline consolidation module.
    
    Takes raw episodes, encodes them, and builds graph structure.
    Designed to run in background worker process.
    """
    
    # Action name to index mapping
    ACTION_MAP = {"LONG": 0, "SHORT": 1, "FLAT": 2, "BUY": 0, "SELL": 1}
    
    def __init__(
        self,
        graph,  # CausalGraph instance
        encoder: Optional[Callable[[np.ndarray], np.ndarray]] = None,
        prune_after_n_episodes: int = 100,
        min_edge_count_for_prune: int = 2
    ):
        """
        Initialize the Dreamer.
        
        Args:
            graph: CausalGraph instance for storing transitions
            encoder: Optional function to encode features -> z
            prune_after_n_episodes: Run pruning after this many episodes
            min_edge_count_for_prune: Minimum edge count to survive pruning
        """
        self.graph = graph
        self.encoder = encoder
        self.prune_after_n_episodes = prune_after_n_episodes
        self.min_edge_count_for_prune = min_edge_count_for_prune
        
        # Stats
        self._episodes_processed = 0
        self._transitions_added = 0
        self._last_consolidation_time = 0.0
        self._total_consolidation_time = 0.0
    
    def consolidate(
        self,
        episodes: List[Any],
        encode_fn: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Consolidate a batch of episodes into the graph.
        
        Args:
            episodes: List of Episode objects with features and rewards
            encode_fn: Optional encoder function (overrides self.encoder)
            
        Returns:
            Consolidation statistics
        """
        start_time = time.time()
        encoder = encode_fn or self.encoder
        
        transitions_count = 0
        episodes_count = 0
        
        for episode in episodes:
            try:
                n_trans = self._process_episode(episode, encoder)
                transitions_count += n_trans
                episodes_count += 1
            except Exception as e:
                logger.warning(f"Failed to process episode: {e}")
                continue
        
        self._episodes_processed += episodes_count
        self._transitions_added += transitions_count
        
        # Periodic pruning
        if self._episodes_processed % self.prune_after_n_episodes == 0:
            self._run_pruning()
        
        elapsed = time.time() - start_time
        self._last_consolidation_time = elapsed
        self._total_consolidation_time += elapsed
        
        stats = self.graph.get_stats()
        
        result = {
            "episodes_processed": episodes_count,
            "transitions_added": transitions_count,
            "elapsed_sec": elapsed,
            "total_episodes": self._episodes_processed,
            "total_transitions": self._transitions_added,
            "graph_nodes": stats["node_count"],
            "graph_edges": stats["edge_count"]
        }
        
        logger.info(
            f"Dream consolidation complete: {episodes_count} episodes, "
            f"{transitions_count} transitions in {elapsed:.2f}s "
            f"(Graph: {stats['node_count']} nodes, {stats['edge_count']} edges)"
        )
        
        return result
    
    def _process_episode(
        self, 
        episode: Any, 
        encoder: Optional[Callable]
    ) -> int:
        """
        Process a single episode into graph transitions.
        
        Args:
            episode: Episode object with features, side, reward
            encoder: Encoder function
            
        Returns:
            Number of transitions added
        """
        # Extract features from episode
        features = episode.features if hasattr(episode, 'features') else {}
        if not features:
            return 0
        
        # Convert features to numpy array
        feature_values = np.array(list(features.values()), dtype=np.float32)
        
        # Encode to latent space
        if encoder is not None:
            z = encoder(feature_values)
        else:
            # Fallback: use raw features as "latent" space
            z = feature_values
        
        # Get action (side mapping)
        side = getattr(episode, 'side', None) or "FLAT"
        action = self.ACTION_MAP.get(side.upper(), 2)
        
        # Get reward
        reward = getattr(episode, 'reward', 0.0) or 0.0
        
        # Get value estimate (if available)
        value = getattr(episode, 'value', 0.0) or 0.0
        
        # Get timestamp
        timestamp = getattr(episode, 'timestamp', time.time())
        
        # For single-step episodes, we create a self-transition
        # (This represents "being in a state" rather than transitioning)
        # In future, we'll process multi-step trajectories properly
        
        # Add single transition (z -> z' where z' = z for now)
        # In real scenarios, z_next would come from the next tick
        z_next = z  # Placeholder - proper sequence handling needed
        
        self.graph.add_transition(
            z_t=z,
            action=action,
            reward=reward,
            z_next=z_next,
            value_t=value,
            value_next=value,
            timestamp=timestamp
        )
        
        return 1
    
    def consolidate_sequences(
        self,
        z_sequences: List[np.ndarray],
        action_sequences: List[List[int]],
        reward_sequences: List[List[float]],
        value_sequences: Optional[List[List[float]]] = None
    ) -> Dict[str, Any]:
        """
        Consolidate pre-encoded sequences directly.
        
        This is more efficient when latent states are already computed
        during inference.
        
        Args:
            z_sequences: List of (T, latent_dim) arrays
            action_sequences: List of action lists
            reward_sequences: List of reward lists
            value_sequences: Optional list of value lists
            
        Returns:
            Consolidation statistics
        """
        start_time = time.time()
        transitions_count = 0
        
        for i, z_seq in enumerate(z_sequences):
            actions = action_sequences[i]
            rewards = reward_sequences[i]
            values = value_sequences[i] if value_sequences else [0.0] * len(rewards)
            
            # Process consecutive transitions
            for t in range(len(z_seq) - 1):
                if t >= len(actions) or t >= len(rewards):
                    break
                
                self.graph.add_transition(
                    z_t=z_seq[t],
                    action=actions[t],
                    reward=rewards[t],
                    z_next=z_seq[t + 1],
                    value_t=values[t] if t < len(values) else 0.0,
                    value_next=values[t + 1] if t + 1 < len(values) else 0.0
                )
                transitions_count += 1
        
        self._transitions_added += transitions_count
        self._episodes_processed += len(z_sequences)
        
        elapsed = time.time() - start_time
        stats = self.graph.get_stats()
        
        return {
            "transitions_added": transitions_count,
            "elapsed_sec": elapsed,
            "graph_nodes": stats["node_count"],
            "graph_edges": stats["edge_count"]
        }
    
    def _run_pruning(self):
        """Run graph pruning to keep it sparse."""
        logger.info("Running graph pruning...")
        
        # Remove low-count edges
        edges_pruned = self.graph.prune_low_count_edges(self.min_edge_count_for_prune)
        
        # Remove orphan nodes
        nodes_pruned = self.graph.prune_orphan_nodes()
        
        logger.info(f"Pruning complete: {edges_pruned} edges, {nodes_pruned} nodes removed")
    
    def get_curiosity_bonus(self, z: np.ndarray) -> float:
        """
        Calculate curiosity bonus based on state novelty.
        
        Less-visited nodes get higher bonus (intrinsic motivation).
        
        Args:
            z: Latent state vector
            
        Returns:
            Curiosity bonus (0.0 to 1.0)
        """
        node_id, distance = self.graph.get_closest_node(z)
        
        if node_id is None:
            # Completely novel state - high curiosity
            return 1.0
        
        node = self.graph.get_node(node_id)
        if node is None:
            return 1.0
        
        # ICM-style curiosity: 1 / sqrt(visit_count)
        # Bounded to [0, 1]
        curiosity = 1.0 / np.sqrt(max(1, node.visit_count))
        
        # Also factor in distance from cluster center
        # Far from center = more novel variation
        distance_bonus = min(distance / self.graph.cluster_radius, 1.0) * 0.3
        
        return min(1.0, curiosity + distance_bonus)
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get dreamer statistics."""
        graph_stats = self.graph.get_stats()
        
        return {
            "episodes_processed": self._episodes_processed,
            "transitions_added": self._transitions_added,
            "last_consolidation_sec": self._last_consolidation_time,
            "total_consolidation_sec": self._total_consolidation_time,
            **graph_stats
        }


# Standalone function for worker process
def dream_consolidation(
    episodes_data: List[Dict],
    db_path: str,
    latent_dim: int,
    encoder_fn: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Standalone function for worker process execution.
    
    Args:
        episodes_data: List of episode dicts
        db_path: Path to hippocampus.db
        latent_dim: Latent dimension for graph
        encoder_fn: Optional encoder function
        
    Returns:
        Consolidation statistics
    """
    from apps.reference.domains.neocortex.logic.memory.graph import CausalGraph
    
    # Create graph
    graph = CausalGraph(
        db_path=Path(db_path),
        latent_dim=latent_dim
    )
    
    # Create dreamer
    dreamer = Dreamer(graph=graph, encoder=encoder_fn)
    
    # Convert dicts back to episode-like objects
    @dataclass
    class EpisodeLike:
        features: Dict
        side: str
        reward: float
        timestamp: float
        value: float = 0.0
    
    episodes = [
        EpisodeLike(
            features=ep.get("features", {}),
            side=ep.get("side", "FLAT"),
            reward=ep.get("reward", 0.0),
            timestamp=ep.get("timestamp", 0.0),
            value=ep.get("value", 0.0)
        )
        for ep in episodes_data
    ]
    
    # Consolidate
    result = dreamer.consolidate(episodes)
    
    graph.close()
    
    return result
