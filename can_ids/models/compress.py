"""Model compression utilities: weight quantization and tree pruning.

Provides:

* :func:`quantize_weights` – INT8 symmetric quantization of a numpy weight
  array.
* :class:`ModelQuantizer` – quantizes all dense-layer weights of a
  :class:`~can_ids.models.classifiers.TinyNeuralNetwork` Keras model.
* :func:`prune_decision_tree` – rebuilds a decision tree with a stricter
  depth/leaf-count constraint to reduce its size.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from sklearn.tree import DecisionTreeClassifier

logger = logging.getLogger(__name__)


def quantize_weights(
    weights: np.ndarray, bits: int = 8
) -> tuple[np.ndarray, float, int]:
    """Symmetric min-max INT-*bits* quantization of a weight array.

    The scale factor and zero-point follow the TensorFlow Lite
    per-tensor symmetric quantization convention:

    ``q = round(w / scale)``  where  ``scale = max(|w|) / (2^(bits-1) - 1)``

    Args:
        weights: Floating-point weight array.
        bits: Target bit-width (default 8).

    Returns:
        Tuple ``(quantized_int_array, scale, zero_point)``.

    Raises:
        ValueError: If *bits* is not in [2, 32].
    """
    if not 2 <= bits <= 32:
        raise ValueError(f"bits must be in [2, 32], got {bits}")

    max_val = np.max(np.abs(weights))
    if max_val == 0.0:
        quantized = np.zeros_like(weights, dtype=np.int8 if bits == 8 else np.int32)
        return quantized, 1.0, 0

    qmax = 2 ** (bits - 1) - 1
    scale = float(max_val / qmax)
    quantized = np.round(weights / scale).clip(-qmax, qmax).astype(np.int32)
    zero_point = 0
    logger.debug(
        "Quantized weights %s → int%d, scale=%.6f", weights.shape, bits, scale
    )
    return quantized, scale, zero_point


@dataclass
class QuantizedLayer:
    """Holds quantized parameters for a single dense layer."""

    name: str
    kernel_q: np.ndarray
    kernel_scale: float
    bias_q: np.ndarray
    bias_scale: float
    bits: int


@dataclass
class ModelQuantizer:
    """Post-training INT8 quantization of a :class:`TinyNeuralNetwork`.

    Example::

        quantizer = ModelQuantizer(tiny_nn, bits=8)
        quantizer.quantize()
        print(quantizer.memory_footprint_bytes())

    Args:
        model: A :class:`~can_ids.models.classifiers.TinyNeuralNetwork`
            instance.
        bits: Target bit-width for quantization.
    """

    model: Any
    bits: int = 8
    quantized_layers: list[QuantizedLayer] = field(default_factory=list, init=False)

    def quantize(self) -> "ModelQuantizer":
        """Quantize all dense-layer weights in the Keras model.

        Returns:
            ``self`` for method chaining.
        """
        self.quantized_layers.clear()
        keras_model = self.model.keras_model
        for layer in keras_model.layers:
            if not layer.get_weights():
                continue
            weights = layer.get_weights()
            if len(weights) < 2:
                continue
            kernel, bias = weights[0], weights[1]
            k_q, k_scale, _ = quantize_weights(kernel, self.bits)
            b_q, b_scale, _ = quantize_weights(bias, self.bits)
            self.quantized_layers.append(
                QuantizedLayer(
                    name=layer.name,
                    kernel_q=k_q,
                    kernel_scale=k_scale,
                    bias_q=b_q,
                    bias_scale=b_scale,
                    bits=self.bits,
                )
            )
            logger.debug("Quantized layer '%s'", layer.name)

        logger.info(
            "Quantized %d layers – estimated footprint: %d bytes",
            len(self.quantized_layers),
            self.memory_footprint_bytes(),
        )
        return self

    def memory_footprint_bytes(self) -> int:
        """Estimated model size in bytes after quantization."""
        total = 0
        for ql in self.quantized_layers:
            bytes_per_element = max(1, self.bits // 8)
            total += ql.kernel_q.size * bytes_per_element
            total += ql.bias_q.size * bytes_per_element
        return total


def prune_decision_tree(
    model: DecisionTreeClassifier,
    X_train: np.ndarray,
    y_train: np.ndarray,
    max_depth: Optional[int] = None,
    ccp_alpha: float = 0.01,
) -> DecisionTreeClassifier:
    """Prune a decision tree using cost-complexity pruning.

    Retrains the tree with a non-zero ``ccp_alpha`` (minimal cost-complexity
    pruning coefficient) to remove branches that do not improve accuracy
    enough to justify their complexity.

    Args:
        model: A fitted :class:`~sklearn.tree.DecisionTreeClassifier`.
        X_train: Training features used to find the optimal alpha.
        y_train: Training labels.
        max_depth: Optional maximum depth for the pruned tree.
        ccp_alpha: Cost-complexity pruning coefficient.  Higher values
            produce smaller trees.

    Returns:
        A new, pruned :class:`~sklearn.tree.DecisionTreeClassifier`.
    """
    params = model.get_params()
    params["ccp_alpha"] = ccp_alpha
    if max_depth is not None:
        params["max_depth"] = max_depth

    pruned = DecisionTreeClassifier(**params)
    pruned.fit(X_train, y_train)
    logger.info(
        "Pruned tree: depth=%d, leaves=%d (was %d leaves)",
        pruned.get_depth(),
        pruned.get_n_leaves(),
        model.get_n_leaves(),
    )
    return pruned
