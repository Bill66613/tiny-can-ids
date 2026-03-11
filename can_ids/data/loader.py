"""CAN bus dataset loading and preprocessing.

Supports synthetic data generation for testing and loading real Car Hacking
Dataset CSV files (available from the OTIDS / KAIST dataset).

Car Hacking Dataset CSV format::

    Timestamp,ID,DLC,Data0,Data1,...,Data7,Flag

where Flag is 'R' for normal and 'T' (or 'attack type') for attacks.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Column names matching the Car Hacking Dataset format
_RAW_COLUMNS = [
    "Timestamp",
    "ID",
    "DLC",
    "Data0",
    "Data1",
    "Data2",
    "Data3",
    "Data4",
    "Data5",
    "Data6",
    "Data7",
    "Flag",
]

# Attack label – anything other than 'R' (normal) is treated as an attack
_NORMAL_FLAG = "R"


def generate_synthetic_can_data(
    n_normal: int = 1000,
    n_attack: int = 200,
    n_ids: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a synthetic CAN bus dataset for testing and demos.

    Normal traffic uses a fixed set of CAN IDs with realistic inter-arrival
    times. Attack traffic injects high-frequency messages with a small set of
    IDs and anomalous payloads.

    Args:
        n_normal: Number of normal CAN frames to generate.
        n_attack: Number of attack (fuzzing) frames to generate.
        n_ids: Number of distinct CAN IDs in the normal traffic.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with columns matching :data:`_RAW_COLUMNS`.
    """
    rng = np.random.default_rng(seed)

    def _make_frames(
        n: int,
        ids: np.ndarray,
        flag: str,
        base_time: float,
        interval_mean: float,
        interval_std: float,
    ) -> pd.DataFrame:
        timestamps = base_time + np.cumsum(
            rng.normal(interval_mean, interval_std, n).clip(0.0001)
        )
        can_ids = rng.choice(ids, size=n)
        dlc = rng.integers(1, 9, size=n)
        payload = rng.integers(0, 256, size=(n, 8)).astype(np.uint8)
        data = {
            "Timestamp": timestamps,
            "ID": [f"{i:03X}" for i in can_ids],
            "DLC": dlc,
        }
        for col_idx in range(8):
            data[f"Data{col_idx}"] = payload[:, col_idx]
        data["Flag"] = flag
        return pd.DataFrame(data)

    normal_ids = rng.integers(0x100, 0x7FF, size=n_ids)
    attack_ids = rng.integers(0x000, 0x100, size=3)

    normal_df = _make_frames(n_normal, normal_ids, _NORMAL_FLAG, 0.0, 0.01, 0.002)
    attack_df = _make_frames(
        n_attack, attack_ids, "T", normal_df["Timestamp"].iloc[-1], 0.001, 0.0001
    )

    df = pd.concat([normal_df, attack_df], ignore_index=True)
    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    logger.debug("Generated %d normal and %d attack frames", n_normal, n_attack)
    return df


def load_can_dataset(path: str | Path) -> pd.DataFrame:
    """Load a Car Hacking Dataset CSV file from *path*.

    The function accepts both the original whitespace-delimited format and
    standard comma-separated files.  The returned DataFrame has the columns
    defined in :data:`_RAW_COLUMNS`.

    Args:
        path: Path to the dataset file.

    Returns:
        Raw DataFrame with string-typed ID and payload columns.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file cannot be parsed as a CAN dataset.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    try:
        # Try whitespace-delimited first (original KAIST format)
        df = pd.read_csv(path, sep=r"\s+", header=None, engine="python")
        if df.shape[1] == len(_RAW_COLUMNS):
            df.columns = _RAW_COLUMNS
        elif df.shape[1] == len(_RAW_COLUMNS) - 1:
            # Some versions omit the Flag column – treat all as normal
            df.columns = _RAW_COLUMNS[:-1]
            df["Flag"] = _NORMAL_FLAG
        else:
            # Fall back to comma-separated
            df = pd.read_csv(path)
        _validate_columns(df)
    except (pd.errors.ParserError, ValueError, KeyError, OSError) as exc:
        raise ValueError(f"Could not parse CAN dataset at {path}: {exc}") from exc

    logger.info("Loaded %d frames from %s", len(df), path)
    return df


def preprocess_can_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and type-cast a raw CAN DataFrame.

    Steps applied:

    1. Convert ``Timestamp`` to float.
    2. Convert ``ID`` to integer (from hex string).
    3. Convert payload bytes to integers (``Data0``–``Data7``).
    4. Convert ``DLC`` to integer.
    5. Map ``Flag`` to a binary integer label: 0 = normal, 1 = attack.
    6. Sort by timestamp and reset the index.

    Args:
        df: Raw CAN DataFrame (as returned by :func:`load_can_dataset` or
            :func:`generate_synthetic_can_data`).

    Returns:
        Preprocessed DataFrame with an additional ``label`` column.
    """
    df = df.copy()

    df["Timestamp"] = pd.to_numeric(df["Timestamp"], errors="coerce")
    df["ID"] = df["ID"].apply(
        lambda x: int(str(x), 16) if isinstance(x, str) else int(x)
    )
    df["DLC"] = pd.to_numeric(df["DLC"], errors="coerce").fillna(0).astype(int)

    for col in [f"Data{i}" for i in range(8)]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        else:
            df[col] = 0

    df["label"] = (df["Flag"].astype(str).str.strip() != _NORMAL_FLAG).astype(int)

    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.dropna(subset=["Timestamp"], inplace=True)

    logger.debug(
        "After preprocessing: %d frames, %d attack (%.1f%%)",
        len(df),
        df["label"].sum(),
        100 * df["label"].mean(),
    )
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_columns(df: pd.DataFrame) -> None:
    required = {"Timestamp", "ID", "DLC", "Flag"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
