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
    quantize_logistic_regression,
    export_decision_tree_structure,
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


# ---------------------------------------------------------------------------
# Class imbalance handling
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def imbalanced_dataset():
    """Dataset with 90/10 class split to test balanced weights."""
    X, y = make_classification(
        n_samples=400,
        n_features=20,
        n_informative=10,
        n_redundant=5,
        weights=[0.9, 0.1],
        random_state=42,
    )
    return X.astype(np.float32), y.astype(np.int32)


def test_logistic_regression_balanced_weights(imbalanced_dataset):
    X, y = imbalanced_dataset
    model = train_logistic_regression(X, y)
    preds = model.predict(X)
    # With a 90/10 split, random guessing gives ~0.10 minority recall.
    # Require a modest improvement over random while avoiding flaky thresholds.
    minority_mask = y == 1
    minority_recall = (preds[minority_mask] == 1).mean()
    assert minority_recall > 0.15, f"Minority recall {minority_recall:.2f} too low"


def test_decision_tree_balanced_weights(imbalanced_dataset):
    X, y = imbalanced_dataset
    model = train_decision_tree(X, y, max_depth=5)
    preds = model.predict(X)
    # Same rationale as logistic regression: just above random baseline (0.10).
    minority_mask = y == 1
    minority_recall = (preds[minority_mask] == 1).mean()
    assert minority_recall > 0.15, f"Minority recall {minority_recall:.2f} too low"


def test_tnn_balanced_classes(imbalanced_dataset):
    X, y = imbalanced_dataset
    tnn = TinyNeuralNetwork(input_dim=X.shape[1], hidden_units=(16, 8))
    tnn.fit(X, y, epochs=10, verbose=0, balance_classes=True)
    preds = tnn.predict(X)
    # Should not predict all-majority-class
    assert len(np.unique(preds)) > 1, "TNN predicted only one class"


# ---------------------------------------------------------------------------
# LR quantization
# ---------------------------------------------------------------------------


def test_quantize_lr_shape(binary_dataset):
    X, y = binary_dataset
    model = train_logistic_regression(X, y)
    qlr = quantize_logistic_regression(model, bits=8)
    assert qlr.coef_q.shape == model.coef_.shape
    assert qlr.intercept_q.shape == model.intercept_.shape


def test_quantize_lr_range(binary_dataset):
    X, y = binary_dataset
    model = train_logistic_regression(X, y)
    qlr = quantize_logistic_regression(model, bits=8)
    assert qlr.coef_q.min() >= -127
    assert qlr.coef_q.max() <= 127


def test_quantize_lr_memory_footprint(binary_dataset):
    X, y = binary_dataset
    model = train_logistic_regression(X, y)
    qlr = quantize_logistic_regression(model, bits=8)
    fp = qlr.memory_footprint_bytes()
    assert fp > 0
    # INT8 should be smaller than float32 original
    float32_size = (model.coef_.size + model.intercept_.size) * 4
    assert fp < float32_size


# ---------------------------------------------------------------------------
# Decision tree structure export
# ---------------------------------------------------------------------------


def test_export_dt_structure_node_count(binary_dataset):
    X, y = binary_dataset
    model = train_decision_tree(X, y, max_depth=5)
    edt = export_decision_tree_structure(model)
    assert edt.n_nodes == model.tree_.node_count


def test_export_dt_structure_leaf_classes(binary_dataset):
    X, y = binary_dataset
    model = train_decision_tree(X, y, max_depth=5)
    edt = export_decision_tree_structure(model)
    # Leaf classes should be valid class indices
    leaf_mask = edt.leaf_class >= 0
    assert leaf_mask.any(), "No leaf nodes found"
    assert set(edt.leaf_class[leaf_mask].tolist()).issubset(set(range(edt.n_classes)))


def test_export_dt_structure_memory(binary_dataset):
    X, y = binary_dataset
    model = train_decision_tree(X, y, max_depth=5)
    edt = export_decision_tree_structure(model)
    fp = edt.memory_footprint_bytes()
    assert fp > 0
    # With max_depth=5, should be well under 2KB
    assert fp < 2048
