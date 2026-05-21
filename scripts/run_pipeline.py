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
import json

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
    "tflite": False,
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
    "tflite": "tflite",
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
        "--tflite",
        action="store_true",
        help="Export to TFLite (forces Tiny Neural Network training).",
    )
    parser.add_argument(
        "--export-model",
        default=None,
        choices=["all", "best", "tnn", "lr", "dt"],
        help="Which model(s) to export to C code. "
        "'all' exports all three, 'best' picks the highest-F1 model "
        "(default: tnn).",
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
def preprocess_features(args, raw_df, window_size):
    from can_ids.data import preprocess_can_data
    from can_ids.features import build_feature_matrix, build_dos_feature_matrix, build_dos_tnn_feature_matrix

    df = preprocess_can_data(raw_df)
    logger.info(
        "After preprocessing: %d frames, %.1f%% attack",
        len(df),
        100 * df["label"].mean(),
    )

    if args.dataset and "dataset/DoS_dataset.csv" in args.dataset:
        if args.export_model == "dt":
            X, y = build_dos_feature_matrix(df, window_size= window_size)
        elif args.export_model == "tnn":
            X, y = build_dos_tnn_feature_matrix(df, window_size= window_size)

    else:
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
    return X_train, X_test, X_train_s, X_test_s, y_train, y_test, scaler


# ------------------------------------------------------------------
# 5. Train models (only what's needed)
# ------------------------------------------------------------------
def train_models(args, X_train, X_train_s, y_train, X_test, X_test_s, num_classes, scaler, output_dir):
    from can_ids.models import (
        train_logistic_regression,
        train_decision_tree,
        TinyNeuralNetwork,
    )

    train_all = args.export_model in ("all", "best")
    # TFLite needs TNN even if export target is different
    need_tnn = train_all or args.export_model == "tnn" or args.tflite
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
        dt_model = train_decision_tree(X_train, y_train, max_depth=5)
        models["dt"] = ("Decision Tree", dt_model, dt_model.predict(X_test))

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
    if args.tflite and "tnn" in models:
        try:
            from can_ids.models import export_to_tflite, save_tflite_model
            from can_ids.models.export import run_tflite_inference

            tnn = models["tnn"][1]
            logger.info("Exporting to TFLite (full-integer quantization) …")
            tflite_bytes = export_to_tflite(tnn, X_train_s[:200])
            is_dos = args.dataset and "dataset/DoS_dataset.csv" in args.dataset
            file_prefix = "dos_ids_tnn_model" if is_dos else "tiny_ids_model"
            
            tflite_path = save_tflite_model(tflite_bytes, output_dir / file_prefix)
            logger.info("TFLite model saved to %s", tflite_path)

            # Validate TFLite inference
            logger.info("Validating TFLite inference …")
            tflite_preds = run_tflite_inference(tflite_bytes, X_test_s)
            _report("TFLite (host validation)", tflite_preds, y_test, class_names)

        except (ImportError, RuntimeError, OSError) as exc:
            logger.warning("TFLite export/validation failed: %s", exc)
    else:
        logger.info("TFLite export skipped (missing --tflite flag)")


# ------------------------------------------------------------------
# 9. C/C++ export
# ------------------------------------------------------------------
def c_export(args, models, y_test, output_dir):
    from can_ids.deploy import export_model_to_c, export_dos_model_to_c

    export_targets = _resolve_export_targets(args.export_model, models, y_test)

    logger.info("Exporting C code for: %s", ", ".join(export_targets))
    for model_type in export_targets:
        name, model_obj, _ = models[model_type]

        if args.dataset and "dataset/DoS_dataset.csv" in args.dataset:
            header, source = export_dos_model_to_c(
                model_obj, 
                model_type, 
                output_dir, 
                model_name="dos_ids",
                window_size=args.window_size,
                n_features=model_obj.input_dim if hasattr(model_obj, 'input_dim') else 8
            )
        else:
            header, source = export_model_to_c(
                model_obj, model_type, output_dir, model_name="tiny_ids"
            )
        logger.info("  %s → %s, %s", name, header.name, source.name)

def main() -> None:
    args = _parse_args()

    is_dos = args.dataset and "DoS_dataset.csv" in args.dataset
    output_dir = Path(args.output_dir) / "dos_only" if is_dos else Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # --- STANDARD PIPELINE ---
    raw_df, num_classes, class_names = load_data(args)
    X, y = preprocess_features(args, raw_df, args.window_size)
    
    n_features = X.shape[1]
    X_train, X_test, X_train_s, X_test_s, y_train, y_test, scaler = split_scale(X, y)

    models = train_models(
        args,
        X_train,
        X_train_s,
        y_train,
        X_test,
        X_test_s,
        num_classes,
        scaler,
        output_dir,
    )
    evaluate(models, y_test, X_test_s, class_names)

    quantization(models)
    tflite_export(args, models, X_train_s, X_test_s, y_test, class_names, output_dir)
    c_export(args, models, y_test, output_dir)

    if is_dos:
        _export_dos_metadata(args, models, y_test, scaler, output_dir, n_features)

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

def _export_dos_metadata(args, models, y_test, scaler, output_dir, n_features):
    from can_ids.models.compress import export_decision_tree_structure

    metadata_path = output_dir / "dos_ids_metadata.json"

    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except json.JSONDecodeError:
            metadata = None
    else:
        metadata = None

    if metadata is None:
        metadata = {
            "project": "tiny-can-ids-dos-only",
            "version": "3.0",
            "task": "Binary Classification (Normal vs DoS)",
            "models": {}
        }

    if "models" not in metadata:
        metadata["models"] = {}

    for key, (name, model_obj, y_pred) in models.items():
        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, average="weighted")
        
        model_info = {
            "model_name": f"dos_ids_{key}",
            "validation_result": {
                "accuracy (> 80%)": round(acc, 4),
                "f1_score_weighted (> 80%)": round(f1, 4)
            },
            "parameters": {
                "window_size_samples": args.window_size,
                "window_size_ms": args.window_size * 1,
                "number_of_features": n_features,
            }
        }
        
        if key == "dt":
            model_info["model_type"] = "Decision Tree (Pruned)"
            edt = export_decision_tree_structure(model_obj)
            model_info["parameters"]["max_depth"] = 5
            model_info["parameters"]["tree_nodes"] = int(model_obj.tree_.node_count)
            model_info["parameters"]["memory_footprint_bytes"] = int(edt.memory_footprint_bytes())
            model_info["feature_names"] = [
                "mean_inter_arrival_time", "std_inter_arrival_time", "message_rate",
                "dominant_id_frequency", "id_entropy", "min_inter_arrival_time",
                "high_priority_id_rate", "max_consecutive_identical_ids"
            ]
            model_info["api_spec"] = {
                "public_api": "void dos_ids_dt_process_window(const CAN_Frame_t *window, int *result);",
                "output_mapping": "*result = 0 (Normal) | 1 (DoS Attack)",
                "artifacts_generated": ["dos_ids_dt_weights.h", "dos_ids_dt_inference.c"]
            }
            
        elif key == "tnn":
            model_info["model_type"] = "Tiny Neural Network (INT8 Quantized)"
            model_info["parameters"]["epochs"] = args.epochs
            model_info["parameters"]["requires_scaling"] = True
            model_info["parameters"]["scaler_file"] = "dos_ids_tnn_scaler.h"
            model_info["feature_names"] = [
                "mean_inter_arrival_time", "std_inter_arrival_time", "min_inter_arrival_time",
                "max_inter_arrival_time", "message_rate", "dominant_id_frequency",
                "id_entropy", "high_priority_id_rate", "mean_hamming_weight",
                "data_change_rate", "id_gaps", "skewness_inter_arrival_time"
            ]
            model_info["api_spec"] = {
                "public_api": "void dos_ids_tnn_process_window(const CAN_Frame_t *window, int *result);",
                "output_mapping": "*result = 0 (Normal) | 1 (DoS Attack)",
                "artifacts_generated": ["dos_ids_tnn_weights.h", "dos_ids_tnn_inference.c", "dos_ids_tnn_model.tflite"]
            }
            
            scaler_path = output_dir / "dos_ids_tnn_scaler.h"
            means = ", ".join([f"{m:.8f}f" for m in scaler.mean_])
            scales = ", ".join([f"{s:.8f}f" for s in scaler.scale_])
            content = f"/* Auto-generated Scaler Data - Do not edit */\n#ifndef DOS_IDS_TNN_SCALER_H\n#define DOS_IDS_TNN_SCALER_H\n\n" \
                      f"static const float dos_ids_tnn_scaler_mean[{len(scaler.mean_)}] = {{ {means} }};\n" \
                      f"static const float dos_ids_tnn_scaler_scale[{len(scaler.scale_)}] = {{ {scales} }};\n\n" \
                      f"#endif /* DOS_IDS_TNN_SCALER_H */\n"
            scaler_path.write_text(content)

        metadata["models"][key] = model_info

    with open(output_dir / "dos_ids_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4)

if __name__ == "__main__":
    main()
