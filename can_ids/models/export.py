"""TensorFlow Lite export utilities.

Converts trained models to ``.tflite`` format for embedded inference on
resource-constrained devices such as MCUs and TCUs.

Supports:

* **Full-integer quantization** of :class:`~can_ids.models.classifiers.TinyNeuralNetwork`
  Keras models using a representative dataset.
* **ONNX-to-TFLite** (not implemented – placeholder for future work).
* Saving and loading ``.tflite`` flatbuffer files.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


def export_to_tflite(
    model: Any,
    representative_data: np.ndarray,
    quantize: bool = True,
    input_type: str = "float32",
    output_type: str = "float32",
) -> bytes:
    """Convert a :class:`~can_ids.models.classifiers.TinyNeuralNetwork` to TFLite.

    Args:
        model: A trained :class:`~can_ids.models.classifiers.TinyNeuralNetwork`
            instance (must have a ``keras_model`` attribute).
        representative_data: A sample of the training data used for
            full-integer quantization calibration.  Shape
            ``(n_samples, n_features)``.
        quantize: If *True*, apply full-integer post-training quantization.
        input_type: Desired input tensor type after quantization.
            One of ``"float32"``, ``"int8"``, ``"uint8"``.
        output_type: Desired output tensor type after quantization.

    Returns:
        The serialized TFLite flatbuffer as a :class:`bytes` object.

    Raises:
        ImportError: If TensorFlow is not installed.
        AttributeError: If *model* does not expose a ``keras_model`` attribute.
    """
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise ImportError(
            "TensorFlow is required for TFLite export. "
            "Install it with: pip install tensorflow"
        ) from exc

    keras_model = model.keras_model

    # Save the Keras model to a temporary directory and convert from there
    with tempfile.TemporaryDirectory() as tmp_dir:
        saved_model_path = Path(tmp_dir) / "saved_model"
        keras_model.export(str(saved_model_path))

        converter = tf.lite.TFLiteConverter.from_saved_model(str(saved_model_path))

        if quantize:
            converter.optimizations = [tf.lite.Optimize.DEFAULT]

            rep_data = representative_data.astype(np.float32)

            def _representative_dataset() -> Any:
                for i in range(min(100, len(rep_data))):
                    yield [rep_data[i : i + 1]]

            converter.representative_dataset = _representative_dataset

            _dtype_map = {
                "int8": tf.int8,
                "uint8": tf.uint8,
                "float32": tf.float32,
            }
            converter.inference_input_type = _dtype_map.get(input_type, tf.float32)
            converter.inference_output_type = _dtype_map.get(
                output_type, tf.float32
            )

        tflite_model: bytes = converter.convert()

    size_kb = len(tflite_model) / 1024
    logger.info("TFLite model size: %.1f KB", size_kb)
    return tflite_model


def save_tflite_model(tflite_model: bytes, path: str | Path) -> Path:
    """Save a TFLite flatbuffer to *path*.

    Args:
        tflite_model: Serialized TFLite model (bytes).
        path: Destination file path.  The ``.tflite`` extension will be
            appended if not already present.

    Returns:
        The resolved :class:`~pathlib.Path` of the saved file.
    """
    path = Path(path)
    if path.suffix != ".tflite":
        path = path.with_suffix(".tflite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tflite_model)
    logger.info("Saved TFLite model to %s (%.1f KB)", path, len(tflite_model) / 1024)
    return path


def load_tflite_model(path: str | Path) -> bytes:
    """Load a TFLite flatbuffer from *path*.

    Args:
        path: Path to a ``.tflite`` file.

    Returns:
        Raw bytes of the TFLite model.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"TFLite model not found: {path}")
    return path.read_bytes()


def run_tflite_inference(
    tflite_model: bytes,
    X: np.ndarray,
    threshold: float = 0.5,
) -> np.ndarray:
    """Run inference using a TFLite interpreter.

    Useful for validating the exported model on the host before deploying
    it to an embedded target.

    Args:
        tflite_model: Serialized TFLite model (bytes).
        X: Feature matrix of shape ``(n_samples, n_features)``.
        threshold: Decision threshold applied to the sigmoid output.

    Returns:
        Integer array of predicted labels.

    Raises:
        ImportError: If TensorFlow is not installed.
    """
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise ImportError(
            "TensorFlow is required for TFLite inference. "
            "Install it with: pip install tensorflow"
        ) from exc

    interpreter = tf.lite.Interpreter(model_content=tflite_model)
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    preds = []
    for i in range(len(X)):
        sample = X[i : i + 1].astype(np.float32)
        interpreter.set_tensor(input_details[0]["index"], sample)
        interpreter.invoke()
        output = interpreter.get_tensor(output_details[0]["index"])
        preds.append(float(output.ravel()[0]))

    probs = np.array(preds, dtype=np.float32)
    return (probs >= threshold).astype(int)
