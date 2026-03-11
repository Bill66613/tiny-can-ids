"""Feature engineering for CAN bus frames.

Extracts three families of features:

* **ID-frequency features** – how often each CAN ID appears in a sliding
  window, normalized counts, and the entropy of the ID distribution.
* **Timing features** – inter-arrival time statistics (mean, std, min, max)
  per window.
* **Payload features** – byte-level statistics (mean, std, hamming weight)
  aggregated per window.

All functions operate on a preprocessed DataFrame (output of
:func:`can_ids.data.loader.preprocess_can_data`) and return a feature matrix
``X`` (numpy array, float32) and label vector ``y`` (numpy array, int).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_PAYLOAD_COLS = [f"Data{i}" for i in range(8)]


def extract_id_frequency_features(
    df: pd.DataFrame,
    window_size: int = 100,
) -> np.ndarray:
    """Compute ID-frequency features over rolling windows.

    For each window of *window_size* consecutive frames, compute:

    * Frequency (count) of each unique CAN ID, normalized by window size.
    * Shannon entropy of the ID distribution.

    The top-*K* most common IDs (K = 20) are kept; less common IDs are
    aggregated into an "other" bucket.

    Args:
        df: Preprocessed CAN DataFrame.
        window_size: Number of frames per window.

    Returns:
        2-D array of shape ``(n_windows, 22)``: 20 ID frequency bins +
        "other" bucket + entropy.
    """
    top_k = 20
    top_ids = df["ID"].value_counts().head(top_k).index.tolist()
    n = len(df)
    n_windows = max(1, n // window_size)
    features = []

    for w in range(n_windows):
        window = df.iloc[w * window_size : (w + 1) * window_size]
        counts = window["ID"].value_counts()
        total = len(window)
        row = np.zeros(top_k + 2, dtype=np.float32)
        other = 0
        for can_id, cnt in counts.items():
            if can_id in top_ids:
                row[top_ids.index(can_id)] = cnt / total
            else:
                other += cnt
        row[top_k] = other / total
        probs = row[: top_k + 1]
        probs = probs[probs > 0]
        row[top_k + 1] = float(-np.sum(probs * np.log2(probs + 1e-12)))
        features.append(row)

    return np.array(features, dtype=np.float32)


def extract_timing_features(
    df: pd.DataFrame,
    window_size: int = 100,
) -> np.ndarray:
    """Compute inter-arrival timing statistics over rolling windows.

    For each window, compute the mean, standard deviation, minimum, and
    maximum of the inter-frame arrival intervals.

    Args:
        df: Preprocessed CAN DataFrame (must have a ``Timestamp`` column).
        window_size: Number of frames per window.

    Returns:
        2-D array of shape ``(n_windows, 4)``.
    """
    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    inter_arrival = np.abs(np.diff(timestamps))
    # Pad the first position so length matches the frame count
    inter_arrival = np.concatenate([[inter_arrival[0] if len(inter_arrival) > 0 else 0.0], inter_arrival])

    n = len(df)
    n_windows = max(1, n // window_size)
    features = []

    for w in range(n_windows):
        window = inter_arrival[w * window_size : (w + 1) * window_size]
        if len(window) == 0:
            features.append(np.zeros(4, dtype=np.float32))
        else:
            features.append(
                np.array(
                    [window.mean(), window.std(), window.min(), window.max()],
                    dtype=np.float32,
                )
            )

    return np.array(features, dtype=np.float32)


def extract_payload_features(
    df: pd.DataFrame,
    window_size: int = 100,
) -> np.ndarray:
    """Compute payload statistics over rolling windows.

    For each window, compute per-byte-position mean, std, and the mean
    Hamming weight (number of set bits) across all payload bytes.

    Args:
        df: Preprocessed CAN DataFrame with ``Data0``–``Data7`` columns.
        window_size: Number of frames per window.

    Returns:
        2-D array of shape ``(n_windows, 17)``:
        8 per-position means + 8 per-position stds + mean Hamming weight.
    """
    payload = df[[c for c in _PAYLOAD_COLS if c in df.columns]].to_numpy(
        dtype=np.uint8
    )
    n_cols = payload.shape[1]
    n = len(df)
    n_windows = max(1, n // window_size)
    features = []

    for w in range(n_windows):
        window = payload[w * window_size : (w + 1) * window_size]
        if len(window) == 0:
            features.append(np.zeros(n_cols * 2 + 1, dtype=np.float32))
            continue
        means = window.mean(axis=0)
        stds = window.std(axis=0)
        hamming = np.mean(np.unpackbits(window.astype(np.uint8), axis=1).sum(axis=1))
        features.append(
            np.concatenate([means, stds, [hamming]]).astype(np.float32)
        )

    return np.array(features, dtype=np.float32)


def build_feature_matrix(
    df: pd.DataFrame,
    window_size: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    """Build the full feature matrix and label vector.

    Concatenates ID-frequency, timing, and payload features for each window.
    The window label is 1 (attack) if *any* frame in the window is an attack
    frame, otherwise 0 (normal).

    Args:
        df: Preprocessed CAN DataFrame.
        window_size: Number of frames per window.

    Returns:
        Tuple ``(X, y)`` where:

        * ``X`` has shape ``(n_windows, n_features)`` (float32).
        * ``y`` has shape ``(n_windows,)`` (int).
    """
    freq = extract_id_frequency_features(df, window_size)
    timing = extract_timing_features(df, window_size)
    payload = extract_payload_features(df, window_size)

    X = np.concatenate([freq, timing, payload], axis=1)

    labels = df["label"].to_numpy()
    n_windows = X.shape[0]
    y = np.array(
        [
            int(labels[w * window_size : (w + 1) * window_size].any())
            for w in range(n_windows)
        ],
        dtype=np.int32,
    )

    logger.info(
        "Feature matrix: %s, attack windows: %d / %d",
        X.shape,
        y.sum(),
        n_windows,
    )
    return X, y
