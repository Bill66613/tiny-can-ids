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
        # The Car Hacking Dataset CSVs have no header row and variable-width
        # rows: when DLC < 8 only DLC data bytes are present, but the Flag
        # field (R/T) is always the last column.  We read with the python
        # engine so pandas doesn't choke on inconsistent column counts, then
        # normalise every row to 12 columns (Timestamp, ID, DLC, Data0-7, Flag).
        df = _read_variable_width_csv(path)
        _validate_columns(df)
    except (pd.errors.ParserError, ValueError, KeyError, OSError) as exc:
        raise ValueError(f"Could not parse CAN dataset at {path}: {exc}") from exc

    logger.info("Loaded %d frames from %s", len(df), path)
    return df


# Mapping from dataset filename patterns to multi-class attack labels.
# Label 0 is always reserved for normal traffic.
ATTACK_LABEL_MAP: dict[str, int] = {
    "DoS": 1,
    "Fuzzy": 2,
    "gear": 3,
    "RPM": 4,
}

CLASS_NAMES: list[str] = ["Normal", "DoS", "Fuzzy", "Gear", "RPM"]


def load_multi_attack_dataset(
    dataset_dir: str | Path,
    max_rows_per_file: int | None = None,
) -> pd.DataFrame:
    """Load all Car Hacking Dataset CSVs from a directory and assign multi-class labels.

    Each CSV file is expected to contain both normal (``R``) and attack
    (``T``) frames.  The attack class is inferred from the filename:

    * ``DoS_dataset.csv``   → label 1
    * ``Fuzzy_dataset.csv`` → label 2
    * ``gear_dataset.csv``  → label 3
    * ``RPM_dataset.csv``   → label 4

    Normal frames (``R``) from every file are assigned label 0.
    Duplicate normal frames across files are dropped.

    Args:
        dataset_dir: Path to the directory containing the CSV files.
        max_rows_per_file: Optional cap on rows loaded per file (useful for
            quick experiments).

    Returns:
        A combined DataFrame with an extra ``attack_type`` column (int)
        containing the multi-class label.

    Raises:
        FileNotFoundError: If *dataset_dir* does not exist or contains none
            of the expected CSV files.
    """
    dataset_dir = Path(dataset_dir)
    if not dataset_dir.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    parts: list[pd.DataFrame] = []
    normal_frames: pd.DataFrame | None = None

    for pattern, label in ATTACK_LABEL_MAP.items():
        matches = list(dataset_dir.glob(f"{pattern}*dataset*.csv"))
        if not matches:
            logger.warning(
                "No CSV matching '%s*dataset*.csv' in %s", pattern, dataset_dir
            )
            continue

        csv_path = matches[0]
        logger.info("Loading %s (attack_type=%d) …", csv_path.name, label)
        raw = load_can_dataset(csv_path)
        if max_rows_per_file is not None:
            raw = raw.head(max_rows_per_file)

        # Assign multi-class label: 0 for normal, attack label for attacks
        is_attack = raw["Flag"].astype(str).str.strip() != _NORMAL_FLAG
        raw["attack_type"] = 0
        raw.loc[is_attack, "attack_type"] = label

        # Separate normal and attack rows
        attack_rows = raw[is_attack]
        norm_rows = raw[~is_attack]
        parts.append(attack_rows)

        if normal_frames is None:
            normal_frames = norm_rows
        # We keep only one copy of normal traffic to avoid duplication

    if not parts:
        raise FileNotFoundError(f"No Car Hacking Dataset CSVs found in {dataset_dir}")

    if normal_frames is not None:
        normal_frames = normal_frames.copy()
        normal_frames["attack_type"] = 0
        parts.insert(0, normal_frames)

    combined = pd.concat(parts, ignore_index=True)
    combined["Timestamp"] = pd.to_numeric(combined["Timestamp"], errors="coerce")
    combined.sort_values("Timestamp", inplace=True)
    combined.reset_index(drop=True, inplace=True)

    logger.info(
        "Combined multi-attack dataset: %d frames, classes: %s",
        len(combined),
        combined["attack_type"].value_counts().to_dict(),
    )
    return combined

