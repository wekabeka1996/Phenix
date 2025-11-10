"""
Tests for XAI Integration (Task 4.2.T1 and 4.2.T2)

This module tests the XAI integration capabilities of RewardEngineV3Plus,
ensuring proper data validation and explanation generation.
"""

import pytest
import json
import logging
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch

from alysha_core.reward_engine_v3plus.xai_integration import RewardEngineXAI
from alysha_core.reward_engine_v3plus.data_types import (
    TotalRewardResult, 
    RewardComponentResult
)
from alysha_core.reward_engine_v3plus.utils import RewardEngineConfig


class TestXAIIntegration:
    """Test XAI integration functionality."""
    pass


class TestXAIDataValidation:
    """Test 4.2.T1: Validation of data for XAI."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock RewardEngineConfig."""
        config = RewardEngineConfig.get_default()
        return config
    
    @pytest.fixture
    def xai_integration(self, mock_config):
        """Create XAI integration instance."""
        return RewardEngineXAI(mock_config)
    
    @pytest.fixture
    def sample_reward_result(self):
        """Create sample reward result for testing."""
        component_rewards = {
            'profit_loss': RewardComponentResult(
                component_name='profit_loss',
                raw_value=150.0,
                normalized_value=0.75,
                subcomponents={'pnl': 150.0},
                metadata={'weight': 0.4, 'value': 30.0, 'explanation': "Profit/Loss component"}
            ),
            'risk': RewardComponentResult(
                component_name='risk',
                raw_value=-0.3,
                normalized_value=-0.6,
                subcomponents={'var_penalty': -0.3},
                metadata={'weight': 0.3, 'value': -18.0, 'explanation': "Risk penalty component"}
            ),
            'execution': RewardComponentResult(
                component_name='execution',
                raw_value=0.05,
                normalized_value=0.5,
                subcomponents={'transaction_cost': -0.02, 'slippage': -0.03},
                metadata={'weight': 0.2, 'value': 10.0, 'explanation': "Execution quality component"}
            ),
            'shaping': RewardComponentResult(
                component_name='shaping',
                raw_value=0.1,
                normalized_value=0.3,
                subcomponents={'state_bonus': 0.1},
                metadata={'weight': 0.1, 'value': 3.0, 'explanation': "State shaping component"}
            )
        }
        
        adaptive_weights = {
            'profit_loss': 0.4,
            'risk': 0.3,
            'execution': 0.2,
            'shaping': 0.1
        }
        
        normalization_stats = {
            'profit_loss': {'mean': 100.0, 'std': 50.0},
            'risk': {'mean': -0.2, 'std': 0.1},
            'execution': {'mean': 0.0, 'std': 0.05},
            'shaping': {'mean': 0.0, 'std': 0.2}
        }
        
        return TotalRewardResult(
            total_reward=25.0,
            component_rewards=component_rewards,
            adaptive_weights=adaptive_weights,
            normalization_stats=normalization_stats,
            timestamp=datetime.now().timestamp(),
            metadata={'engine_version': 'V3Plus', 'calculation_time': 0.001}
        )
    
    def test_explanation_structure_completeness(self, xai_integration, sample_reward_result):
        """Test that XAI explanation contains all required fields."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        
        # Required top-level fields
        required_fields = [
            'trace_id', 'timestamp_utc', 'component_source', 'event_type',
            'total_reward', 'component_breakdown', 'importance_scores',
            'explanation_text', 'feature_importance', 'decision_factors',
            'explainability_score', 'confidence_score', 'metadata'
        ]
        
        for field in required_fields:
            assert field in explanation, f"Missing required field: {field}"
    
    def test_component_breakdown_validation(self, xai_integration, sample_reward_result):
        """Test that component breakdown contains proper structure."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        breakdown = explanation['component_breakdown']
        
        # Check each component has required fields
        required_component_fields = ['value', 'contribution_percent', 'impact_level', 'direction']
        
        for component_name, component_data in breakdown.items():
            for field in required_component_fields:
                assert field in component_data, f"Component {component_name} missing field: {field}"
            
            # Validate data types and ranges
            assert isinstance(component_data['value'], (int, float))
            assert isinstance(component_data['contribution_percent'], (int, float))
            assert 0 <= component_data['contribution_percent'] <= 100
            assert component_data['impact_level'] in ['low', 'medium', 'high']
            assert component_data['direction'] in ['positive', 'negative', 'neutral']
    
    def test_importance_scores_validation(self, xai_integration, sample_reward_result):
        """Test that importance scores are properly calculated and normalized."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        importance_scores = explanation['importance_scores']
        
        # All components should have importance scores
        component_names = set(sample_reward_result.component_rewards.keys())
        score_names = set(importance_scores.keys())
        assert component_names == score_names, "Importance scores don't match components"
        
        # Scores should be between 0 and 1
        for component, score in importance_scores.items():
            assert 0 <= score <= 1, f"Invalid importance score for {component}: {score}"
        
        # Scores should approximately sum to 1 (allowing for floating point errors)
        total_score = sum(importance_scores.values())
        assert abs(total_score - 1.0) < 0.001, f"Importance scores don't sum to 1: {total_score}"
    
    def test_metadata_validation(self, xai_integration, sample_reward_result):
        """Test that metadata contains proper information."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        metadata = explanation['metadata']
        
        required_metadata_fields = ['engine_version', 'adaptive_weights', 'normalization_stats', 'timestamp']
        
        for field in required_metadata_fields:
            assert field in metadata, f"Missing metadata field: {field}"
        
        assert metadata['engine_version'] == 'V3Plus'
        assert isinstance(metadata['adaptive_weights'], dict)
        assert isinstance(metadata['normalization_stats'], dict)
    
    def test_explainability_and_confidence_scores(self, xai_integration, sample_reward_result):
        """Test explainability and confidence score calculation."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        
        explainability_score = explanation['explainability_score']
        confidence_score = explanation['confidence_score']
        
        # Both scores should be between 0 and 1
        assert 0 <= explainability_score <= 1, f"Invalid explainability score: {explainability_score}"
        assert 0 <= confidence_score <= 1, f"Invalid confidence score: {confidence_score}"
    
    def test_json_serialization(self, xai_integration, sample_reward_result):
        """Test that explanation can be serialized to JSON."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        
        try:
            json_str = json.dumps(explanation, default=str)
            parsed = json.loads(json_str)
            assert isinstance(parsed, dict)
        except Exception as e:
            pytest.fail(f"Explanation cannot be serialized to JSON: {e}")


