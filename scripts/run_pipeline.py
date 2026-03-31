"""End-to-end CAN bus intrusion detection pipeline.

Usage::

    python scripts/run_pipeline.py [--output-dir OUTPUT_DIR]

    # Train on all 4 attack types from the Car Hacking Dataset:
    python scripts/run_pipeline.py --dataset-dir path/to/Car-Hacking-Dataset

Steps:

1. Generate (or load) a CAN bus dataset.
2. Pre-process frames.
3. Engineer features.
4. Train Logistic Regression, Decision Tree, and Tiny Neural Network.
5. Evaluate all models on a held-out test set.
6. Quantize the Tiny Neural Network (INT8).
7. Export the Tiny Neural Network to TFLite.
8. Validate TFLite inference.
9. Export quantized weights as a C header and inference C source.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import classification_report
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
    # 5. Train models
    # ------------------------------------------------------------------
    from can_ids.models import (
        train_logistic_regression,
        train_decision_tree,
        TinyNeuralNetwork,
    )

    logger.info("Training Logistic Regression …")
    lr_model = train_logistic_regression(X_train_s, y_train)
    _report("Logistic Regression", lr_model.predict(X_test_s), y_test, class_names)

    logger.info("Training Decision Tree …")
    dt_model = train_decision_tree(X_train_s, y_train, max_depth=5)
    _report("Decision Tree", dt_model.predict(X_test_s), y_test, class_names)

    logger.info("Training Tiny Neural Network (%d classes) …", num_classes)
    tnn = TinyNeuralNetwork(input_dim=X_train_s.shape[1], num_classes=num_classes)
    tnn.fit(X_train_s, y_train, epochs=args.epochs, verbose=0)
    _report("Tiny Neural Network", tnn.predict(X_test_s), y_test, class_names)
    tnn.summary()

    # ------------------------------------------------------------------
    # 6. Quantize Tiny Neural Network
    # ------------------------------------------------------------------
    from can_ids.models import ModelQuantizer

    logger.info("Quantizing Tiny Neural Network (INT8) …")
    quantizer = ModelQuantizer(model=tnn, bits=8)
    quantizer.quantize()
    logger.info(
        "Quantized model footprint: %d bytes", quantizer.memory_footprint_bytes()
    )

    # ------------------------------------------------------------------
    # 7. TFLite export
    # ------------------------------------------------------------------
    if not args.no_tflite:
        try:
            from can_ids.models import export_to_tflite, save_tflite_model
            from can_ids.models.export import run_tflite_inference

            logger.info("Exporting to TFLite (full-integer quantization) …")
            tflite_bytes = export_to_tflite(tnn, X_train_s[:200])
            tflite_path = save_tflite_model(tflite_bytes, output_dir / "tiny_ids_model")
            logger.info("TFLite model saved to %s", tflite_path)

            # ------------------------------------------------------------------
            # 8. Validate TFLite inference
            # ------------------------------------------------------------------
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
    from can_ids.deploy import export_weights_to_c_header, generate_inference_c_code

    logger.info("Exporting C/C++ model files …")
    header_path = export_weights_to_c_header(quantizer, output_dir / "tiny_ids_weights")
    c_path = generate_inference_c_code(quantizer, output_dir / "tiny_ids_inference")
    logger.info("C header: %s", header_path)
    logger.info("C source: %s", c_path)

    logger.info("Pipeline complete.  Artefacts in: %s", output_dir.resolve())


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
