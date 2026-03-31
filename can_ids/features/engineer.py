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


def _compute_top_ids(df: pd.DataFrame, k: int = 20) -> list:
    """Return the *k* most common CAN IDs in *df*."""
    return df["ID"].value_counts().head(k).index.tolist()


def extract_id_frequency_features(
    df: pd.DataFrame,
    window_size: int = 100,
    top_ids: list | None = None,
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
        top_ids: Pre-computed list of top-K CAN IDs.  If *None*, computed
            from *df*.

    Returns:
        2-D array of shape ``(n_windows, 22)``: 20 ID frequency bins +
        "other" bucket + entropy.
    """
    top_k = 20
    if top_ids is None:
        top_ids = _compute_top_ids(df, k=top_k)
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
    inter_arrival = np.concatenate(
        [[inter_arrival[0] if len(inter_arrival) > 0 else 0.0], inter_arrival]
    )

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
    payload = df[[c for c in _PAYLOAD_COLS if c in df.columns]].to_numpy(dtype=np.uint8)
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
        features.append(np.concatenate([means, stds, [hamming]]).astype(np.float32))

    return np.array(features, dtype=np.float32)


def extract_rate_and_novelty_features(
    df: pd.DataFrame,
    window_size: int = 100,
    top_ids: list | None = None,
) -> np.ndarray:
    """Compute CAN-domain rate and ID novelty features per window.

    For each window of *window_size* consecutive frames, compute:

    * **Message rate** – frames per second in the window.  Highly
      discriminative for DoS flooding attacks (10-100x normal rate).
    * **Unique ID count** – number of distinct CAN IDs, normalised by
      window size.  Captures Fuzzy attacks that inject random IDs.
    * **New ID ratio** – fraction of unique IDs in the window that do not
      appear in the global *top_ids* set.  Captures gear/RPM spoofing
      attacks that inject specific unusual IDs.

    Args:
        df: Preprocessed CAN DataFrame.
        window_size: Number of frames per window.
        top_ids: Pre-computed list of top-K CAN IDs.  If *None*, computed
            from *df*.

    Returns:
        2-D array of shape ``(n_windows, 3)``.
    """
    if top_ids is None:
        top_ids = _compute_top_ids(df, k=20)

    top_set = set(top_ids)
    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    ids = df["ID"].to_numpy()
    n = len(df)
    n_windows = max(1, n // window_size)
    features = np.zeros((n_windows, 3), dtype=np.float32)

    for w in range(n_windows):
        start = w * window_size
        end = (w + 1) * window_size
        win_ts = timestamps[start:end]
        win_ids = ids[start:end]

        # Message rate (frames / second)
        time_span = win_ts[-1] - win_ts[0] if len(win_ts) > 1 else 1e-6
        features[w, 0] = len(win_ts) / max(time_span, 1e-6)

        # Unique ID count (normalised)
        unique_ids = set(win_ids)
        features[w, 1] = len(unique_ids) / window_size

        # New ID ratio
        if len(unique_ids) > 0:
            new_ids = sum(1 for uid in unique_ids if uid not in top_set)
            features[w, 2] = new_ids / len(unique_ids)

    return features


def build_feature_matrix(
    df: pd.DataFrame,
    window_size: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    """Build the full feature matrix and label vector.

    Concatenates ID-frequency, timing, payload, and rate/novelty features
    for each window.  The resulting feature vector has **46** columns:
    22 (ID freq) + 4 (timing) + 17 (payload) + 3 (rate & novelty).

    For **binary** labels (0/1), the window label is 1 (attack) if *any*
    frame in the window is an attack frame, otherwise 0 (normal).

    For **multi-class** labels (0–N), the window label is the highest
    attack class present in the window (ties go to the first seen).
    If the window contains only normal frames (label 0), its label is 0.

    Args:
        df: Preprocessed CAN DataFrame.
        window_size: Number of frames per window.

    Returns:
        Tuple ``(X, y)`` where:

        * ``X`` has shape ``(n_windows, 46)`` (float32).
        * ``y`` has shape ``(n_windows,)`` (int).
    """
    top_ids = _compute_top_ids(df, k=20)
    freq = extract_id_frequency_features(df, window_size, top_ids=top_ids)
    timing = extract_timing_features(df, window_size)
    payload = extract_payload_features(df, window_size)
    rate_novelty = extract_rate_and_novelty_features(
        df, window_size, top_ids=top_ids
    )

    X = np.concatenate([freq, timing, payload, rate_novelty], axis=1)

    labels = df["label"].to_numpy()
    n_windows = X.shape[0]
    is_multiclass = labels.max() > 1

    if is_multiclass:
        # Multi-class: take the most common non-zero label in the window
        y = np.zeros(n_windows, dtype=np.int32)
        for w in range(n_windows):
            window_labels = labels[w * window_size : (w + 1) * window_size]
            attack_labels = window_labels[window_labels > 0]
            if len(attack_labels) > 0:
                # Use the most frequent attack class in this window
                values, counts = np.unique(attack_labels, return_counts=True)
                y[w] = values[np.argmax(counts)]
    else:
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
