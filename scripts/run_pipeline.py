"""End-to-end CAN bus intrusion detection pipeline.

Usage::

    python scripts/run_pipeline.py [--output-dir OUTPUT_DIR]

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

from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
)
logger = logging.getLogger("pipeline")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tiny CAN Intrusion Detection System – end-to-end pipeline"
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
        default="output",
        help="Directory for exported artifacts (default: ./output).",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=50,
        help="Sliding window size for feature engineering (default: 50).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=20,
        help="Training epochs for the Tiny Neural Network (default: 20).",
    )
    parser.add_argument(
        "--no-tflite",
        action="store_true",
        help="Skip TFLite export (useful when TensorFlow is not installed).",
    )
    parser.add_argument(
        "--export-model",
        default="tnn",
        choices=["all", "best", "tnn", "lr", "dt"],
        help="Which model(s) to export to C code. "
        "'all' exports all three, 'best' picks the highest-F1 model "
        "(default: tnn).",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load / generate data
    # ------------------------------------------------------------------
    from can_ids.data import (
        generate_synthetic_can_data,
        load_can_dataset,
        preprocess_can_data,
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

    # ------------------------------------------------------------------
    # 2. Pre-process
    # ------------------------------------------------------------------
    df = preprocess_can_data(raw_df)
    logger.info(
        "After preprocessing: %d frames, %.1f%% attack",
        len(df),
        100 * df["label"].mean(),
    )

    # ------------------------------------------------------------------
    # 3. Feature engineering
    # ------------------------------------------------------------------
    from can_ids.features import build_feature_matrix

    X, y = build_feature_matrix(df, window_size=args.window_size)
    logger.info("Feature matrix: %s  labels: %s", X.shape, np.bincount(y))

    # ------------------------------------------------------------------
    # 4. Train / test split + scaling
    # ------------------------------------------------------------------
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # ------------------------------------------------------------------
    # 5. Train models (only what's needed)
    # ------------------------------------------------------------------
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

    models: dict = {}

    if need_lr:
        logger.info("Training Logistic Regression …")
        lr_model = train_logistic_regression(X_train_s, y_train)
        models["lr"] = ("Logistic Regression", lr_model, lr_model.predict(X_test_s))

    if need_dt:
        logger.info("Training Decision Tree …")
        dt_model = train_decision_tree(X_train_s, y_train, max_depth=5)
        models["dt"] = ("Decision Tree", dt_model, dt_model.predict(X_test_s))

    if need_tnn:
        logger.info("Training Tiny Neural Network (%d classes) …", num_classes)
        tnn = TinyNeuralNetwork(input_dim=X_train_s.shape[1], num_classes=num_classes)
        tnn.fit(X_train_s, y_train, epochs=args.epochs, verbose=0, balance_classes=True)
        models["tnn"] = ("Tiny Neural Network", tnn, tnn.predict(X_test_s))

    # ------------------------------------------------------------------
    # 6. Evaluate trained models + comparison table
    # ------------------------------------------------------------------
    for key, (name, model, y_pred) in models.items():
        _report(name, y_pred, y_test, class_names)

    if "tnn" in models:
        models["tnn"][1].summary()

    if len(models) > 1:
        _model_comparison_table(models, y_test, X_test_s)

    # ------------------------------------------------------------------
    # 7. Quantize Tiny Neural Network
    # ------------------------------------------------------------------
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
    from can_ids.deploy import export_model_to_c

    export_targets = _resolve_export_targets(args.export_model, models, y_test)

    logger.info("Exporting C code for: %s", ", ".join(export_targets))
    for model_type in export_targets:
        name, model_obj, _ = models[model_type]
        header, source = export_model_to_c(
            model_obj, model_type, output_dir, model_name="tiny_ids"
        )
        logger.info("  %s → %s, %s", name, header.name, source.name)

    # ------------------------------------------------------------------
    # 10. Deployment summary
    # ------------------------------------------------------------------
    logger.info("Pipeline complete.  Artefacts in: %s", output_dir.resolve())


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
