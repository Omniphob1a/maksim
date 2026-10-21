import numpy as np
import pytest

from netgaf.transforms import FixedScaler, gaf


@pytest.mark.parametrize("method", ["gasf", "gadf"])
def test_gaf_matches_angular_definition(method):
    values = np.random.default_rng(4).random((2, 16, 3)).astype(np.float32)
    angles = np.arccos(values.transpose(0, 2, 1))
    expected = (
        np.cos(angles[..., :, None] + angles[..., None, :])
        if method == "gasf"
        else np.sin(angles[..., :, None] - angles[..., None, :])
    )
    np.testing.assert_allclose(gaf(values, method), expected, atol=4e-7)


def test_gasf_diagonal_recovers_the_time_series():
    x = np.random.default_rng(5).random((32, 3))
    image = gaf(x)
    np.testing.assert_allclose(image, image.swapaxes(-1, -2), atol=1e-7)
    restored = np.sqrt(np.maximum(0, (np.diagonal(image, axis1=-2, axis2=-1) + 1) / 2))
    np.testing.assert_allclose(restored.T, x, atol=2e-12)


def test_float32_diagonal_recovery_respects_rounding_error_bound():
    x = np.linspace(0, 1, 1000, dtype=np.float32).reshape(-1, 1)
    image = gaf(x)
    restored = np.sqrt(np.maximum(0, (np.diagonal(image, axis1=-2, axis2=-1) + 1) / 2)).T
    # sqrt is ill-conditioned at zero: O(sqrt(epsilon)), rather than O(epsilon).
    assert np.max(np.abs(restored - x)) <= np.sqrt(2 * np.finfo(np.float32).eps)


def test_gadf_is_antisymmetric():
    image = gaf(np.random.default_rng(3).random((16, 3)), "gadf")
    np.testing.assert_allclose(image, -image.swapaxes(-1, -2), atol=1e-7)
    np.testing.assert_array_equal(np.diagonal(image, axis1=-2, axis2=-1), 0)


def test_scaler_uses_training_bounds_instead_of_window_bounds():
    training = np.array([[1, 10, 2], [2, 20, 2], [3, 30, 2]])
    scaler = FixedScaler.fit(training)
    normal, *_ = scaler.transform(training)
    changed, low, high, excess = scaler.transform(training * 10)
    assert not np.array_equal(gaf(normal), gaf(changed))
    assert high.tolist() == [3, 3, 3]
    assert low.tolist() == [0, 0, 0]
    assert (excess > 0).all()
    np.testing.assert_array_equal(scaler.upper, [3, 30, 2])


@pytest.mark.parametrize("values", [np.array([[np.nan] * 3]), np.array([[-1, 0, 1]])])
def test_invalid_training_values_rejected(values):
    with pytest.raises(ValueError):
        FixedScaler.fit(values)


def test_gaf_rejects_missing_normalization():
    with pytest.raises(ValueError):
        gaf(np.full((32, 3), 2))
