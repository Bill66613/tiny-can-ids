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

# ------------------------------------------------------------------
# DoS Feature Extraction
# ------------------------------------------------------------------
def build_dos_feature_matrix(
    df: pd.DataFrame, 
    window_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a lightweight feature matrix specifically for DoS attack detection.
    Extracts only 8 critical features per window to save CPU cycles on MCU.
    
    Features: [Mean Δt, Std Δt, Message Rate, Dominant ID Freq, ID Entropy]
    """
    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    ids = df["ID"].to_numpy()
    labels = df["label"].to_numpy()
    n = len(df)
    n_windows = max(1, n // window_size)

    X = np.zeros((n_windows, 8), dtype=np.float32)
    y = np.zeros(n_windows, dtype=np.int32)

    for w in range(n_windows):
        start = w * window_size
        end = (w + 1) * window_size

        win_ts = timestamps[start:end]
        win_ids = ids[start:end]
        win_labels = labels[start:end]
        # Timing: Mean Δt và Std Δt
        if len(win_ts) > 1:
            dt = np.diff(win_ts)
            X[w, 0] = dt.mean()
            X[w, 1] = dt.std()
            
            # Message Rate (Messages / Second)
            time_span = win_ts[-1] - win_ts[0]
            X[w, 2] = len(win_ts) / max(time_span, 1e-6)
            # Min Δt: Highly sensitive to instant DoS signals
            X[w, 5] = dt.min()
        else:
            X[w, 0], X[w, 1], X[w, 2], X[w, 5] = 0.0, 0.0, 0.0

        if len(win_ids) > 0:
            # Calculate the probability of the IDs appearing in the window.
            _, counts = np.unique(win_ids, return_counts=True)
            probs = counts / len(win_ids)
            
            # Dominant ID Frequency 
            X[w, 3] = probs.max()
            
            # Shannon Entropy
            X[w, 4] = float(-np.sum(probs * np.log2(probs + 1e-12)))

            # High Priority ID rate (< 0x100 or 256)
            X[w, 6] = np.sum(win_ids < 256) / len(win_ids)
            
            # Longest sequence of identical IDs
            # Logic: Find the points where the ID changes, calculate the distance between those points
            changes = np.concatenate(([1], np.diff(win_ids) != 0))
            run_lengths = np.diff(np.where(np.concatenate((changes, [1])))[0])
            X[w, 7] = run_lengths.max() if len(run_lengths) > 0 else 0
        # If there is any attack -> Label 1
        y[w] = int(win_labels.any())
        
    logger.info("DoS Feature matrix optimized: %s (Reduced from 46 to 8 features)", X.shape)
    return X, y

def build_dos_tnn_feature_matrix(
    df: pd.DataFrame, 
    window_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build an extended 12-feature matrix specifically for DoS attack detection using TNN.
    Includes Payload and advanced timing/distribution features for robustness.
    
    Features:
    0: Mean Δt                 4: Message Rate              8: Mean Hamming Weight
    1: Std Δt                  5: Dominant ID Frequency     9: Data Change Rate
    2: Min Δt                  6: Shannon ID Entropy       10: ID Gaps
    3: Max Δt                  7: High Priority ID Ratio   11: Skewness Δt
    """
    import logging
    logger = logging.getLogger(__name__)

    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    ids = df["ID"].to_numpy()
    labels = df["label"].to_numpy()
    
    # Prepare the payload data. (Data0 -> Data7)
    payload_cols = [f"Data{i}" for i in range(8)]
    existing_cols = [c for c in payload_cols if c in df.columns]
    payload = np.zeros((len(df), 8), dtype=np.uint8)
    if existing_cols:
        payload[:, :len(existing_cols)] = df[existing_cols].to_numpy(dtype=np.uint8)

    n = len(df)
    n_windows = max(1, n // window_size)

    # Initialize the matrix X (12 features)
    X = np.zeros((n_windows, 12), dtype=np.float32)
    y = np.zeros(n_windows, dtype=np.int32)

    for w in range(n_windows):
        start = w * window_size
        end = (w + 1) * window_size

        win_ts = timestamps[start:end]
        win_ids = ids[start:end]
        win_labels = labels[start:end]
        win_payload = payload[start:end]

        # ------------------------------------------------
        # Group 1: Timing Features (F0, F1, F2, F3, F4, F11)
        # ------------------------------------------------
        if len(win_ts) > 1:
            dt = np.diff(win_ts)
            X[w, 0] = dt.mean()
            X[w, 1] = dt.std()
            X[w, 2] = dt.min()
            X[w, 3] = dt.max()
            
            # F4: Message Rate
            time_span = win_ts[-1] - win_ts[0]
            X[w, 4] = len(win_ts) / max(time_span, 1e-6)
            
            # F11: Skewness Δt (Use manual methods to avoid importing scipy.)
            # Fisher-Pearson Formula: E[((x - mu) / sigma)^3]
            std_dt = X[w, 1]
            if std_dt > 1e-6:
                X[w, 11] = np.mean(((dt - X[w, 0]) / std_dt) ** 3)
            else:
                X[w, 11] = 0.0

        # ------------------------------------------------
        # Group 2: ID Features (F5, F6, F7, F10)
        # ------------------------------------------------
        if len(win_ids) > 0:
            unique_ids, counts = np.unique(win_ids, return_counts=True)
            probs = counts / len(win_ids)
            
            X[w, 5] = probs.max()                                          # F5: Dominant Freq
            X[w, 6] = float(-np.sum(probs * np.log2(probs + 1e-12)))       # F6: Entropy
            X[w, 7] = np.sum(win_ids < 256) / len(win_ids)                 # F7: High Priority Ratio
            
            # F10: ID Gaps 
            # Assuming the ID range is from Min(ID) to Max(ID). Number of missing IDs = (Gaps) - (Number of unique IDs)
            id_range = int(win_ids.max() - win_ids.min() + 1)
            X[w, 10] = max(0, id_range - len(unique_ids))

        # ------------------------------------------------
        # Group 3: Payload Features (F8, F9)
        # ------------------------------------------------
        if len(win_payload) > 0:
            # F8: Mean Hamming Weight (Count the total number of 1 bits in all 8 bytes, then calculate the average.)
            X[w, 8] = np.mean(np.unpackbits(win_payload, axis=1).sum(axis=1))
            
            # F9: Data Change Rate (The percentage of frames with changed data compared to the frame immediately preceding it.)
            if len(win_payload) > 1:
                # np.diff trên axis=0 subtract the previous line from the following line. If != 0, it means a byte has been changed.
                changes = np.any(np.diff(win_payload, axis=0) != 0, axis=1)
                X[w, 9] = np.sum(changes) / len(changes)

        # Label: Any packet that is an Attack -> That window is an Attack
        y[w] = int(win_labels.any())
        
    logger.info("DoS TNN Feature matrix constructed: %s (12 features)", X.shape)
    return X, y