"""Tests for TFLite export and C/C++ code generation."""

import textwrap
from pathlib import Path

import numpy as np
import pytest
from sklearn.datasets import make_classification

from can_ids.models.classifiers import TinyNeuralNetwork
from can_ids.models.compress import ModelQuantizer
from can_ids.deploy.c_export import (
    export_weights_to_c_header,
    generate_inference_c_code,
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
