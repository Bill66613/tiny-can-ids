"""Tests for can_ids.data.loader."""

import pytest
import numpy as np
import pandas as pd

from can_ids.data.loader import (
    generate_synthetic_can_data,
    preprocess_can_data,
)


def test_generate_synthetic_returns_dataframe():
    df = generate_synthetic_can_data(n_normal=100, n_attack=20, seed=0)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 120
    assert set(df.columns) >= {"Timestamp", "ID", "DLC", "Flag"}


def test_generate_synthetic_labels():
    df = generate_synthetic_can_data(n_normal=100, n_attack=20, seed=0)
    normal = (df["Flag"] == "R").sum()
    attack = (df["Flag"] != "R").sum()
    assert normal == 100
    assert attack == 20


def test_generate_reproducible():
    df1 = generate_synthetic_can_data(seed=7)
    df2 = generate_synthetic_can_data(seed=7)
    assert df1["Timestamp"].equals(df2["Timestamp"])


def test_generate_different_seeds():
    df1 = generate_synthetic_can_data(seed=1)
    df2 = generate_synthetic_can_data(seed=2)
    assert not df1["Timestamp"].equals(df2["Timestamp"])


def test_generate_sorted_by_timestamp():
    df = generate_synthetic_can_data(n_normal=200, n_attack=50, seed=99)
    assert df["Timestamp"].is_monotonic_increasing


def test_preprocess_adds_label_column():
    df = generate_synthetic_can_data(n_normal=100, n_attack=20, seed=0)
    proc = preprocess_can_data(df)
    assert "label" in proc.columns


def test_preprocess_label_values():
    df = generate_synthetic_can_data(n_normal=100, n_attack=20, seed=0)
    proc = preprocess_can_data(df)
    assert set(proc["label"].unique()).issubset({0, 1})
    assert proc["label"].sum() > 0  # some attack frames


def test_preprocess_id_is_integer():
    df = generate_synthetic_can_data(n_normal=100, n_attack=0, seed=0)
    proc = preprocess_can_data(df)
    assert proc["ID"].dtype in (int, np.int64, np.int32)


def test_preprocess_payload_bytes_in_range():
    df = generate_synthetic_can_data(n_normal=200, n_attack=0, seed=0)
    proc = preprocess_can_data(df)
    for col in [f"Data{i}" for i in range(8)]:
        assert proc[col].between(0, 255).all(), f"{col} out of range"


def test_preprocess_no_nan_timestamps():
    df = generate_synthetic_can_data(n_normal=100, n_attack=10, seed=5)
    proc = preprocess_can_data(df)
    assert proc["Timestamp"].notna().all()


def test_load_can_dataset_file_not_found():
    from can_ids.data.loader import load_can_dataset
    with pytest.raises(FileNotFoundError):
        load_can_dataset("/nonexistent/path/data.csv")


def test_load_can_dataset_roundtrip(tmp_path):
    """Saving a synthetic dataset as CSV and reloading it should work."""
    from can_ids.data.loader import load_can_dataset, _RAW_COLUMNS

    df = generate_synthetic_can_data(n_normal=50, n_attack=10, seed=1)
    csv_path = tmp_path / "test_can.csv"
    df.to_csv(csv_path, index=False)

    loaded = load_can_dataset(csv_path)
    assert len(loaded) == len(df)
    assert "Flag" in loaded.columns