class TestXAIExplanationGeneration:
    """Test 4.2.T2: Testing XAI explanation generation."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock RewardEngineConfig."""
        config = RewardEngineConfig.get_default()
        return config
    
    @pytest.fixture
    def xai_integration(self, mock_config):
        """Create XAI integration instance."""
        return RewardEngineXAI(mock_config)
    
    @pytest.fixture
    def sample_reward_result(self):
        """Create sample reward result for testing."""
        component_rewards = {
            'profit_loss': RewardComponentResult(
                component_name='profit_loss',
                raw_value=150.0,
                normalized_value=0.75,
                subcomponents={'pnl': 150.0},
                metadata={'weight': 0.4, 'value': 30.0, 'explanation': "Profit/Loss component"}
            ),
            'risk': RewardComponentResult(
                component_name='risk',
                raw_value=-0.3,
                normalized_value=-0.6,
                subcomponents={'var_penalty': -0.3},
                metadata={'weight': 0.3, 'value': -18.0, 'explanation': "Risk penalty component"}
            ),
            'execution': RewardComponentResult(
                component_name='execution',
                raw_value=0.05,
                normalized_value=0.5,
                subcomponents={'transaction_cost': -0.02, 'slippage': -0.03},
                metadata={'weight': 0.2, 'value': 10.0, 'explanation': "Execution quality component"}
            ),
            'shaping': RewardComponentResult(
                component_name='shaping',
                raw_value=0.1,
                normalized_value=0.3,
                subcomponents={'state_bonus': 0.1},
                metadata={'weight': 0.1, 'value': 3.0, 'explanation': "State shaping component"}
            )
        }
        
        adaptive_weights = {
            'profit_loss': 0.4,
            'risk': 0.3,
            'execution': 0.2,
            'shaping': 0.1
        }
        
        normalization_stats = {
            'profit_loss': {'mean': 100.0, 'std': 50.0},
            'risk': {'mean': -0.2, 'std': 0.1},
            'execution': {'mean': 0.0, 'std': 0.05},
            'shaping': {'mean': 0.0, 'std': 0.2}
        }
        
        return TotalRewardResult(
            total_reward=25.0,
            component_rewards=component_rewards,
            adaptive_weights=adaptive_weights,
            normalization_stats=normalization_stats,
            timestamp=datetime.now().timestamp(),
            metadata={'engine_version': 'V3Plus', 'calculation_time': 0.001}
        )
    
    def test_explanation_text_generation(self, xai_integration, sample_reward_result):
        """Test that explanation text is informative and correct."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        explanation_text = explanation['explanation_text']
        
        assert isinstance(explanation_text, str)
        assert len(explanation_text) > 0
        
        # Should mention total reward
        total_reward = sample_reward_result.total_reward
        assert str(total_reward) in explanation_text or f"{total_reward:.4f}" in explanation_text
    
    def test_dominant_component_identification(self, xai_integration, sample_reward_result):
        """Test that XAI correctly identifies dominant components."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        importance_scores = explanation['importance_scores']
        
        # Profit/Loss component should be most important (has highest absolute value: 30.0)
        max_importance_component = max(importance_scores.items(), key=lambda x: x[1])
        assert max_importance_component[0] == 'profit_loss', "Failed to identify dominant component"
    
    def test_impact_level_classification(self, xai_integration, sample_reward_result):
        """Test proper classification of impact levels."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        breakdown = explanation['component_breakdown']
        
        # Test different scenarios
        high_impact_components = [name for name, data in breakdown.items() 
                                if data['impact_level'] == 'high']
        
        # Should have at least one high impact component (profit_loss and risk should be high)
        assert len(high_impact_components) > 0, "No high impact components identified"
    
    def test_direction_classification(self, xai_integration, sample_reward_result):
        """Test proper direction classification."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        breakdown = explanation['component_breakdown']
        
        # Profit/Loss should be positive (30.0 > 0)
        assert breakdown['profit_loss']['direction'] == 'positive'
        
        # Risk should be negative (-18.0 < 0)  
        assert breakdown['risk']['direction'] == 'negative'
        
        # Execution should be positive (10.0 > 0)
        assert breakdown['execution']['direction'] == 'positive'
    
    def test_contribution_percentage_calculation(self, xai_integration, sample_reward_result):
        """Test that contribution percentages are calculated correctly."""
        explanation = xai_integration.generate_explanation(sample_reward_result)
        breakdown = explanation['component_breakdown']
        
        # Calculate expected percentages
        # Values: profit_loss=30.0, risk=-18.0, execution=10.0, shaping=3.0
        # Absolute values: 30.0, 18.0, 10.0, 3.0
        # Total absolute: 61.0
        # Expected percentages: ~49.2%, ~29.5%, ~16.4%, ~4.9%
        
        total_percentage = sum(comp['contribution_percent'] for comp in breakdown.values())
        assert abs(total_percentage - 100.0) < 0.1, f"Contribution percentages don't sum to 100%: {total_percentage}"
        
        # Profit/Loss should have highest contribution
        profit_loss_contribution = breakdown['profit_loss']['contribution_percent']
        risk_contribution = breakdown['risk']['contribution_percent']
        
        assert profit_loss_contribution > risk_contribution, "Profit/Loss should have higher contribution than Risk"


