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
    # Use int8 for 8-bit (TFLite-compatible), int32 for wider bit-widths
    dtype = np.int8 if bits == 8 else np.int32
    quantized = np.round(weights / scale).clip(-qmax, qmax).astype(dtype)
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


@dataclass
class QuantizedLR:
    """Holds INT8-quantized parameters for a logistic regression model.

    For binary classification ``coef_q`` has shape ``(1, n_features)`` and
    ``intercept_q`` has shape ``(1,)``.  For multi-class they expand to
    ``(n_classes, n_features)`` and ``(n_classes,)`` respectively.
    """

    coef_q: np.ndarray
    coef_scale: float
    intercept_q: np.ndarray
    intercept_scale: float
    n_features: int
    n_classes: int
    bits: int = 8

    def memory_footprint_bytes(self) -> int:
        """Estimated model size in bytes after quantization."""
        bpe = max(1, self.bits // 8)
        return (self.coef_q.size + self.intercept_q.size) * bpe


def quantize_logistic_regression(
    model: Any,
    bits: int = 8,
) -> QuantizedLR:
    """Quantize a fitted scikit-learn LogisticRegression model.

    Uses symmetric min-max quantization on the coefficient matrix and
    intercept vector, identical to the approach used for TNN dense layers.

    Args:
        model: A fitted :class:`~sklearn.linear_model.LogisticRegression`.
        bits: Target bit-width (default 8).

    Returns:
        A :class:`QuantizedLR` containing INT8 coefficients and scales.
    """
    coef = model.coef_.astype(np.float32)
    intercept = model.intercept_.astype(np.float32)
    coef_q, coef_scale, _ = quantize_weights(coef, bits)
    intercept_q, intercept_scale, _ = quantize_weights(intercept, bits)
    n_classes = coef.shape[0] if coef.shape[0] > 1 else 2
    qlr = QuantizedLR(
        coef_q=coef_q,
        coef_scale=coef_scale,
        intercept_q=intercept_q,
        intercept_scale=intercept_scale,
        n_features=coef.shape[1],
        n_classes=n_classes,
        bits=bits,
    )
    logger.info(
        "Quantized LR: coef %s, footprint %d bytes",
        coef_q.shape,
        qlr.memory_footprint_bytes(),
    )
    return qlr


@dataclass
class ExportedDecisionTree:
    """Array-based representation of a decision tree for C export.

    Stores parallel arrays that support a simple while-loop tree traversal
    in generated C code.  Internal nodes have ``children_left[i] != -1``;
    leaf nodes store the predicted class in ``leaf_class[i]``.
    """

    feature_index: np.ndarray
    threshold: np.ndarray
    children_left: np.ndarray
    children_right: np.ndarray
    leaf_class: np.ndarray
    n_nodes: int
    n_classes: int
    max_depth: int

    def memory_footprint_bytes(self) -> int:
        """Estimated C-side memory footprint in bytes.

        feature_index, children_left, children_right, leaf_class are int8
        (1 byte each), threshold is float32 (4 bytes).
        """
        return self.n_nodes * (1 + 4 + 1 + 1 + 1)  # 8 bytes per node


def export_decision_tree_structure(
    model: DecisionTreeClassifier,
) -> ExportedDecisionTree:
    """Extract a decision tree into parallel arrays for C export.

    Args:
        model: A fitted :class:`~sklearn.tree.DecisionTreeClassifier`.

    Returns:
        An :class:`ExportedDecisionTree` with arrays ready for C code
        generation.

    Raises:
        ValueError: If the tree has more than 127 nodes (does not fit in
            int8 index fields).
    """
    tree = model.tree_
    n_nodes = tree.node_count

    if n_nodes > 127:
        raise ValueError(
            f"Tree has {n_nodes} nodes which exceeds int8 capacity (127). "
            f"Reduce max_depth or increase min_samples_leaf."
        )

    feature_index = tree.feature.astype(np.int8)
    threshold = tree.threshold.astype(np.float32)
    children_left = tree.children_left.astype(np.int8)
    children_right = tree.children_right.astype(np.int8)

    # For each node, compute the majority class from tree.value
    leaf_class = np.full(n_nodes, -1, dtype=np.int8)
    for i in range(n_nodes):
        if children_left[i] == -1:  # leaf node (sklearn uses -1 sentinel)
            # tree.value[i] has shape (1, n_classes) – counts per class
            leaf_class[i] = np.argmax(tree.value[i].ravel())

    # Mark internal node feature_index: sklearn uses -2 for leaves,
    # remap to -1 for consistency with our children sentinel
    feature_index[feature_index == -2] = -1

    if isinstance(tree.n_classes, (np.ndarray, list, tuple)):
        # For multi-output trees sklearn stores per-output class counts; we
        # currently support only single-output classification, so take index 0.
        n_classes = int(tree.n_classes[0])
    else:
        n_classes = int(tree.n_classes)

    edt = ExportedDecisionTree(
        feature_index=feature_index,
        threshold=threshold,
        children_left=children_left,
        children_right=children_right,
        leaf_class=leaf_class,
        n_nodes=n_nodes,
        n_classes=int(n_classes),
        max_depth=model.get_depth(),
    )
    logger.info(
        "Exported DT: %d nodes, depth %d, footprint %d bytes",
        n_nodes,
        edt.max_depth,
        edt.memory_footprint_bytes(),
    )
    return edt


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