def safe_int_conversion(x):
    """Safe conversion function for CAN bus ID."""
    try:
        if isinstance(x, str):
            # If contains the exponent character 'E' or the plus sign '+'
            if 'E' in x.upper() or '+' in x:
                # Change from Scientific -> Float -> Int
                return int(float(x))
            # If it's pure Hex 
            return int(x, 16)
        return int(x)
    except (ValueError, TypeError):
        return 0 

def preprocess_can_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and type-cast a raw CAN DataFrame.

    Steps applied:

    1. Convert ``Timestamp`` to float.
    2. Convert ``ID`` to integer (from hex string).
    3. Convert payload bytes to integers (``Data0``–``Data7``).
    4. Convert ``DLC`` to integer.
    5. Map ``Flag`` to a label column.

       * If an ``attack_type`` column exists (multi-class), it is used
         directly as the ``label``.
       * Otherwise, a binary label is created: 0 = normal, 1 = attack.

    6. Sort by timestamp and reset the index.

    Args:
        df: Raw CAN DataFrame (as returned by :func:`load_can_dataset`,
            :func:`load_multi_attack_dataset`, or
            :func:`generate_synthetic_can_data`).

    Returns:
        Preprocessed DataFrame with a ``label`` column.
    """
    df = df.copy()

    df["Timestamp"] = pd.to_numeric(df["Timestamp"], errors="coerce")
    df["ID"] = df["ID"].apply(safe_int_conversion)
    df["DLC"] = pd.to_numeric(df["DLC"], errors="coerce").fillna(0).astype(int)

    for col in [f"Data{i}" for i in range(8)]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        else:
            df[col] = 0

    if "attack_type" in df.columns:
        df["label"] = df["attack_type"].astype(int)
    else:
        df["label"] = (df["Flag"].astype(str).str.strip() != _NORMAL_FLAG).astype(int)

    df.sort_values("Timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    df.dropna(subset=["Timestamp"], inplace=True)

    logger.debug(
        "After preprocessing: %d frames, label distribution: %s",
        len(df),
        df["label"].value_counts().to_dict(),
    )
    return df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_variable_width_csv(path: Path) -> pd.DataFrame:
    """Read a Car Hacking Dataset CSV that may have variable-width rows.

    When DLC < 8 the row has fewer data-byte fields, but the Flag (R/T) is
    always the *last* field.  This function normalises every row to the
    standard 12-column layout: Timestamp, ID, DLC, Data0–Data7, Flag.
    """
    # Fast path: try reading with a header row first (handles CSVs written
    # with pandas to_csv which includes a header by default).
    try:
        df = pd.read_csv(path)
        if df.shape[1] == len(_RAW_COLUMNS) and list(df.columns) == _RAW_COLUMNS:
            return df
    except pd.errors.ParserError:
        pass

    # Fast path: try reading without a header (original Car Hacking Dataset
    # format has no header row).
    try:
        df = pd.read_csv(path, header=None)
        if df.shape[1] == len(_RAW_COLUMNS):
            df.columns = _RAW_COLUMNS
            return df
    except pd.errors.ParserError:
        pass

    # Slow path: handle variable-width rows
    logger.info(
        "Variable-width rows detected – using flexible parser for %s", path.name
    )
    rows: list[list[str]] = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            # Layout: Timestamp, ID, DLC, <DLC data bytes>, Flag
            ts = parts[0]
            can_id = parts[1]
            dlc = parts[2]
            flag = parts[-1]
            data_fields = parts[3:-1]  # variable length (0–8)
            # Pad to exactly 8 data fields
            data_fields = (data_fields + ["00"] * 8)[:8]
            rows.append([ts, can_id, dlc] + data_fields + [flag])

    df = pd.DataFrame(rows, columns=_RAW_COLUMNS)
    return df


def _validate_columns(df: pd.DataFrame) -> None:
    required = {"Timestamp", "ID", "DLC", "Flag"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
