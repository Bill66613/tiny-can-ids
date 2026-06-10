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
        window = df.iloc[w * window_size: (w + 1) * window_size]
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
        window = inter_arrival[w * window_size: (w + 1) * window_size]
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
    payload = df[[c for c in _PAYLOAD_COLS if c in df.columns]
                 ].to_numpy(dtype=np.uint8)
    n_cols = payload.shape[1]
    n = len(df)
    n_windows = max(1, n // window_size)
    features = []

    for w in range(n_windows):
        window = payload[w * window_size: (w + 1) * window_size]
        if len(window) == 0:
            features.append(np.zeros(n_cols * 2 + 1, dtype=np.float32))
            continue
        means = window.mean(axis=0)
        stds = window.std(axis=0)
        hamming = np.mean(np.unpackbits(
            window.astype(np.uint8), axis=1).sum(axis=1))
        features.append(np.concatenate(
            [means, stds, [hamming]]).astype(np.float32))

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
            window_labels = labels[w * window_size: (w + 1) * window_size]
            attack_labels = window_labels[window_labels > 0]
            if len(attack_labels) > 0:
                # Use the most frequent attack class in this window
                values, counts = np.unique(attack_labels, return_counts=True)
                y[w] = values[np.argmax(counts)]
    else:
        y = np.array(
            [
                int(labels[w * window_size: (w + 1) * window_size].any())
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


def _clean_dos_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a DoS dataset before feature extraction.

    Removes timestamp outliers (inter-arrival > 1s, likely recording gaps)
    and ensures strictly monotonic timestamps.
    """
    df = df.copy()
    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    ts = df["Timestamp"].to_numpy(dtype=np.float64)
    if len(ts) > 1:
        dt = np.diff(ts)
        keep = np.concatenate(([True], dt <= 1.0))
        n_dropped = (~keep).sum()
        if n_dropped > 0:
            logger.info("DoS cleaning: dropped %d frames with inter-arrival > 1s", n_dropped)
            df = df.loc[keep].reset_index(drop=True)

    dup_mask = df["Timestamp"].diff() <= 0
    n_dup = dup_mask.sum()
    if n_dup > 0:
        logger.info("DoS cleaning: dropped %d non-monotonic timestamps", n_dup)
        df = df.loc[~dup_mask].reset_index(drop=True)

    return df


_DOS_ATTACK_RATIO_THRESHOLD = 0.2


def build_dos_feature_matrix(
    df: pd.DataFrame,
    window_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a lightweight feature matrix for DoS attack detection.

    Extracts 8 features per window:
      0: Mean Δt              4: ID Entropy
      1: Std Δt               5: Min Δt
      2: Message Rate         6: Timing CV (std/mean)
      3: Dominant ID Freq     7: Unique ID Ratio

    Window label = 1 (attack) only if >= 30% of frames are attack,
    preventing contamination from scattered single-frame injections.
    """
    df = _clean_dos_dataframe(df)

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

        if len(win_ts) > 1:
            dt = np.diff(win_ts)
            mean_dt = dt.mean()
            std_dt = dt.std()
            X[w, 0] = mean_dt
            X[w, 1] = std_dt
            time_span = win_ts[-1] - win_ts[0]
            X[w, 2] = len(win_ts) / max(time_span, 1e-6)
            X[w, 5] = dt.min()
            X[w, 6] = std_dt / max(mean_dt, 1e-12)

        if len(win_ids) > 0:
            unique_ids, counts = np.unique(win_ids, return_counts=True)
            probs = counts / len(win_ids)
            X[w, 3] = probs.max()
            X[w, 4] = float(-np.sum(probs * np.log2(probs + 1e-12)))
            X[w, 7] = len(unique_ids) / window_size

        attack_ratio = win_labels.sum() / window_size
        y[w] = int(attack_ratio >= _DOS_ATTACK_RATIO_THRESHOLD)

    logger.info(
        "DoS DT feature matrix: %s, attack windows: %d / %d (threshold=%.0f%%)",
        X.shape, y.sum(), n_windows, _DOS_ATTACK_RATIO_THRESHOLD * 100,
    )
    return X, y


def build_dos_tnn_feature_matrix(
    df: pd.DataFrame,
    window_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Build an extended 12-feature matrix for DoS detection using TNN.

    Features:
      0: Mean Δt              4: Message Rate             8: Mean Hamming Weight
      1: Std Δt               5: Dominant ID Frequency    9: Data Change Rate
      2: Min Δt               6: Shannon ID Entropy      10: Unique ID Ratio
      3: Max Δt               7: Timing CV (std/mean)    11: Skewness Δt

    Window label = 1 (attack) only if >= 30% of frames are attack.
    """
    df = _clean_dos_dataframe(df)

    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    ids = df["ID"].to_numpy()
    labels = df["label"].to_numpy()

    payload_cols = [f"Data{i}" for i in range(8)]
    existing_cols = [c for c in payload_cols if c in df.columns]
    payload = np.zeros((len(df), 8), dtype=np.uint8)
    if existing_cols:
        payload[:, :len(existing_cols)] = df[existing_cols].to_numpy(dtype=np.uint8)

    n = len(df)
    n_windows = max(1, n // window_size)

    X = np.zeros((n_windows, 12), dtype=np.float32)
    y = np.zeros(n_windows, dtype=np.int32)

    for w in range(n_windows):
        start = w * window_size
        end = (w + 1) * window_size

        win_ts = timestamps[start:end]
        win_ids = ids[start:end]
        win_labels = labels[start:end]
        win_payload = payload[start:end]

        # --- Timing features (F0, F1, F2, F3, F4, F7, F11) ---
        if len(win_ts) > 1:
            dt = np.diff(win_ts)
            mean_dt = dt.mean()
            std_dt = dt.std()
            X[w, 0] = mean_dt
            X[w, 1] = std_dt
            X[w, 2] = dt.min()
            X[w, 3] = dt.max()

            time_span = win_ts[-1] - win_ts[0]
            X[w, 4] = len(win_ts) / max(time_span, 1e-6)

            X[w, 7] = std_dt / max(mean_dt, 1e-12)

            if std_dt > 1e-6:
                X[w, 11] = np.mean(((dt - mean_dt) / std_dt) ** 3)

        # --- ID features (F5, F6, F10) ---
        if len(win_ids) > 0:
            unique_ids, counts = np.unique(win_ids, return_counts=True)
            probs = counts / len(win_ids)

            X[w, 5] = probs.max()
            X[w, 6] = float(-np.sum(probs * np.log2(probs + 1e-12)))
            X[w, 10] = len(unique_ids) / window_size

        # --- Payload features (F8, F9) ---
        if len(win_payload) > 0:
            X[w, 8] = np.mean(np.unpackbits(win_payload, axis=1).sum(axis=1))
            if len(win_payload) > 1:
                changes = np.any(np.diff(win_payload, axis=0) != 0, axis=1)
                X[w, 9] = np.sum(changes) / len(changes)

        attack_ratio = win_labels.sum() / window_size
        y[w] = int(attack_ratio >= _DOS_ATTACK_RATIO_THRESHOLD)

    logger.info(
        "DoS TNN feature matrix: %s, attack windows: %d / %d (threshold=%.0f%%)",
        X.shape, y.sum(), n_windows, _DOS_ATTACK_RATIO_THRESHOLD * 100,
    )
    return X, y

def build_rpm_dt_feature_matrix(
    df: pd.DataFrame,
    window_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a feature matrix specifically for RPM Spoofing detection (Decision Tree).

    Extracts 6 core features per window:
      0: Mean Δt (avg_dt)         3: Dominant ID Freq (max_freq)
      1: Min Δt                   4: Shannon ID Entropy (entropy)
      2: Message Rate             5: Max Consecutive Same ID (max_consecutive)

    Window label = 1 (attack) if >= 30% of frames are attack frames.
    """
    df = _clean_dos_dataframe(df)

    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    ids = df["ID"].to_numpy()
    labels = df["label"].to_numpy()
    n = len(df)
    n_windows = max(1, n // window_size)

    X = np.zeros((n_windows, 6), dtype=np.float32)
    y = np.zeros(n_windows, dtype=np.int32)

    for w in range(n_windows):
        start = w * window_size
        end = (w + 1) * window_size

        win_ts = timestamps[start:end]
        win_ids = ids[start:end]
        win_labels = labels[start:end]

        if len(win_ts) > 1:
            dt = np.diff(win_ts)
            X[w, 0] = dt.mean()                                      # F0: avg_dt (Mean Delta Time)
            X[w, 1] = dt.min()                                       # F1: min_dt (Min Delta Time)
            time_span = win_ts[-1] - win_ts[0]
            X[w, 2] = len(win_ts) / max(time_span, 1e-6)             # F2: message_rate

        if len(win_ids) > 0:
            unique_ids, counts = np.unique(win_ids, return_counts=True)
            probs = counts / len(win_ids)
            X[w, 3] = probs.max()                                    # F3: max_freq
            X[w, 4] = float(-np.sum(probs * np.log2(probs + 1e-12))) # F4: entropy
            
            
            padded_ids = np.insert(win_ids, 0, -1)
            padded_ids = np.append(padded_ids, -2)
            diff_indices = np.where(padded_ids[1:] != padded_ids[:-1])[0]
            if len(diff_indices) > 1:
                max_consecutive = np.max(np.diff(diff_indices))
            else:
                max_consecutive = len(win_ids)
            X[w, 5] = max_consecutive                               # F5: max_consecutive

        attack_ratio = win_labels.sum() / window_size
        y[w] = int(attack_ratio >= _DOS_ATTACK_RATIO_THRESHOLD)

    logger.info(
        "RPM DT feature matrix: %s, attack windows: %d / %d (threshold=%.0f%%)",
        X.shape, y.sum(), n_windows, _DOS_ATTACK_RATIO_THRESHOLD * 100,
    )
    return X, y


def build_rpm_tnn_feature_matrix(
    df: pd.DataFrame,
    window_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Build an extended 12-feature matrix for RPM Spoofing detection using TNN.

    Tailored Features for RPM Spoofing:
      0: Mean Δt              4: Message Rate             8: Data Change Rate
      1: Std Δt               5: Dominant ID Frequency    9: Max Consecutive ID
      2: Min Δt               6: Shannon ID Entropy      10: High Priority Ratio
      3: Max Δt               7: Timing CV (std/mean)    11: Unique ID Ratio

    Window label = 1 (attack) only if >= 30% of frames are attack.
    """
    df = _clean_dos_dataframe(df)

    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    ids = df["ID"].to_numpy()
    labels = df["label"].to_numpy()

    payload_cols = [f"Data{i}" for i in range(8)]
    existing_cols = [c for c in payload_cols if c in df.columns]
    payload = np.zeros((len(df), 8), dtype=np.uint8)
    if existing_cols:
        payload[:, :len(existing_cols)] = df[existing_cols].to_numpy(dtype=np.uint8)

    n = len(df)
    n_windows = max(1, n // window_size)

    X = np.zeros((n_windows, 12), dtype=np.float32)
    y = np.zeros(n_windows, dtype=np.int32)

    for w in range(n_windows):
        start = w * window_size
        end = (w + 1) * window_size

        win_ts = timestamps[start:end]
        win_ids = ids[start:end]
        win_labels = labels[start:end]
        win_payload = payload[start:end]

        # Timing Features
        if len(win_ts) > 1:
            dt = np.diff(win_ts)
            mean_dt = dt.mean()
            std_dt = dt.std()
            X[w, 0] = mean_dt
            X[w, 1] = std_dt
            X[w, 2] = dt.min()
            X[w, 3] = dt.max()

            time_span = win_ts[-1] - win_ts[0]
            X[w, 4] = len(win_ts) / max(time_span, 1e-6)
            X[w, 7] = std_dt / max(mean_dt, 1e-12)

        # ID Features
        if len(win_ids) > 0:
            unique_ids, counts = np.unique(win_ids, return_counts=True)
            probs = counts / len(win_ids)

            X[w, 5] = probs.max()
            X[w, 6] = float(-np.sum(probs * np.log2(probs + 1e-12)))
            X[w, 10] = np.sum(win_ids < 256) / window_size
            X[w, 11] = len(unique_ids) / window_size

            # Tính max consecutive ID (Core feature cho RPM Spoofing)
            padded_ids = np.insert(win_ids, 0, -1)
            padded_ids = np.append(padded_ids, -2)
            diff_indices = np.where(padded_ids[1:] != padded_ids[:-1])[0]
            if len(diff_indices) > 1:
                X[w, 9] = np.max(np.diff(diff_indices))
            else:
                X[w, 9] = len(win_ids)

        # Payload Feature
        if len(win_payload) > 1:
            changes = np.any(np.diff(win_payload, axis=0) != 0, axis=1)
            X[w, 8] = np.sum(changes) / len(changes)

        attack_ratio = win_labels.sum() / window_size
        y[w] = int(attack_ratio >= _DOS_ATTACK_RATIO_THRESHOLD)

    logger.info(
        "RPM TNN feature matrix: %s, attack windows: %d / %d (threshold=%.0f%%)",
        X.shape, y.sum(), n_windows, _DOS_ATTACK_RATIO_THRESHOLD * 100,
    )
    return X, y

def build_gear_dt_feature_matrix(
    df: pd.DataFrame,
    window_size: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Build a feature matrix specifically for Gear Spoofing detection (Decision Tree).

    Extracts 7 core features per window, explicitly calculating Data Change Rate
    only on the Dominant ID to detect static payload injection:
      0: Mean Δt (avg_dt)         4: Shannon ID Entropy (entropy)
      1: Min Δt (min_dt)          5: Max Consecutive Same ID (max_consecutive)
      2: Message Rate             6: Data Change Rate (Dominant ID only)
      3: Dominant ID Freq (max_freq)
    """
    df = _clean_dos_dataframe(df)

    timestamps = df["Timestamp"].to_numpy(dtype=np.float64)
    ids = df["ID"].to_numpy()
    labels = df["label"].to_numpy()
    
    payload_cols = [f"Data{i}" for i in range(8)]
    existing_cols = [c for c in payload_cols if c in df.columns]
    payload = np.zeros((len(df), 8), dtype=np.uint8)
    if existing_cols:
        payload[:, :len(existing_cols)] = df[existing_cols].to_numpy(dtype=np.uint8)

    n = len(df)
    n_windows = max(1, n // window_size)

    X = np.zeros((n_windows, 7), dtype=np.float32)
    y = np.zeros(n_windows, dtype=np.int32)

    for w in range(n_windows):
        start = w * window_size
        end = (w + 1) * window_size

        win_ts = timestamps[start:end]
        win_ids = ids[start:end]
        win_labels = labels[start:end]
        win_payload = payload[start:end]

        if len(win_ts) > 1:
            dt = np.diff(win_ts)
            X[w, 0] = dt.mean()
            X[w, 1] = dt.min()
            time_span = win_ts[-1] - win_ts[0]
            X[w, 2] = len(win_ts) / max(time_span, 1e-6)

        if len(win_ids) > 0:
            unique_ids, counts = np.unique(win_ids, return_counts=True)
            dominant_idx = np.argmax(counts)
            dominant_id = unique_ids[dominant_idx] 

            probs = counts / len(win_ids)
            X[w, 3] = probs.max()
            X[w, 4] = float(-np.sum(probs * np.log2(probs + 1e-12)))
            
            padded_ids = np.insert(win_ids, 0, -1)
            padded_ids = np.append(padded_ids, -2)
            diff_indices = np.where(padded_ids[1:] != padded_ids[:-1])[0]
            if len(diff_indices) > 1:
                X[w, 5] = np.max(np.diff(diff_indices))
            else:
                X[w, 5] = len(win_ids)

            dom_payload = win_payload[win_ids == dominant_id]
            if len(dom_payload) > 1:
                changes = np.any(np.diff(dom_payload, axis=0) != 0, axis=1)
                X[w, 6] = np.sum(changes) / len(changes)                 
            else:
                X[w, 6] = 0.0

        attack_ratio = win_labels.sum() / window_size
        y[w] = int(attack_ratio >= _DOS_ATTACK_RATIO_THRESHOLD)

    return X, y