class TestXAIErrorHandling:
    """Test XAI error handling and edge cases."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock RewardEngineConfig."""
        config = RewardEngineConfig.get_default()
        return config
    
    @pytest.fixture
    def xai_integration(self, mock_config):
        """Create XAI integration instance."""
        return RewardEngineXAI(mock_config)
    
    def test_empty_components_handling(self, xai_integration):
        """Test handling of empty component rewards."""
        empty_result = TotalRewardResult(
            total_reward=0.0,
            component_rewards={},
            adaptive_weights={},
            normalization_stats={},
            timestamp=datetime.now().timestamp(),
            metadata={}
        )
        
        explanation = xai_integration.generate_explanation(empty_result)
        assert explanation is not None
        assert explanation['total_reward'] == 0.0
        assert isinstance(explanation['component_breakdown'], dict)
    
    def test_zero_values_handling(self, xai_integration):
        """Test handling of zero reward values."""
        zero_components = {
            'component1': RewardComponentResult(
                component_name='component1',
                raw_value=0.0,
                normalized_value=0.0,
                metadata={'weight': 0.5, 'value': 0.0, 'explanation': "Zero component"}
            ),
            'component2': RewardComponentResult(
                component_name='component2',
                raw_value=0.0,
                normalized_value=0.0,
                metadata={'weight': 0.5, 'value': 0.0, 'explanation': "Another zero component"}
            )
        }
        
        zero_result = TotalRewardResult(
            total_reward=0.0,
            component_rewards=zero_components,
            adaptive_weights={},
            normalization_stats={},
            timestamp=datetime.now().timestamp(),
            metadata={}
        )
        
        explanation = xai_integration.generate_explanation(zero_result)
        assert explanation is not None
        
        # All importance scores should be 0
        for score in explanation['importance_scores'].values():
            assert score == 0.0, "Zero values should result in zero importance scores"
    
    def test_invalid_data_handling(self, xai_integration):
        """Test handling of invalid or corrupted data."""
        # Test with None result
        with patch.object(xai_integration, '_create_error_explanation') as mock_error:
            mock_error.return_value = {'error': 'test_error'}
            
            # This should trigger error handling
            result = xai_integration.generate_explanation(None)
            assert 'error' in result or result is not None


