import numpy as np


def test_welford_normalizer_fit_then_normalize(tmp_path):
    from logic.ingest.normalizer import WelfordNormalizer

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
    from logic.ingest.normalizer import WelfordNormalizer

    d = 3
    norm = WelfordNormalizer(dim=d, eps=1e-8)
    x = np.array([1000.0, 0.5, -2.0], dtype=np.float32)
    norm.update(x)

    z = norm.normalize(x)
    assert z.shape == (d,)
    assert z.dtype == np.float32
    assert np.all(np.isfinite(z))

