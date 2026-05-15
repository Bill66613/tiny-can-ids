"""End-to-end CAN bus intrusion detection pipeline.

Usage::

    python scripts/run_pipeline.py [--output-dir OUTPUT_DIR]

    # Use a config file (or auto-detect pipeline.toml in cwd):
    python scripts/run_pipeline.py --config my_config.toml

    # CLI arguments override config file values:
    python scripts/run_pipeline.py --config my_config.toml --epochs 50

    # Train on all 4 attack types from the Car Hacking Dataset:
    python scripts/run_pipeline.py --dataset-dir path/to/Car-Hacking-Dataset

    # Export all models to C:
    python scripts/run_pipeline.py --export-model all --output-dir output/

Steps:

1. Generate (or load) a CAN bus dataset.
2. Pre-process frames.
3. Engineer features (46 features: 22 ID freq + 4 timing + 17 payload + 3 rate/novelty).
4. Train/test split and scaling.
5. Train Logistic Regression, Decision Tree, and Tiny Neural Network.
6. Evaluate all models and print comparison table.
7. Quantize the Tiny Neural Network (INT8).
8. Export to TFLite (optional).
9. Export selected model(s) to C code.
10. Print deployment summary.
"""

from __future__ import annotations

import argparse
import logging
import sys
import joblib
import os

import pandas as pd
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger("pipeline")


def _load_config(path: Path) -> dict:
    """Load a TOML config file and return it as a flat dict."""
    if tomllib is None:
        logger.warning(
            "Config file found but TOML support unavailable (Python < 3.11). "
            "Install tomli: pip install tomli"
        )
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


# Hardcoded fallback defaults (layer 3 — lowest priority).
_DEFAULTS: dict = {
    "dataset": None,
    "dataset_dir": None,
    "max_rows_per_file": None,
    "output_dir": "output",
    "window_size": 50,
    "epochs": 20,
    "no_tflite": False,
    "export_model": "tnn",
    "mode": "standard",
}

# TOML key → argparse dest mapping (handles hyphens vs underscores).
_TOML_KEY_MAP: dict[str, str] = {
    "dataset-dir": "dataset_dir",
    "max-rows-per-file": "max_rows_per_file",
    "output-dir": "output_dir",
    "window-size": "window_size",
    "export-model": "export_model",
    "no-tflite": "no_tflite",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tiny CAN Intrusion Detection System – end-to-end pipeline"
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a TOML config file. If omitted, looks for "
        "'pipeline.toml' in the current directory.",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Path to a single Car Hacking Dataset CSV (binary classification).",
    )
    parser.add_argument(
        "--dataset-dir",
        default=None,
        help="Path to a directory with all Car Hacking Dataset CSVs "
        "(DoS, Fuzzy, gear, RPM) for multi-class training.",
    )
    parser.add_argument(
        "--max-rows-per-file",
        type=int,
        default=None,
        help="Limit rows loaded per CSV in --dataset-dir mode (for quick experiments).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for exported artifacts (default: ./output).",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=None,
        help="Sliding window size for feature engineering (default: 50).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="Training epochs for the Tiny Neural Network (default: 20).",
    )
    parser.add_argument(
        "--no-tflite",
        action="store_const",
        const=True,
        default=None,
        help="Skip TFLite export (useful when TensorFlow is not installed).",
    )
    parser.add_argument(
        "--export-model",
        default=None,
        choices=["all", "best", "tnn", "lr", "dt"],
        help="Which model(s) to export to C code. "
        "'all' exports all three, 'best' picks the highest-F1 model "
        "(default: tnn).",
    )
    parser.add_argument(
        "--mode",
        default="standard",
        choices=["standard", "dos_only"],
        help="Choose the execution path: 'standard' for a comprehensive pipeline, 'dos_only' for specific DoS optimization."
    )
    cli_args = parser.parse_args()

    # --- Layer 2: config file ---
    config: dict = {}
    config_path = Path(cli_args.config) if cli_args.config else Path("pipeline.toml")
    if config_path.is_file():
        logger.info("Loading config from %s", config_path)
        raw = _load_config(config_path)
        # Normalise TOML keys to argparse dest names.
        for k, v in raw.items():
            dest = _TOML_KEY_MAP.get(k, k.replace("-", "_"))
            config[dest] = v
    elif cli_args.config:
        # User explicitly passed --config but file doesn't exist.
        parser.error(f"Config file not found: {config_path}")

    # --- 3-layer merge: CLI > config > hardcoded defaults ---
    merged = argparse.Namespace()
    for key, fallback in _DEFAULTS.items():
        cli_val = getattr(cli_args, key, None)
        if cli_val is not None:
            # CLI explicitly provided — highest priority.
            setattr(merged, key, cli_val)
        elif key in config:
            # Config file — middle priority.
            setattr(merged, key, config[key])
        else:
            # Hardcoded default — lowest priority.
            setattr(merged, key, fallback)

    return merged


