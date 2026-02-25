"""
Tests for Phase R1.5: The Dreamer - Offline Consolidation

Tests cover:
1. CausalGraph SQLite operations
2. Node clustering and edge updates
3. Dreamer consolidation logic
4. Integration with episodes
"""

import pytest
import tempfile
import shutil
import numpy as np
from pathlib import Path
from dataclasses import dataclass
from typing import Dict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.memory.graph import CausalGraph, GraphNode, GraphEdge
from logic.dreamer import Dreamer


class TestCausalGraph:
    """Tests for CausalGraph SQLite operations."""
    
    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create temporary database path."""
        db_path = tmp_path / "test_hippocampus.db"
        yield db_path
        # Cleanup happens automatically with tmp_path
    
    @pytest.fixture
    def graph(self, temp_db):
        """Create a graph instance."""
        g = CausalGraph(db_path=temp_db, latent_dim=8)
        yield g
        g.close()
    
    def test_graph_initialization(self, graph, temp_db):
        """Test graph creates database file."""
        assert temp_db.exists()
        
    def test_create_node(self, graph):
        """Test node creation."""
        z = np.random.randn(8).astype(np.float32)
        node_id = graph._create_node(z, value=1.5)
        
        assert node_id > 0
        
        # Retrieve node
        node = graph.get_node(node_id)
        assert node is not None
        assert node.id == node_id
        assert node.visit_count == 1
        assert abs(node.avg_value - 1.5) < 0.01
    
    def test_find_closest_node(self, graph):
        """Test nearest neighbor search."""
        # Create some nodes
        z1 = np.array([0, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        z2 = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.float32)
        
        id1 = graph._create_node(z1)
        id2 = graph._create_node(z2)
        
        # Query close to z1
        query = np.array([0.1, 0.1, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        closest, dist = graph.get_closest_node(query)
        
        assert closest == id1
        assert dist < 0.2
    
    def test_find_or_create_existing(self, graph):
        """Test find_or_create returns existing node within radius."""
        z1 = np.array([0, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        id1 = graph._create_node(z1)
        
        # Very close query should return same node
        z_close = np.array([0.1, 0.1, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        id2 = graph.find_or_create_node(z_close)
        
        assert id2 == id1
        
        # Node should have visit_count=2 now
        node = graph.get_node(id1)
        assert node.visit_count == 2
    
    def test_find_or_create_new(self, graph):
        """Test find_or_create creates new node far from existing."""
        z1 = np.array([0, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        id1 = graph._create_node(z1)
        
        # Far query should create new node
        z_far = np.array([5, 5, 5, 5, 5, 5, 5, 5], dtype=np.float32)
        id2 = graph.find_or_create_node(z_far)
        
        assert id2 != id1
        
        stats = graph.get_stats()
        assert stats["node_count"] == 2
    
    def test_add_transition(self, graph):
        """Test adding a full transition."""
        z1 = np.random.randn(8).astype(np.float32)
        z2 = np.random.randn(8).astype(np.float32) + 2  # Far enough for separate node
        
        graph.add_transition(
            z_t=z1,
            action=0,  # LONG
            reward=5.0,
            z_next=z2,
            value_t=1.0,
            value_next=1.5
        )
        
        stats = graph.get_stats()
        assert stats["node_count"] == 2
        assert stats["edge_count"] == 1
    
    def test_edge_reward_statistics(self, graph):
        """Test edge reward mean/variance updates."""
        z1 = np.array([0, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        z2 = np.array([2, 2, 2, 2, 0, 0, 0, 0], dtype=np.float32)
        
        # Add multiple transitions with different rewards
        rewards = [1.0, 2.0, 3.0]
        for r in rewards:
            graph.add_transition(z_t=z1, action=0, reward=r, z_next=z2)
        
        # Get edge
        node1_id, _ = graph.get_closest_node(z1)
        edges = graph.get_outgoing_edges(node1_id)
        
        assert len(edges) == 1
        edge = edges[0]
        assert edge.count == 3
        assert abs(edge.reward_mean - 2.0) < 0.01  # Mean of [1,2,3] = 2
    
    def test_prune_low_count_edges(self, graph):
        """Test pruning edges with low count."""
        z1 = np.array([0, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
        z2 = np.array([2, 2, 2, 2, 0, 0, 0, 0], dtype=np.float32)
        z3 = np.array([4, 4, 4, 4, 0, 0, 0, 0], dtype=np.float32)
        
        # Add transitions - one with count=1, one with count=3
        graph.add_transition(z_t=z1, action=0, reward=1.0, z_next=z2)
        
        for _ in range(3):
            graph.add_transition(z_t=z1, action=1, reward=2.0, z_next=z3)
        
        stats_before = graph.get_stats()
        assert stats_before["edge_count"] == 2
        
        # Prune edges with count < 2
        graph.prune_low_count_edges(min_count=2)
        
        stats_after = graph.get_stats()
        assert stats_after["edge_count"] == 1  # Only the count=3 edge remains
    
    def test_get_stats(self, graph):
        """Test statistics retrieval."""
        stats = graph.get_stats()
        
        assert "node_count" in stats
        assert "edge_count" in stats
        assert "total_visits" in stats
        assert "db_path" in stats


class TestDreamer:
    """Tests for Dreamer consolidation logic."""
    
    @pytest.fixture
    def graph_and_dreamer(self, tmp_path):
        """Create graph and dreamer instances."""
        db_path = tmp_path / "test_dreamer.db"
        graph = CausalGraph(db_path=db_path, latent_dim=8)
        
        # Simple identity encoder for testing
        encoder = lambda x: x[:8] if len(x) >= 8 else np.pad(x, (0, 8-len(x)))
        
        dreamer = Dreamer(
            graph=graph,
            encoder=encoder,
            prune_after_n_episodes=50,
            min_edge_count_for_prune=2
        )
        
        yield graph, dreamer
        graph.close()
    
    @pytest.fixture
    def sample_episodes(self):
        """Create sample episodes for testing."""
        @dataclass
        class Episode:
            features: Dict
            side: str
            reward: float
            timestamp: float
            value: float = 0.0
        
        episodes = [
            Episode(
                features={"f1": 0.1, "f2": 0.2, "f3": 0.3, "f4": 0.4, 
                         "f5": 0.5, "f6": 0.6, "f7": 0.7, "f8": 0.8},
                side="LONG",
                reward=5.0,
                timestamp=1000.0
            ),
            Episode(
                features={"f1": 0.2, "f2": 0.3, "f3": 0.4, "f4": 0.5,
                         "f5": 0.6, "f6": 0.7, "f7": 0.8, "f8": 0.9},
                side="SHORT",
                reward=-2.0,
                timestamp=1001.0
            ),
            Episode(
                features={"f1": 1.0, "f2": 1.0, "f3": 1.0, "f4": 1.0,
                         "f5": 1.0, "f6": 1.0, "f7": 1.0, "f8": 1.0},
                side="FLAT",
                reward=0.0,
                timestamp=1002.0
            )
        ]
        return episodes
    
    def test_consolidate_episodes(self, graph_and_dreamer, sample_episodes):
        """Test consolidating episodes into graph."""
        graph, dreamer = graph_and_dreamer
        
        result = dreamer.consolidate(sample_episodes)
        
        assert result["episodes_processed"] == 3
        assert result["transitions_added"] == 3
        assert result["graph_nodes"] > 0
    
    def test_action_mapping(self, graph_and_dreamer):
        """Test action string to index mapping."""
        _, dreamer = graph_and_dreamer
        
        assert dreamer.ACTION_MAP["LONG"] == 0
        assert dreamer.ACTION_MAP["SHORT"] == 1
        assert dreamer.ACTION_MAP["FLAT"] == 2
        assert dreamer.ACTION_MAP["BUY"] == 0
        assert dreamer.ACTION_MAP["SELL"] == 1
    
    def test_curiosity_bonus_novel_state(self, graph_and_dreamer):
        """Test curiosity bonus for completely novel state."""
        _, dreamer = graph_and_dreamer
        
        # Empty graph - should give maximum curiosity
        z_novel = np.random.randn(8).astype(np.float32)
        curiosity = dreamer.get_curiosity_bonus(z_novel)
        
        assert curiosity == 1.0
    
    def test_curiosity_decreases_with_visits(self, graph_and_dreamer, sample_episodes):
        """Test curiosity decreases as states are visited."""
        graph, dreamer = graph_and_dreamer
        
        # Consolidate some episodes first
        dreamer.consolidate(sample_episodes)
        
        # Query a known state
        z = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float32)
        curiosity = dreamer.get_curiosity_bonus(z)
        
        # Should be less than 1.0 since similar states exist
        assert curiosity < 1.0
    
    def test_dreamer_stats(self, graph_and_dreamer, sample_episodes):
        """Test dreamer statistics tracking."""
        graph, dreamer = graph_and_dreamer
        
        dreamer.consolidate(sample_episodes)
        
        stats = dreamer.stats
        assert stats["episodes_processed"] == 3
        assert stats["transitions_added"] == 3
        assert stats["node_count"] > 0


class TestDreamerIntegration:
    """Integration tests for Dreamer with full pipeline."""
    
    def test_hippocampus_db_created(self, tmp_path):
        """Verify hippocampus.db is created after consolidation."""
        db_path = tmp_path / "hippocampus.db"
        
        assert not db_path.exists()
        
        graph = CausalGraph(db_path=db_path, latent_dim=8)
        dreamer = Dreamer(graph=graph)
        
        # Empty consolidation - should still create db
        dreamer.consolidate([])
        
        assert db_path.exists()
        graph.close()
    
    def test_graph_topology_preserved(self, tmp_path):
        """Verify graph edges A->B exist after consolidation."""
        db_path = tmp_path / "test_topology.db"
        graph = CausalGraph(db_path=db_path, latent_dim=4)
        
        # Create clear transition A -> B
        z_A = np.array([0, 0, 0, 0], dtype=np.float32)
        z_B = np.array([1, 1, 1, 1], dtype=np.float32)
        
        graph.add_transition(z_t=z_A, action=0, reward=1.0, z_next=z_B)
        
        # Get node A
        node_A_id, _ = graph.get_closest_node(z_A)
        node_B_id, _ = graph.get_closest_node(z_B)
        
        # Check edge exists
        edges = graph.get_outgoing_edges(node_A_id)
        
        assert len(edges) == 1
        assert edges[0].source_id == node_A_id
        assert edges[0].target_id == node_B_id
        assert edges[0].action == 0
        assert abs(edges[0].reward_mean - 1.0) < 0.01
        
        graph.close()


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