class TestXAILogging:
    """Test XAI logging functionality."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock RewardEngineConfig."""
        config = RewardEngineConfig.get_default()
        return config
    
    @pytest.fixture
    def xai_integration(self, mock_config):
        """Create XAI integration instance."""
        return RewardEngineXAI(mock_config)
    
    @pytest.fixture
    def sample_reward_result(self):
        """Create sample reward result for testing."""
        component_rewards = {
            'profit_loss': RewardComponentResult(
                component_name='profit_loss',
                raw_value=150.0,
                normalized_value=0.75,
                subcomponents={'pnl': 150.0},
                metadata={'weight': 0.4, 'value': 30.0, 'explanation': "Profit/Loss component"}
            )
        }
        
        return TotalRewardResult(
            total_reward=25.0,
            component_rewards=component_rewards,
            adaptive_weights={'profit_loss': 0.4},
            normalization_stats={'profit_loss': {'mean': 100.0, 'std': 50.0}},
            timestamp=datetime.now().timestamp(),
            metadata={'engine_version': 'V3Plus', 'calculation_time': 0.001}
        )
    
    def test_explanation_logging(self, xai_integration, sample_reward_result, tmp_path):
        """Test that explanations are properly logged."""
        # Set up temporary log path
        xai_integration.explanation_log_path = tmp_path / "xai_logs"
        xai_integration.explanation_log_path.mkdir(exist_ok=True)
        
        # Generate explanation (should trigger logging)
        explanation = xai_integration.generate_explanation(sample_reward_result)
        
        # Check if log file was created (jsonl format)
        log_files = list(xai_integration.explanation_log_path.glob("*.jsonl"))
        assert len(log_files) > 0, "No explanation log files created"
    
    def test_structured_logging_format(self, xai_integration, sample_reward_result):
        """Test that logging follows structured format."""
        with patch.object(xai_integration, '_log_explanation') as mock_log:
            explanation = xai_integration.generate_explanation(sample_reward_result)
            
            # Should have called logging function
            mock_log.assert_called_once()
            logged_data = mock_log.call_args[0][0]
            
            # Verify structured format
            assert 'trace_id' in logged_data
            assert 'timestamp_utc' in logged_data
            assert 'component_source' in logged_data
            assert logged_data['component_source'] == 'RewardEngineV3Plus'


# Performance and integration tests
class TestXAIPerformance:
    """Test XAI performance characteristics."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock RewardEngineConfig."""
        config = RewardEngineConfig.get_default()
        return config
    
    @pytest.fixture
    def xai_integration(self, mock_config):
        """Create XAI integration instance."""
        return RewardEngineXAI(mock_config)
    
    @pytest.fixture
    def sample_reward_result(self):
        """Create sample reward result for testing."""
        component_rewards = {
            'profit_loss': RewardComponentResult(
                component_name='profit_loss',
                raw_value=150.0,
                normalized_value=0.75,
                subcomponents={'pnl': 150.0},
                metadata={'weight': 0.4, 'value': 30.0, 'explanation': "Profit/Loss component"}
            )
        }
        
        return TotalRewardResult(
            total_reward=25.0,
            component_rewards=component_rewards,
            adaptive_weights={'profit_loss': 0.4},
            normalization_stats={'profit_loss': {'mean': 100.0, 'std': 50.0}},
            timestamp=datetime.now().timestamp(),
            metadata={'engine_version': 'V3Plus', 'calculation_time': 0.001}
        )
    
    def test_explanation_generation_performance(self, xai_integration, sample_reward_result):
        """Test that explanation generation completes within reasonable time."""
        import time
        
        start_time = time.time()
        explanation = xai_integration.generate_explanation(sample_reward_result)
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        # Should complete within 100ms for reasonable sized data
        assert execution_time < 0.1, f"Explanation generation too slow: {execution_time:.3f}s"
        assert explanation is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