# ------------------------------------------------------------------
# 1. Load / generate data
# ------------------------------------------------------------------
def load_data(args):
    from can_ids.data import (
        generate_synthetic_can_data,
        load_can_dataset,
    )
    from can_ids.data.loader import load_multi_attack_dataset, CLASS_NAMES

    num_classes = 2  # default: binary
    class_names = ["Normal", "Attack"]

    if args.dataset_dir:
        logger.info("Loading multi-attack dataset from %s", args.dataset_dir)
        raw_df = load_multi_attack_dataset(
            args.dataset_dir, max_rows_per_file=args.max_rows_per_file
        )
        num_classes = len(CLASS_NAMES)
        class_names = CLASS_NAMES
    elif args.dataset:
        logger.info("Loading dataset from %s", args.dataset)
        raw_df = load_can_dataset(args.dataset)
    else:
        logger.info("No dataset provided – generating synthetic CAN data")
        raw_df = generate_synthetic_can_data(n_normal=2000, n_attack=400, seed=42)

    logger.info("Raw frames: %d", len(raw_df))
    return raw_df, num_classes, class_names


# ------------------------------------------------------------------
# 2. Pre-process & # 3. Feature engineering
# ------------------------------------------------------------------
def preprocess_features(raw_df, window_size):
    from can_ids.data import preprocess_can_data
    from can_ids.features import build_feature_matrix

    df = preprocess_can_data(raw_df)
    logger.info(
        "After preprocessing: %d frames, %.1f%% attack",
        len(df),
        100 * df["label"].mean(),
    )

    X, y = build_feature_matrix(df, window_size=window_size)
    logger.info("Feature matrix: %s  labels: %s", X.shape, np.bincount(y))
    return X, y


# ------------------------------------------------------------------
# 4. Train / test split + scaling
# ------------------------------------------------------------------
def split_scale(X, y):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    return X_train_s, X_test_s, y_train, y_test, scaler


