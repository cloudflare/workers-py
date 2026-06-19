import numpy as np


def test_numpy_random_default_rng_with_seed():
    rng = np.random.default_rng(42)
    val = rng.random()
    assert 0.0 <= val < 1.0


def test_numpy_random_default_rng_without_seed():
    rng = np.random.default_rng()
    val = rng.random()
    assert 0.0 <= val < 1.0


def test_numpy_random_seed_produces_deterministic_results():
    np.random.seed(42)
    a = np.random.random(5)
    np.random.seed(42)
    b = np.random.random(5)
    np.testing.assert_array_equal(a, b)
