"""Lightweight ML classifiers for CAN intrusion detection.

Provides three model families suitable for embedded deployment:

* :func:`train_logistic_regression` – scikit-learn logistic regression.
* :func:`train_decision_tree` – scikit-learn decision tree with depth limit.
* :class:`TinyNeuralNetwork` – a small Keras/TensorFlow neural network
  designed to fit on microcontrollers (< 50 KB when quantized).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

logger = logging.getLogger(__name__)


def train_logistic_regression(
    X_train: np.ndarray,
    y_train: np.ndarray,
    C: float = 1.0,
    max_iter: int = 1000,
    **kwargs: Any,
) -> LogisticRegression:
    """Train a logistic regression classifier.

    Args:
        X_train: Training feature matrix.
        y_train: Training labels (0 = normal, 1 = attack).
        C: Inverse of regularisation strength.
        max_iter: Maximum number of solver iterations.
        **kwargs: Additional keyword arguments forwarded to
            :class:`~sklearn.linear_model.LogisticRegression`.

    Returns:
        Fitted :class:`~sklearn.linear_model.LogisticRegression` model.
    """
    model = LogisticRegression(C=C, max_iter=max_iter, **kwargs)
    model.fit(X_train, y_train)
    logger.info(
        "Logistic regression trained – coef shape: %s", model.coef_.shape
    )
    return model


def train_decision_tree(
    X_train: np.ndarray,
    y_train: np.ndarray,
    max_depth: int = 5,
    min_samples_leaf: int = 5,
    **kwargs: Any,
) -> DecisionTreeClassifier:
    """Train a shallow decision tree classifier.

    Depth is limited by *max_depth* to keep the model small enough for
    embedded deployment.

    Args:
        X_train: Training feature matrix.
        y_train: Training labels.
        max_depth: Maximum tree depth.
        min_samples_leaf: Minimum number of samples at a leaf node.
        **kwargs: Additional keyword arguments forwarded to
            :class:`~sklearn.tree.DecisionTreeClassifier`.

    Returns:
        Fitted :class:`~sklearn.tree.DecisionTreeClassifier` model.
    """
    model = DecisionTreeClassifier(
        max_depth=max_depth, min_samples_leaf=min_samples_leaf, **kwargs
    )
    model.fit(X_train, y_train)
    logger.info(
        "Decision tree trained – depth: %d, leaves: %d",
        model.get_depth(),
        model.get_n_leaves(),
    )
    return model


class TinyNeuralNetwork:
    """A small fully-connected neural network for CAN intrusion detection.

    Architecture: ``input → Dense(32, ReLU) → Dense(16, ReLU) → Dense(1, sigmoid)``

    The model is intentionally tiny so that it can be quantized and deployed
    on microcontrollers with limited flash/RAM.

    Args:
        input_dim: Number of input features.
        hidden_units: Tuple of hidden layer sizes.
        learning_rate: Adam learning rate.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_units: tuple[int, ...] = (32, 16),
        learning_rate: float = 1e-3,
    ) -> None:
        self.input_dim = input_dim
        self.hidden_units = hidden_units
        self.learning_rate = learning_rate
        self._model: Any = None
        self._build()

    def _build(self) -> None:
        import tensorflow as tf

        inputs = tf.keras.Input(shape=(self.input_dim,), name="can_features")
        x = inputs
        for units in self.hidden_units:
            x = tf.keras.layers.Dense(units, activation="relu")(x)
        outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="ids_output")(x)

        self._model = tf.keras.Model(inputs=inputs, outputs=outputs, name="tiny_ids")
        self._model.compile(
            optimizer=tf.keras.optimizers.Adam(self.learning_rate),
            loss="binary_crossentropy",
            metrics=["accuracy"],
        )
        logger.debug(
            "TinyNeuralNetwork built – parameters: %d",
            self._model.count_params(),
        )

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        epochs: int = 20,
        batch_size: int = 32,
        validation_split: float = 0.1,
        verbose: int = 0,
    ) -> "TinyNeuralNetwork":
        """Train the neural network.

        Args:
            X_train: Training features (float32).
            y_train: Binary labels.
            epochs: Number of training epochs.
            batch_size: Mini-batch size.
            validation_split: Fraction of training data used for validation.
            verbose: Keras verbosity level.

        Returns:
            ``self`` for method chaining.
        """
        self._model.fit(
            X_train.astype(np.float32),
            y_train.astype(np.float32),
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            verbose=verbose,
        )
        logger.info("TinyNeuralNetwork training complete")
        return self

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Predict binary labels for *X*.

        Args:
            X: Feature matrix.
            threshold: Decision threshold for the sigmoid output.

        Returns:
            Integer array of predicted labels.
        """
        probs = self._model.predict(X.astype(np.float32), verbose=0)
        return (probs.ravel() >= threshold).astype(int)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return sigmoid output probabilities.

        Args:
            X: Feature matrix.

        Returns:
            1-D float array of probabilities for the positive (attack) class.
        """
        return self._model.predict(X.astype(np.float32), verbose=0).ravel()

    @property
    def keras_model(self) -> Any:
        """The underlying :class:`tf.keras.Model` instance."""
        return self._model

    def summary(self) -> None:
        """Print the Keras model summary."""
        self._model.summary()
