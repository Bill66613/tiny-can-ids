"""Tests for TFLite export and C/C++ code generation."""

import textwrap
from pathlib import Path

import numpy as np
import pytest
from sklearn.datasets import make_classification

from can_ids.models.classifiers import (
    TinyNeuralNetwork,
    train_logistic_regression,
    train_decision_tree,
)
from can_ids.models.compress import (
    ModelQuantizer,
    quantize_logistic_regression,
    export_decision_tree_structure,
)
from can_ids.deploy.c_export import (
    export_weights_to_c_header,
    generate_inference_c_code,
    export_lr_to_c_header,
    generate_lr_inference_c_code,
    export_dt_to_c_header,
    generate_dt_inference_c_code,
    export_model_to_c,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tiny_dataset():
    X, y = make_classification(
        n_samples=200,
        n_features=15,
        n_informative=8,
        random_state=0,
    )
    return X.astype(np.float32), y.astype(np.int32)


@pytest.fixture(scope="module")
def trained_tnn(tiny_dataset):
    X, y = tiny_dataset
    tnn = TinyNeuralNetwork(input_dim=X.shape[1], hidden_units=(16, 8))
    tnn.fit(X, y, epochs=5, verbose=0)
    return tnn


@pytest.fixture(scope="module")
def quantizer(trained_tnn):
    q = ModelQuantizer(model=trained_tnn, bits=8)
    q.quantize()
    return q


# ---------------------------------------------------------------------------
# C header export
# ---------------------------------------------------------------------------


def test_c_header_created(tmp_path, quantizer):
    out = export_weights_to_c_header(quantizer, tmp_path / "weights")
    assert out.exists()
    assert out.suffix == ".h"


def test_c_header_include_guard(tmp_path, quantizer):
    out = export_weights_to_c_header(
        quantizer, tmp_path / "weights2", model_name="my_ids"
    )
    content = out.read_text()
    assert "#ifndef MY_IDS_WEIGHTS_H" in content
    assert "#define MY_IDS_WEIGHTS_H" in content
    assert "#endif" in content


def test_c_header_contains_arrays(tmp_path, quantizer):
    out = export_weights_to_c_header(quantizer, tmp_path / "weights3")
    content = out.read_text()
    assert "int8_t" in content
    assert "static const" in content


def test_c_header_scale_defines(tmp_path, quantizer):
    out = export_weights_to_c_header(quantizer, tmp_path / "weights4")
    content = out.read_text()
    assert "_KERNEL_SCALE" in content
    assert "_BIAS_SCALE" in content


# ---------------------------------------------------------------------------
# C inference code generation
# ---------------------------------------------------------------------------


def test_c_inference_created(tmp_path, quantizer):
    out = generate_inference_c_code(quantizer, tmp_path / "inference")
    assert out.exists()
    assert out.suffix == ".c"


def test_c_inference_function_signature(tmp_path, quantizer):
    out = generate_inference_c_code(quantizer, tmp_path / "inference2")
    content = out.read_text()
    assert "tiny_ids_predict" in content


def test_c_inference_includes_header(tmp_path, quantizer):
    out = generate_inference_c_code(quantizer, tmp_path / "inference3")
    content = out.read_text()
    assert '#include "tiny_ids_weights.h"' in content


def test_c_inference_contains_relu(tmp_path, quantizer):
    out = generate_inference_c_code(quantizer, tmp_path / "inference4")
    content = out.read_text()
    assert "_relu" in content or "relu" in content.lower()


def test_c_inference_contains_sigmoid(tmp_path, quantizer):
    out = generate_inference_c_code(quantizer, tmp_path / "inference5")
    content = out.read_text()
    assert "_sigmoid" in content or "sigmoid" in content.lower()


# ---------------------------------------------------------------------------
# TFLite export
# ---------------------------------------------------------------------------


def test_tflite_export_returns_bytes(tiny_dataset, trained_tnn):
    pytest.importorskip("tensorflow")
    from can_ids.models.export import export_to_tflite

    X, _ = tiny_dataset
    tflite_bytes = export_to_tflite(trained_tnn, X[:50])
    assert isinstance(tflite_bytes, bytes)
    assert len(tflite_bytes) > 0


def test_tflite_export_size_reasonable(tiny_dataset, trained_tnn):
    pytest.importorskip("tensorflow")
    from can_ids.models.export import export_to_tflite

    X, _ = tiny_dataset
    tflite_bytes = export_to_tflite(trained_tnn, X[:50])
    # A tiny model should be under 100 KB
    assert len(tflite_bytes) < 100 * 1024


def test_tflite_save_and_load(tmp_path, tiny_dataset, trained_tnn):
    pytest.importorskip("tensorflow")
    from can_ids.models.export import (
        export_to_tflite,
        save_tflite_model,
        load_tflite_model,
    )

    X, _ = tiny_dataset
    tflite_bytes = export_to_tflite(trained_tnn, X[:50])
    path = save_tflite_model(tflite_bytes, tmp_path / "model")
    assert path.exists()

    loaded = load_tflite_model(path)
    assert loaded == tflite_bytes


def test_tflite_inference_shape(tiny_dataset, trained_tnn):
    pytest.importorskip("tensorflow")
    from can_ids.models.export import export_to_tflite, run_tflite_inference

    X, y = tiny_dataset
    tflite_bytes = export_to_tflite(trained_tnn, X[:50])
    preds = run_tflite_inference(tflite_bytes, X[:10])
    assert preds.shape == (10,)
    assert set(np.unique(preds)).issubset({0, 1})


# ---------------------------------------------------------------------------
# LR C export – fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def trained_lr(tiny_dataset):
    X, y = tiny_dataset
    return train_logistic_regression(X, y)


@pytest.fixture(scope="module")
def quantized_lr(trained_lr):
    return quantize_logistic_regression(trained_lr, bits=8)


# ---------------------------------------------------------------------------
# LR C header tests
# ---------------------------------------------------------------------------


def test_lr_c_header_created(tmp_path, quantized_lr):
    out = export_lr_to_c_header(quantized_lr, tmp_path / "lr_weights")
    assert out.exists()
    assert out.suffix == ".h"


def test_lr_c_header_contains_coef_array(tmp_path, quantized_lr):
    out = export_lr_to_c_header(quantized_lr, tmp_path / "lr_weights2")
    content = out.read_text()
    assert "int8_t" in content
    assert "_coef" in content


def test_lr_c_header_scale_defines(tmp_path, quantized_lr):
    out = export_lr_to_c_header(quantized_lr, tmp_path / "lr_weights3")
    content = out.read_text()
    assert "COEF_SCALE" in content
    assert "INTERCEPT_SCALE" in content


# ---------------------------------------------------------------------------
# LR C inference tests
# ---------------------------------------------------------------------------


def test_lr_c_inference_created(tmp_path, quantized_lr):
    out = generate_lr_inference_c_code(quantized_lr, tmp_path / "lr_inference")
    assert out.exists()
    assert out.suffix == ".c"


def test_lr_c_inference_function_signature(tmp_path, quantized_lr):
    out = generate_lr_inference_c_code(quantized_lr, tmp_path / "lr_inference2")
    content = out.read_text()
    assert "tiny_ids_lr_predict" in content


def test_lr_c_inference_dot_product(tmp_path, quantized_lr):
    out = generate_lr_inference_c_code(quantized_lr, tmp_path / "lr_inference3")
    content = out.read_text()
    # Should contain a loop computing the dot product
    assert "for" in content
    assert "_coef[" in content


# ---------------------------------------------------------------------------
# DT C export – fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def trained_dt(tiny_dataset):
    X, y = tiny_dataset
    return train_decision_tree(X, y, max_depth=5)


@pytest.fixture(scope="module")
def exported_dt(trained_dt):
    return export_decision_tree_structure(trained_dt)


# ---------------------------------------------------------------------------
# DT C header tests
# ---------------------------------------------------------------------------


def test_dt_c_header_created(tmp_path, exported_dt):
    out = export_dt_to_c_header(exported_dt, tmp_path / "dt_weights")
    assert out.exists()
    assert out.suffix == ".h"


def test_dt_c_header_contains_arrays(tmp_path, exported_dt):
    out = export_dt_to_c_header(exported_dt, tmp_path / "dt_weights2")
    content = out.read_text()
    assert "feature_index" in content
    assert "threshold" in content
    assert "children_left" in content
    assert "children_right" in content
    assert "leaf_class" in content


def test_dt_c_header_node_count(tmp_path, exported_dt):
    out = export_dt_to_c_header(exported_dt, tmp_path / "dt_weights3")
    content = out.read_text()
    assert "N_NODES" in content


# ---------------------------------------------------------------------------
# DT C inference tests
# ---------------------------------------------------------------------------


def test_dt_c_inference_created(tmp_path, exported_dt):
    out = generate_dt_inference_c_code(exported_dt, tmp_path / "dt_inference")
    assert out.exists()
    assert out.suffix == ".c"


def test_dt_c_inference_traversal_loop(tmp_path, exported_dt):
    out = generate_dt_inference_c_code(exported_dt, tmp_path / "dt_inference2")
    content = out.read_text()
    assert "while" in content
    assert "children_left" in content


def test_dt_c_inference_function_signature(tmp_path, exported_dt):
    out = generate_dt_inference_c_code(exported_dt, tmp_path / "dt_inference3")
    content = out.read_text()
    assert "tiny_ids_dt_predict" in content


# ---------------------------------------------------------------------------
# Unified export dispatch
# ---------------------------------------------------------------------------


def test_unified_export_tnn(tmp_path, trained_tnn):
    header, source = export_model_to_c(trained_tnn, "tnn", tmp_path)
    assert header.exists() and header.suffix == ".h"
    assert source.exists() and source.suffix == ".c"


def test_unified_export_lr(tmp_path, trained_lr):
    header, source = export_model_to_c(trained_lr, "lr", tmp_path)
    assert header.exists() and header.suffix == ".h"
    assert source.exists() and source.suffix == ".c"


def test_unified_export_dt(tmp_path, trained_dt):
    header, source = export_model_to_c(trained_dt, "dt", tmp_path)
    assert header.exists() and header.suffix == ".h"
    assert source.exists() and source.suffix == ".c"


def test_unified_export_invalid_type(tmp_path, trained_tnn):
    with pytest.raises(ValueError, match="Unknown model_type"):
        export_model_to_c(trained_tnn, "invalid", tmp_path)
