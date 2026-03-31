# tiny-can-ids

TinyML-based CAN bus intrusion detection system for resource-constrained
automotive embedded systems (TCUs, MCUs).

## Overview

This project implements a lightweight machine learning pipeline for detecting
intrusions on a Controller Area Network (CAN) bus. The pipeline covers:

1. **Data loading & preprocessing** – supports the [Car Hacking Dataset](https://ocslab.hksecurity.net/Datasets/car-hacking-dataset) and synthetic data generation for testing.
2. **Feature engineering** – extracts ID-frequency, inter-arrival timing, and payload statistics from CAN frames using a sliding-window approach.
3. **Lightweight model training** – Logistic Regression, Decision Tree, and a Tiny Neural Network (< 50 KB when quantized).
4. **Model compression** – post-training INT8 symmetric quantization and cost-complexity tree pruning.
5. **TFLite export** – full-integer quantization and conversion to `.tflite` format for embedded inference.
6. **C/C++ deployment** – generates a ``.h`` header with quantized weights and a ``.c`` file with a self-contained `ids_predict()` inference function ready for ARM Cortex-M toolchains.

## Project Structure

```
can_ids/
├── data/
│   └── loader.py          # Dataset loading and preprocessing
├── features/
│   └── engineer.py        # Feature extraction
├── models/
│   ├── classifiers.py     # LR, Decision Tree, Tiny NN
│   ├── compress.py        # INT8 quantization, tree pruning
│   └── export.py          # TFLite conversion and inference
└── deploy/
    └── c_export.py        # C/C++ header and source generation

scripts/
└── run_pipeline.py        # End-to-end demo pipeline

tests/
├── test_data.py
├── test_features.py
├── test_models.py
└── test_export.py
```

## Quick Start

```bash
pip install -r requirements.txt

# Run the full pipeline with synthetic data (binary: normal vs attack)
python scripts/run_pipeline.py --output-dir output/

# Run with a single dataset file (binary classification)
python scripts/run_pipeline.py --dataset path/to/can_dataset.csv --output-dir output/

# Run with the full Car Hacking Dataset (multi-class: Normal, DoS, Fuzzy, Gear, RPM)
python scripts/run_pipeline.py --dataset-dir "path/to/Car-Hacking Dataset" --output-dir output/

# Quick experiment with limited rows per file
python scripts/run_pipeline.py --dataset-dir "path/to/Car-Hacking Dataset" --max-rows-per-file 50000 --output-dir output/
```

## Testing

```bash
pytest tests/
```

## Embedded Deployment

After running the pipeline, the `output/` directory contains:

- `tiny_ids_model.tflite` – quantized TFLite model for on-device inference.
- `tiny_ids_weights.h` – C header with INT8 weight arrays.
- `tiny_ids_inference.c` – C source with `tiny_ids_predict()` function.

Compile the C files with your embedded toolchain:

```bash
arm-none-eabi-gcc -O2 -mthumb -mcpu=cortex-m4 \
    tiny_ids_inference.c -lm -o tiny_ids.elf
```

## Memory Footprint

| Model               | Size (FP32) | Size (INT8) |
|---------------------|-------------|-------------|
| Tiny NN (32-16-1)   | ~3 KB       | ~0.8 KB     |
| Decision Tree (d=5) | ~2 KB       | N/A         |
| Logistic Regression | ~1 KB       | N/A         |