# ------------------------------------------------------------------
# 5. Train models (only what's needed)
# ------------------------------------------------------------------
def train_models(args, X_train_s, y_train, X_test_s, num_classes, scaler, output_dir):
    from can_ids.models import (
        train_logistic_regression,
        train_decision_tree,
        TinyNeuralNetwork,
    )

    train_all = args.export_model in ("all", "best")
    # TFLite needs TNN even if export target is different
    need_tnn = train_all or args.export_model == "tnn" or not args.no_tflite
    need_lr = train_all or args.export_model == "lr"
    need_dt = train_all or args.export_model == "dt"

    checkpoint_dir = Path(output_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    models: dict = {}

    if need_lr:
        logger.info("Training Logistic Regression …")
        lr_model = train_logistic_regression(X_train_s, y_train)
        models["lr"] = ("Logistic Regression", lr_model, lr_model.predict(X_test_s))

        # Save Logistic Regression model
        lr_checkpoint_path = checkpoint_dir / "tiny_ids_lr_save_model.joblib"
        joblib.dump({"model": lr_model, "scaler": scaler}, lr_checkpoint_path)
        logger.info("Saved Logistic Regression checkpoint to %s", lr_checkpoint_path)

    if need_dt:
        logger.info("Training Decision Tree …")
        dt_model = train_decision_tree(X_train_s, y_train, max_depth=5)
        models["dt"] = ("Decision Tree", dt_model, dt_model.predict(X_test_s))

        # Save Decision Tree model
        dt_checkpoint_path = checkpoint_dir / "tiny_ids_dt_save_model.joblib"
        joblib.dump({"model": dt_model, "scaler": scaler}, dt_checkpoint_path)
        logger.info("Saved Decision Tree checkpoint to %s", dt_checkpoint_path)

    if need_tnn:
        logger.info("Training Tiny Neural Network (%d classes) …", num_classes)
        tnn = TinyNeuralNetwork(input_dim=X_train_s.shape[1], num_classes=num_classes)
        tnn.fit(X_train_s, y_train, epochs=args.epochs, verbose=0, balance_classes=True)
        models["tnn"] = ("Tiny Neural Network", tnn, tnn.predict(X_test_s))

        # Save Tiny Neural Network model
        tnn_checkpoint_path = checkpoint_dir / "tiny_ids_tnn_save_model.joblib"
        joblib.dump({"model": tnn, "scaler": scaler}, tnn_checkpoint_path)
        logger.info("Saved Tiny Neural Network checkpoint to %s", tnn_checkpoint_path)

    return models


# ------------------------------------------------------------------
# 6. Evaluate trained models + comparison table
# ------------------------------------------------------------------
def evaluate(models, y_test, X_test_s, class_names):

    for key, (name, model, y_pred) in models.items():
        _report(name, y_pred, y_test, class_names)

    if "tnn" in models:
        models["tnn"][1].summary()

    if len(models) > 1:
        _model_comparison_table(models, y_test, X_test_s)


# ------------------------------------------------------------------
# 7. Quantize Tiny Neural Network
# ------------------------------------------------------------------
def quantization(models):
    if "tnn" in models:
        from can_ids.models import ModelQuantizer

        logger.info("Quantizing Tiny Neural Network (INT8) …")
        quantizer = ModelQuantizer(model=models["tnn"][1], bits=8)
        quantizer.quantize()
        logger.info(
            "Quantized model footprint: %d bytes", quantizer.memory_footprint_bytes()
        )


# ------------------------------------------------------------------
# 8. TFLite export
# ------------------------------------------------------------------
def tflite_export(args, models, X_train_s, X_test_s, y_test, class_names, output_dir):
    if not args.no_tflite and "tnn" in models:
        try:
            from can_ids.models import export_to_tflite, save_tflite_model
            from can_ids.models.export import run_tflite_inference

            tnn = models["tnn"][1]
            logger.info("Exporting to TFLite (full-integer quantization) …")
            tflite_bytes = export_to_tflite(tnn, X_train_s[:200])
            tflite_path = save_tflite_model(tflite_bytes, output_dir / "tiny_ids_model")
            logger.info("TFLite model saved to %s", tflite_path)

            # Validate TFLite inference
            logger.info("Validating TFLite inference …")
            tflite_preds = run_tflite_inference(tflite_bytes, X_test_s)
            _report("TFLite (host validation)", tflite_preds, y_test, class_names)

        except (ImportError, RuntimeError, OSError) as exc:
            logger.warning("TFLite export/validation failed: %s", exc)
    else:
        logger.info("TFLite export skipped (--no-tflite)")


# ------------------------------------------------------------------
# 9. C/C++ export
# ------------------------------------------------------------------
def c_export(args, models, y_test, output_dir):
    from can_ids.deploy import export_model_to_c

    export_targets = _resolve_export_targets(args.export_model, models, y_test)

    logger.info("Exporting C code for: %s", ", ".join(export_targets))
    for model_type in export_targets:
        name, model_obj, _ = models[model_type]
        header, source = export_model_to_c(
            model_obj, model_type, output_dir, model_name="tiny_ids"
        )
        logger.info("  %s → %s, %s", name, header.name, source.name)

def run_dos_specific_pipeline(args, output_dir: Path):
    """
    End-to-end pipeline specifically optimized for DoS Attack Detection.
    Uses Decision Tree as the priority model.
    """
    import json
    from can_ids.features import build_dos_feature_matrix, build_dos_tnn_feature_matrix
    from can_ids.data.loader import load_can_dataset
    from can_ids.data import preprocess_can_data
    from can_ids.models import train_decision_tree, TinyNeuralNetwork
    from can_ids.models.compress import export_decision_tree_structure
    from can_ids.deploy import export_dos_model_to_c
    from can_ids.models.export import export_to_tflite, save_tflite_model
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, accuracy_score, f1_score

    logger.info("=== Starting Integrated DoS Pipeline (DT 8-feat + TNN 12-feat) ===")

    # =========================================================
    # 1. LOAD DATA & GENERAL PREPROCESSING
    # =========================================================
    if not args.dataset:
        logger.error("Please provide the --dataset path to the DoS_dataset.csv file.")
        return
    
    logger.info("Loading DoS dataset from %s", args.dataset)
    raw_df = load_can_dataset(args.dataset)
    df = preprocess_can_data(raw_df)
    
    window_size = args.window_size if args.window_size else 50
    dos_output_dir = output_dir / "dos_only"
    dos_output_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================
    # PATH A: DECISION TREE (8 FEATURES)
    # =========================================================
    logger.info("\n--- [Path A] DECISION TREE (8 Features) ---")
    logger.info("Extracting 8 features...")
    X8, y8 = build_dos_feature_matrix(df, window_size=window_size)
    X8_train, X8_test, y8_train, y8_test = train_test_split(X8, y8, test_size=0.2, random_state=42, stratify=y8)

    logger.info("Training Decision Tree...")
    dt_model = train_decision_tree(X8_train, y8_train, max_depth=5)
    
    y8_pred = dt_model.predict(X8_test)
    dt_acc = accuracy_score(y8_test, y8_pred)
    dt_f1 = f1_score(y8_test, y8_pred, average='weighted')
    
    print(f"\n{'=' * 50}\n  DoS Decision Tree Performance\n{'=' * 50}")
    print(classification_report(y8_test, y8_pred, target_names=["Normal", "DoS"], digits=4))

    # Export DT
    edt = export_decision_tree_structure(dt_model)
    dt_size = edt.memory_footprint_bytes()
    logger.info("Pruned DT Footprint: %d bytes", dt_size)
    n_features_dt = X8_train.shape[1]
    header_dt, source_dt = export_dos_model_to_c(dt_model, "dt", dos_output_dir, model_name="dos_ids", window_size = window_size, n_features = n_features_dt)


    # =========================================================
    # PATH B: TINY NEURAL NETWORK (12 FEATURES)
    # =========================================================
    logger.info("\n--- [Path B] TINY NEURAL NETWORK (12 Features) ---")
    logger.info("Extracting 12 extended features...")
    X12, y12 = build_dos_tnn_feature_matrix(df, window_size=window_size)
    X12_train, X12_test, y12_train, y12_test = train_test_split(X12, y12, test_size=0.2, random_state=42, stratify=y12)

    logger.info("Scaling features for TNN...")
    scaler = StandardScaler()
    X12_train_s = scaler.fit_transform(X12_train)
    X12_test_s = scaler.transform(X12_test)

    logger.info("Training Tiny Neural Network...")
    tnn_model = TinyNeuralNetwork(input_dim=12, num_classes=2)
    tnn_model.fit(X12_train_s, y12_train, epochs=args.epochs if args.epochs else 20, verbose=0, balance_classes=True)
    
    y12_pred = tnn_model.predict(X12_test_s)
    tnn_acc = accuracy_score(y12_test, y12_pred)
    tnn_f1 = f1_score(y12_test, y12_pred, average='weighted')

    print(f"\n{'=' * 50}\n  DoS Tiny Neural Network Performance\n{'=' * 50}")
    print(classification_report(y12_test, y12_pred, target_names=["Normal", "DoS"], digits=4))

    # Export TNN ra TFLite & C Code
    logger.info("Exporting TNN to TFLite and C Code...")
    
    tflite_filename = "N/A"
    if getattr(args, "no_tflite", False) is False:
        tflite_bytes = export_to_tflite(tnn_model, X12_train_s[:200], quantize=True)
        tflite_path = save_tflite_model(tflite_bytes, dos_output_dir / "dos_ids_tnn")
        tflite_filename = tflite_path.name
        
    n_features_tnn = X12_train_s.shape[1]
    header_tnn, source_tnn = export_dos_model_to_c(tnn_model, "tnn", dos_output_dir, model_name="dos_ids", window_size = window_size, n_features = n_features_tnn, scaler=scaler)

    # =========================================================
    # 3. EXPORT COMMON METADATA FOR BOTH MODELS
    # =========================================================
    logger.info("\nGenerating Combined Metadata JSON...")
    
    metadata = {
        "project": "tiny-can-ids-dos-only",
        "version": "3.0",
        "task": "Binary Classification (Normal vs DoS)",
        "models": {
            "decision_tree": {
                "model_name": "dos_ids_dt",
                "model_type": "Decision Tree (Pruned)",
                "validation_result": {
                    "accuracy (> 80%)": round(dt_acc, 4),
                    "f1_score_weighted (> 80%)": round(dt_f1, 4),
                },
                "parameters": {
                    "window_size_samples": window_size,
                    "window_size_ms": window_size * 1, 
                    "max_depth": 5,
                    "tree_nodes": int(dt_model.tree_.node_count),
                    "memory_footprint_bytes": int(dt_size)
                },
                "feature_names": [
                    "mean_inter_arrival_time",
                    "std_inter_arrival_time",
                    "message_rate",
                    "dominant_id_frequency",
                    "id_entropy",
                    "min_inter_arrival_time",
                    "high_priority_id_rate",
                    "max_consecutive_identical_ids"
                ],
                "api_spec": {
                    "public_api": "void dos_ids_dt_process_window(const CAN_Frame_t *window, int *result);",
                    "output_mapping": "*result = 0 (Normal) | 1 (DoS Attack)",
                    "artifacts_generated": [header_dt.name, source_dt.name]
                }
            },
            "tiny_neural_network": {
                "model_name": "dos_ids_tnn",
                "model_type": "Tiny Neural Network (INT8 Quantized)",
                "validation_result": {
                    "accuracy (> 80%)": round(tnn_acc, 4),
                    "f1_score_weighted (> 80%)": round(tnn_f1, 4),
                },
                "parameters": {
                    "window_size_samples": window_size,
                    "window_size_ms": window_size * 1,
                    "epochs": args.epochs if args.epochs else 20,
                    "requires_scaling": True,
                    "scaler_file": "dos_ids_tnn_scaler.h"
                },
                "feature_names": [
                    "mean_inter_arrival_time",
                    "std_inter_arrival_time",
                    "min_inter_arrival_time",
                    "max_inter_arrival_time",
                    "message_rate",
                    "dominant_id_frequency",
                    "id_entropy",
                    "high_priority_id_rate",
                    "mean_hamming_weight",
                    "data_change_rate",
                    "id_gaps",
                    "skewness_inter_arrival_time"
                ],
                "api_spec": {
                    "public_api": "void dos_ids_tnn_process_window(const CAN_Frame_t *window, int *result);",
                    "output_mapping": "*result = 0 (Normal) | 1 (DoS Attack)",
                    "artifacts_generated": [header_tnn.name, source_tnn.name, tflite_filename]
                }
            }
        }
    }

    metadata_path = dos_output_dir / "dos_ids_metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)
    
    logger.info("  -> Generated: %s", metadata_path.name)
    logger.info("\n=== Integrated DoS Pipeline Complete. Artifacts in: %s ===", dos_output_dir.resolve())


def main() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- DoS_ONLY PIPELINE ---
    if getattr(args, "mode", "standard") == "dos_only":
        run_dos_specific_pipeline(args, output_dir)
        return
    
    # --- STANDARD PIPELINE ---
    raw_df, num_classes, class_names = load_data(args)
    X, y = preprocess_features(raw_df, args.window_size)
    X_train_s, X_test_s, y_train, y_test, scaler = split_scale(X, y)

    models = train_models(
        args,
        X_train_s,
        y_train,
        X_test_s,
        num_classes,
        scaler,
        output_dir,
    )
    evaluate(models, y_test, X_test_s, class_names)

    quantization(models)
    tflite_export(args, models, X_train_s, X_test_s, y_test, class_names, output_dir)
    c_export(args, models, y_test, output_dir)

    logger.info("Pipeline complete. Artifacts in: %s", output_dir.resolve())


def _resolve_export_targets(
    choice: str,
    models: dict,
    y_test: np.ndarray,
) -> list[str]:
    """Map --export-model choice to a list of model type keys."""
    if choice == "all":
        return ["tnn", "lr", "dt"]
    if choice == "best":
        best_key = max(
            models,
            key=lambda k: f1_score(y_test, models[k][2], average="weighted"),
        )
        return [best_key]
    return [choice]


def _model_comparison_table(
    models: dict,
    y_test: np.ndarray,
    X_test_s: np.ndarray,
) -> None:
    """Print a comparison table of all trained models."""
    from can_ids.models.compress import (
        quantize_logistic_regression,
        export_decision_tree_structure,
        ModelQuantizer,
    )

    print(f"\n{'=' * 65}")
    print("  Model Comparison")
    print("=" * 65)
    print(f"  {'Model':<25s} {'Acc':>8s} {'F1':>8s} {'Size(B)':>10s}")
    print(f"  {'-' * 25} {'-' * 8} {'-' * 8} {'-' * 10}")

    rows = []
    for key, (name, model_obj, y_pred) in models.items():
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average="weighted")
        # Estimate C deployment size
        if key == "tnn":
            q = ModelQuantizer(model=model_obj, bits=8)
            q.quantize()
            size = q.memory_footprint_bytes()
        elif key == "lr":
            qlr = quantize_logistic_regression(model_obj, bits=8)
            size = qlr.memory_footprint_bytes()
        elif key == "dt":
            edt = export_decision_tree_structure(model_obj)
            size = edt.memory_footprint_bytes()
        else:
            size = 0
        rows.append((name, acc, f1, size))

    # Sort by F1 descending
    rows.sort(key=lambda r: r[2], reverse=True)
    for name, acc, f1, size in rows:
        print(f"  {name:<25s} {acc:>8.4f} {f1:>8.4f} {size:>10d}")
    print()


def _report(
    name: str,
    y_pred: np.ndarray,
    y_true: np.ndarray,
    class_names: list[str] | None = None,
) -> None:
    if class_names is None:
        class_names = ["Normal", "Attack"]
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print("=" * 60)
    print(classification_report(y_true, y_pred, target_names=class_names, digits=4))


if __name__ == "__main__":
    main()
