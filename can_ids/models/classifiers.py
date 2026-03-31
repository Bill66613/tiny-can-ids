"""Lightweight ML classifiers for CAN intrusion detection.

Provides three model families suitable for embedded deployment:

* :func:`train_logistic_regression` – scikit-learn logistic regression.
* :func:`train_decision_tree` – scikit-learn decision tree with depth limit.
* :class:`TinyNeuralNetwork` – a small Keras/TensorFlow neural network
  designed to fit on microcontrollers (< 50 KB when quantized).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

logger = logging.getLogger(__name__)


def train_logistic_regression(
    X_train: np.ndarray,
    y_train: np.ndarray,
    C: float = 1.0,
    max_iter: int = 1000,
    class_weight: str | dict | None = "balanced",
    **kwargs: Any,
) -> LogisticRegression:
    """Train a logistic regression classifier.

    Args:
        X_train: Training feature matrix.
        y_train: Training labels (0 = normal, 1 = attack).
        C: Inverse of regularisation strength.
        max_iter: Maximum number of solver iterations.
        class_weight: Weights associated with classes.  ``"balanced"``
            (default) automatically adjusts weights inversely proportional
            to class frequencies, which is important for imbalanced CAN
            bus data (typically 95%+ normal frames).
        **kwargs: Additional keyword arguments forwarded to
            :class:`~sklearn.linear_model.LogisticRegression`.

    Returns:
        Fitted :class:`~sklearn.linear_model.LogisticRegression` model.
    """
    model = LogisticRegression(
        C=C, max_iter=max_iter, class_weight=class_weight, **kwargs
    )
    model.fit(X_train, y_train)
    logger.info("Logistic regression trained – coef shape: %s", model.coef_.shape)
    return model


def train_decision_tree(
    X_train: np.ndarray,
    y_train: np.ndarray,
    max_depth: int = 5,
    min_samples_leaf: int = 5,
    class_weight: str | dict | None = "balanced",
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
        class_weight: Weights associated with classes.  ``"balanced"``
            (default) automatically adjusts weights inversely proportional
            to class frequencies.
        **kwargs: Additional keyword arguments forwarded to
            :class:`~sklearn.tree.DecisionTreeClassifier`.

    Returns:
        Fitted :class:`~sklearn.tree.DecisionTreeClassifier` model.
    """
    model = DecisionTreeClassifier(
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
        class_weight=class_weight,
        **kwargs,
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

    Architecture (binary)::

        input → Dense(32, ReLU) → Dense(16, ReLU) → Dense(1, sigmoid)

    Architecture (multi-class, *num_classes* > 2)::

        input → Dense(32, ReLU) → Dense(16, ReLU) → Dense(num_classes, softmax)

    The model is intentionally tiny so that it can be quantized and deployed
    on microcontrollers with limited flash/RAM.

    Args:
        input_dim: Number of input features.
        num_classes: Number of output classes.  Use 2 (default) for binary
            classification (normal vs attack) or >2 for multi-class.
        hidden_units: Tuple of hidden layer sizes.
        learning_rate: Adam learning rate.
    """

    def __init__(
        self,
        input_dim: int,
        num_classes: int = 2,
        hidden_units: tuple[int, ...] = (32, 16),
        learning_rate: float = 1e-3,
    ) -> None:
        self.input_dim = input_dim
        self.num_classes = num_classes
        self.hidden_units = hidden_units
        self.learning_rate = learning_rate
        self._model: Any = None
        self._build()

    @property
    def is_multiclass(self) -> bool:
        return self.num_classes > 2

    def _build(self) -> None:
        import tensorflow as tf

        inputs = tf.keras.Input(shape=(self.input_dim,), name="can_features")
        x = inputs
        for units in self.hidden_units:
            x = tf.keras.layers.Dense(units, activation="relu")(x)

        if self.is_multiclass:
            outputs = tf.keras.layers.Dense(
                self.num_classes, activation="softmax", name="ids_output"
            )(x)
            loss = "sparse_categorical_crossentropy"
        else:
            outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="ids_output")(
                x
            )
            loss = "binary_crossentropy"

        self._model = tf.keras.Model(inputs=inputs, outputs=outputs, name="tiny_ids")
        self._model.compile(
            optimizer=tf.keras.optimizers.Adam(self.learning_rate),
            loss=loss,
            metrics=["accuracy"],
        )
        logger.debug(
            "TinyNeuralNetwork built – parameters: %d, classes: %d",
            self._model.count_params(),
            self.num_classes,
        )

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        epochs: int = 20,
        batch_size: int = 32,
        validation_split: float = 0.1,
        verbose: int = 0,
        balance_classes: bool = False,
    ) -> "TinyNeuralNetwork":
        """Train the neural network.

        Args:
            X_train: Training features (float32).
            y_train: Binary labels.
            epochs: Number of training epochs.
            batch_size: Mini-batch size.
            validation_split: Fraction of training data used for validation.
            verbose: Keras verbosity level.
            balance_classes: If *True*, compute sample weights inversely
                proportional to class frequencies to handle imbalanced CAN
                bus data.

        Returns:
            ``self`` for method chaining.
        """
        fit_kwargs: dict = dict(
            epochs=epochs,
            batch_size=batch_size,
            validation_split=validation_split,
            verbose=verbose,
        )
        if balance_classes:
            from sklearn.utils.class_weight import compute_sample_weight

            fit_kwargs["sample_weight"] = compute_sample_weight(
                "balanced", y_train
            )

        self._model.fit(
            X_train.astype(np.float32),
            y_train.astype(np.float32),
            **fit_kwargs,
        )
        logger.info("TinyNeuralNetwork training complete")
        return self

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Predict labels for *X*.

        For binary mode, applies *threshold* to the sigmoid output.
        For multi-class mode, returns the argmax class index.

        Args:
            X: Feature matrix.
            threshold: Decision threshold (binary mode only).

        Returns:
            Integer array of predicted labels.
        """
        raw = self._model.predict(X.astype(np.float32), verbose=0)
        if self.is_multiclass:
            return np.argmax(raw, axis=1).astype(int)
        return (raw.ravel() >= threshold).astype(int)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Return output probabilities.

        For binary mode, returns a 1-D array of attack probabilities.
        For multi-class mode, returns a 2-D array of shape
        ``(n_samples, num_classes)``.

        Args:
            X: Feature matrix.

        Returns:
            Probability array.
        """
        raw = self._model.predict(X.astype(np.float32), verbose=0)
        if self.is_multiclass:
            return raw
        return raw.ravel()

    @property
    def keras_model(self) -> Any:
        """The underlying :class:`tf.keras.Model` instance."""
        return self._model

    def summary(self) -> None:
        """Print the Keras model summary."""
        self._model.summary()
