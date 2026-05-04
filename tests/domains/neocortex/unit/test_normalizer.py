import pytest
import numpy as np
from pathlib import Path

from apps.reference.domains.neocortex.logic.ingest.normalizer import WelfordNormalizer, MultiSymbolWelfordNormalizer
from apps.reference.domains.neocortex.logic.ingest.normalizer import sanitize_symbol

def test_welford_normalizer_init():
    with pytest.raises(ValueError):
        WelfordNormalizer(0)
    
    norm = WelfordNormalizer(2)
    assert norm.dim == 2
    assert norm.count == 0

def test_welford_normalizer_update_and_variance():
    norm = WelfordNormalizer(2)
    # Variance of zero denominator (count < 2) returns zeros
    norm.update(np.array([1.0, 2.0]))
    assert norm.count == 1
    
    # Normalize with count=1 should just center it (std=1 from eps fallback)
    # std = sqrt(0 + eps) or 1.0 depending on eps. With x=mean, delta is 0
    res = norm.normalize(np.array([1.0, 2.0]))
    np.testing.assert_array_equal(res, np.array([0.0, 0.0]))
    
    norm.update(np.array([3.0, 4.0]))
    assert norm.count == 2
    # Mean is [2.0, 3.0]
    # Var is sum((x - mean)^2) / (count-1) -> [1 + 1] / 1 = [2.0, 2.0]
    # std is sqrt(2.0)
    
    st = norm.state()
    np.testing.assert_array_almost_equal(st.mean, np.array([2.0, 3.0]))
    
    res = norm.normalize(np.array([2.0, 3.0])) # Mean
    np.testing.assert_array_almost_equal(res, np.array([0.0, 0.0]))
    
    res = norm.normalize(np.array([2.0 + np.sqrt(2), 3.0 + np.sqrt(2)])) # +1 std
    np.testing.assert_array_almost_equal(res, np.array([1.0, 1.0]))

def test_welford_normalizer_dim_mismatch():
    norm = WelfordNormalizer(2)
    with pytest.raises(ValueError):
        norm.update(np.array([1.0]))
        
    with pytest.raises(ValueError):
        norm.normalize(np.array([1.0, 2.0, 3.0]))

def test_welford_normalizer_save_load(tmp_path):
    norm = WelfordNormalizer(2)
    norm.update(np.array([1.0, 2.0]))
    norm.update(np.array([3.0, 4.0]))
    
    state_file = tmp_path / "state.npz"
    norm.save_state(state_file)
    
    assert state_file.exists()
    
    norm2 = WelfordNormalizer(2)
    assert norm2.load_state(state_file) == True
    assert norm2.count == 2
    np.testing.assert_array_equal(norm2.state().mean, norm.state().mean)

    # Missing file
    norm3 = WelfordNormalizer(2)
    assert norm3.load_state(tmp_path / "missing.npz") == False

def test_multi_symbol_normalizer(tmp_path):
    multi = MultiSymbolWelfordNormalizer(2)
    assert multi.dim == 2
    assert sanitize_symbol(None) == "UNKNOWN"
    multi.update("BTC", np.array([1.0, 2.0]))
    multi.update("ETH", np.array([3.0, 4.0]))
    
    assert "BTC" in multi.symbols
    assert "ETH" in multi.symbols
    
    btc_norm = multi.get("BTC")
    assert btc_norm.count == 1
    
    multi.save_states(tmp_path)
    
    multi2 = MultiSymbolWelfordNormalizer(2)
    loaded = multi2.load_states(tmp_path)
    assert loaded == 2
    assert "BTC" in multi2.symbols
    assert multi2.get("BTC").count == 1


def test_welford_normalizer_load_state_dim_mismatch_and_missing_dir(tmp_path):
    norm = WelfordNormalizer(2)
    mismatched = tmp_path / "mismatched.npz"
    with open(mismatched, "wb") as handle:
        np.savez(
            handle,
            count=np.asarray([1], dtype=np.int64),
            mean=np.asarray([1.0, 2.0, 3.0], dtype=np.float32),
            m2=np.asarray([0.0, 0.0, 0.0], dtype=np.float32),
            dim=np.asarray([3], dtype=np.int64),
            eps=np.asarray([1e-8], dtype=np.float32),
        )
    with pytest.raises(ValueError, match="dim mismatch"):
        norm.load_state(mismatched)

    multi = MultiSymbolWelfordNormalizer(2)
    assert multi.load_states(tmp_path / "missing-dir") == 0


def test_multi_symbol_normalizer_skips_false_load_state(tmp_path, monkeypatch):
    states_dir = tmp_path / "states"
    states_dir.mkdir()
    (states_dir / "normalizer_BTC.npz").touch()

    def _false_load_state(self, path):  # pragma: no cover - exercised via branch test
        return False

    monkeypatch.setattr(WelfordNormalizer, "load_state", _false_load_state)

    multi = MultiSymbolWelfordNormalizer(2)
    assert multi.load_states(states_dir) == 0
    assert multi.symbols == []
