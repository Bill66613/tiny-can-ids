"""Tests for can_ids.features.engineer."""

import numpy as np
import pytest

from can_ids.data.loader import generate_synthetic_can_data, preprocess_can_data
from can_ids.features.engineer import (
    extract_id_frequency_features,
    extract_timing_features,
    extract_payload_features,
    extract_rate_and_novelty_features,
    build_feature_matrix,
)


@pytest.fixture(scope="module")
def preprocessed_df():
    raw = generate_synthetic_can_data(n_normal=500, n_attack=100, seed=42)
    return preprocess_can_data(raw)


def test_id_frequency_shape(preprocessed_df):
    feats = extract_id_frequency_features(preprocessed_df, window_size=50)
    n_windows = len(preprocessed_df) // 50
    assert feats.shape == (n_windows, 22), feats.shape


def test_id_frequency_dtype(preprocessed_df):
    feats = extract_id_frequency_features(preprocessed_df, window_size=50)
    assert feats.dtype == np.float32


def test_id_frequency_normalized(preprocessed_df):
    feats = extract_id_frequency_features(preprocessed_df, window_size=50)
    # First 21 columns (bins + other) should sum to ≤ 1 per row
    assert (feats[:, :21].sum(axis=1) <= 1.0 + 1e-5).all()


def test_timing_features_shape(preprocessed_df):
    feats = extract_timing_features(preprocessed_df, window_size=50)
    n_windows = len(preprocessed_df) // 50
    assert feats.shape == (n_windows, 4)


def test_timing_features_non_negative(preprocessed_df):
    feats = extract_timing_features(preprocessed_df, window_size=50)
    # min and max inter-arrival should be >= 0
    assert (feats[:, 2] >= 0).all()  # min
    assert (feats[:, 3] >= feats[:, 2]).all()  # max >= min


def test_payload_features_shape(preprocessed_df):
    feats = extract_payload_features(preprocessed_df, window_size=50)
    n_windows = len(preprocessed_df) // 50
    assert feats.shape == (n_windows, 17)


def test_payload_features_dtype(preprocessed_df):
    feats = extract_payload_features(preprocessed_df, window_size=50)
    assert feats.dtype == np.float32


def test_build_feature_matrix_shapes(preprocessed_df):
    X, y = build_feature_matrix(preprocessed_df, window_size=50)
    n_windows = len(preprocessed_df) // 50
    assert X.shape[0] == n_windows
    assert y.shape[0] == n_windows
    # Total features: 22 (id freq) + 4 (timing) + 17 (payload) + 3 (rate & novelty)
    assert X.shape[1] == 46, X.shape[1]


def test_build_feature_matrix_labels_binary(preprocessed_df):
    _, y = build_feature_matrix(preprocessed_df, window_size=50)
    assert set(np.unique(y)).issubset({0, 1})


def test_build_feature_matrix_no_nan(preprocessed_df):
    X, y = build_feature_matrix(preprocessed_df, window_size=50)
    assert not np.isnan(X).any()
    assert not np.isnan(y.astype(float)).any()


def test_build_feature_matrix_has_attack_windows(preprocessed_df):
    _, y = build_feature_matrix(preprocessed_df, window_size=50)
    assert y.sum() > 0, "Expected at least one attack window"


# ---------------------------------------------------------------------------
# Rate and novelty features
# ---------------------------------------------------------------------------


def test_rate_novelty_features_shape(preprocessed_df):
    feats = extract_rate_and_novelty_features(preprocessed_df, window_size=50)
    n_windows = len(preprocessed_df) // 50
    assert feats.shape == (n_windows, 3), feats.shape


def test_rate_novelty_features_dtype(preprocessed_df):
    feats = extract_rate_and_novelty_features(preprocessed_df, window_size=50)
    assert feats.dtype == np.float32


def test_rate_novelty_features_non_negative(preprocessed_df):
    feats = extract_rate_and_novelty_features(preprocessed_df, window_size=50)
    assert (feats >= 0).all()


def test_rate_novelty_message_rate_positive(preprocessed_df):
    feats = extract_rate_and_novelty_features(preprocessed_df, window_size=50)
    # Message rate should be > 0 for all windows with valid timestamps
    assert (feats[:, 0] > 0).all()
