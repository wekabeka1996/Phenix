import numpy as np


def test_welford_normalizer_fit_then_normalize(tmp_path):
    from apps.reference.domains.neocortex.logic.ingest.normalizer import WelfordNormalizer

    rng = np.random.default_rng(123)
    n = 5000
    d = 8
    x = (rng.normal(loc=10.0, scale=3.0, size=(n, d))).astype(np.float32)

    norm = WelfordNormalizer(dim=d, eps=1e-8)
    for i in range(n):
        norm.update(x[i])

    z = np.stack([norm.normalize(x[i]) for i in range(n)]).astype(np.float32)

    mean = z.mean(axis=0)
    std = z.std(axis=0, ddof=1)

    assert np.all(np.isfinite(z))
    assert np.all(np.abs(mean) < 0.05)
    assert np.all(np.abs(std - 1.0) < 0.05)

    state_path = tmp_path / "normalizer_state.npz"
    norm.save_state(state_path)

    norm2 = WelfordNormalizer(dim=d, eps=1e-8)
    assert norm2.load_state(state_path) is True

    z2 = np.stack([norm2.normalize(x[i]) for i in range(n)]).astype(np.float32)
    assert np.allclose(z, z2, atol=1e-6, rtol=1e-6)


def test_welford_normalizer_handles_count_one():
    from apps.reference.domains.neocortex.logic.ingest.normalizer import WelfordNormalizer

    d = 3
    norm = WelfordNormalizer(dim=d, eps=1e-8)
    x = np.array([1000.0, 0.5, -2.0], dtype=np.float32)
    norm.update(x)

    z = norm.normalize(x)
    assert z.shape == (d,)
    assert z.dtype == np.float32
    assert np.all(np.isfinite(z))


def test_multi_symbol_welford_normalizer_isolated_stats(tmp_path):
    from apps.reference.domains.neocortex.logic.ingest.normalizer import MultiSymbolWelfordNormalizer

    norm = MultiSymbolWelfordNormalizer(dim=2, eps=1e-8)

    # Symbol A centered near 0
    for _ in range(100):
        norm.update("BTCUSDT", np.array([0.0, 1.0], dtype=np.float32))
    # Symbol B centered far away
    for _ in range(100):
        norm.update("ETHUSDT", np.array([1000.0, 2000.0], dtype=np.float32))

    z_a = norm.normalize("BTCUSDT", np.array([0.0, 1.0], dtype=np.float32))
    z_b = norm.normalize("ETHUSDT", np.array([1000.0, 2000.0], dtype=np.float32))

    assert np.all(np.isfinite(z_a))
    assert np.all(np.isfinite(z_b))
    assert np.max(np.abs(z_a)) < 1e-3
    assert np.max(np.abs(z_b)) < 1e-3

    states_dir = tmp_path / "normalizer_states"
    saved = norm.save_states(states_dir)
    assert saved == 2

    norm2 = MultiSymbolWelfordNormalizer(dim=2, eps=1e-8)
    loaded = norm2.load_states(states_dir)
    assert loaded == 2

    z2_a = norm2.normalize("BTCUSDT", np.array([0.0, 1.0], dtype=np.float32))
    z2_b = norm2.normalize("ETHUSDT", np.array([1000.0, 2000.0], dtype=np.float32))
    assert np.allclose(z_a, z2_a, atol=1e-6, rtol=1e-6)
    assert np.allclose(z_b, z2_b, atol=1e-6, rtol=1e-6)


