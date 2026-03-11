"""Tests for can_ids.models (classifiers and compression)."""

import numpy as np
import pytest
from sklearn.datasets import make_classification

from can_ids.models.classifiers import (
    train_logistic_regression,
    train_decision_tree,
    TinyNeuralNetwork,
)
from can_ids.models.compress import (
    quantize_weights,
    ModelQuantizer,
    prune_decision_tree,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def binary_dataset():
    X, y = make_classification(
        n_samples=300,
        n_features=20,
        n_informative=10,
        n_redundant=5,
        random_state=42,
    )
    return X.astype(np.float32), y.astype(np.int32)


@pytest.fixture(scope="module")
def trained_tnn(binary_dataset):
    X, y = binary_dataset
    tnn = TinyNeuralNetwork(input_dim=X.shape[1], hidden_units=(16, 8))
    tnn.fit(X, y, epochs=5, verbose=0)
    return tnn


# ---------------------------------------------------------------------------
# Logistic Regression
# ---------------------------------------------------------------------------

def test_logistic_regression_trains(binary_dataset):
    X, y = binary_dataset
    model = train_logistic_regression(X, y)
    assert hasattr(model, "coef_")


def test_logistic_regression_predict_shape(binary_dataset):
    X, y = binary_dataset
    model = train_logistic_regression(X, y)
    preds = model.predict(X)
    assert preds.shape == (len(X),)


def test_logistic_regression_accuracy(binary_dataset):
    X, y = binary_dataset
    model = train_logistic_regression(X, y)
    acc = (model.predict(X) == y).mean()
    assert acc > 0.5, f"Accuracy {acc:.2f} below chance level"


# ---------------------------------------------------------------------------
# Decision Tree
# ---------------------------------------------------------------------------

def test_decision_tree_trains(binary_dataset):
    X, y = binary_dataset
    model = train_decision_tree(X, y, max_depth=5)
    assert hasattr(model, "tree_")


def test_decision_tree_depth_limit(binary_dataset):
    X, y = binary_dataset
    model = train_decision_tree(X, y, max_depth=3)
    assert model.get_depth() <= 3


def test_decision_tree_predict_shape(binary_dataset):
    X, y = binary_dataset
    model = train_decision_tree(X, y)
    preds = model.predict(X)
    assert preds.shape == (len(X),)


def test_decision_tree_pruning(binary_dataset):
    X, y = binary_dataset
    original = train_decision_tree(X, y, max_depth=10)
    pruned = prune_decision_tree(original, X, y, ccp_alpha=0.02)
    assert pruned.get_n_leaves() <= original.get_n_leaves()


# ---------------------------------------------------------------------------
# Tiny Neural Network
# ---------------------------------------------------------------------------

def test_tnn_predict_shape(binary_dataset, trained_tnn):
    X, _ = binary_dataset
    preds = trained_tnn.predict(X)
    assert preds.shape == (len(X),)


def test_tnn_predict_binary(binary_dataset, trained_tnn):
    X, _ = binary_dataset
    preds = trained_tnn.predict(X)
    assert set(np.unique(preds)).issubset({0, 1})


def test_tnn_predict_proba_range(binary_dataset, trained_tnn):
    X, _ = binary_dataset
    probs = trained_tnn.predict_proba(X)
    assert probs.min() >= 0.0
    assert probs.max() <= 1.0


def test_tnn_keras_model_accessible(trained_tnn):
    import tensorflow as tf
    assert isinstance(trained_tnn.keras_model, tf.keras.Model)


# ---------------------------------------------------------------------------
# Weight quantization
# ---------------------------------------------------------------------------

def test_quantize_weights_shape():
    w = np.random.randn(10, 5).astype(np.float32)
    q, scale, zp = quantize_weights(w, bits=8)
    assert q.shape == w.shape


def test_quantize_weights_range():
    w = np.random.randn(10, 5).astype(np.float32)
    q, scale, zp = quantize_weights(w, bits=8)
    assert q.min() >= -(2**7 - 1)
    assert q.max() <= 2**7 - 1


def test_quantize_weights_scale_positive():
    w = np.random.randn(10, 5).astype(np.float32)
    _, scale, _ = quantize_weights(w, bits=8)
    assert scale > 0


def test_quantize_all_zeros():
    w = np.zeros((4, 4), dtype=np.float32)
    q, scale, zp = quantize_weights(w, bits=8)
    assert (q == 0).all()


def test_quantize_invalid_bits():
    w = np.ones((3, 3), dtype=np.float32)
    with pytest.raises(ValueError):
        quantize_weights(w, bits=1)


# ---------------------------------------------------------------------------
# ModelQuantizer
# ---------------------------------------------------------------------------

def test_model_quantizer_layers(trained_tnn):
    quantizer = ModelQuantizer(model=trained_tnn, bits=8)
    quantizer.quantize()
    assert len(quantizer.quantized_layers) > 0


def test_model_quantizer_footprint(trained_tnn):
    quantizer = ModelQuantizer(model=trained_tnn, bits=8)
    quantizer.quantize()
    fp = quantizer.memory_footprint_bytes()
    assert fp > 0


def test_model_quantizer_footprint_smaller_than_float(trained_tnn):
    quantizer = ModelQuantizer(model=trained_tnn, bits=8)
    quantizer.quantize()
    fp_int8 = quantizer.memory_footprint_bytes()
    # Original float32 weights should be 4x larger
    total_params = sum(
        ql.kernel_q.size + ql.bias_q.size for ql in quantizer.quantized_layers
    )
    fp_float32 = total_params * 4
    assert fp_int8 < fp_float32
