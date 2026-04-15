import joblib
import os
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from can_ids.data.loader import load_can_dataset, preprocess_can_data
from can_ids.features.engineer import build_feature_matrix
from can_ids.models import ModelQuantizer

def load_existing_model(model_path='save_models/tiny_ids_tnn_checkpoint.joblib'):
    """Load both the model and scaler from the checkpoint file."""
    if os.path.exists(model_path):
        print(f"--- Loading existing model checkpoint from {model_path} ---")
        checkpoint = joblib.load(model_path)
        model = checkpoint['model']
        scaler = checkpoint['scaler']
        return model, scaler
    else:
        print("Error: No checkpoint found. Please train the model first.")
        return None, None

def main():
    # 1. Path configuration
    MODEL_PATH = 'save_models/tiny_ids_tnn_checkpoint.joblib'
    DATA_PATH = 'dataset/DoS_dataset.csv'  
    
    # 2. Loading the model and scaler (Way 2: Joblib)
    model, scaler = load_existing_model(MODEL_PATH)
    if model is None:
        return

    # 3. Quantify the model (INT8) to fit the Quantization step in the Pipeline.
    print("--- Quantizing Model (INT8) ---")
    quantizer = ModelQuantizer(model=model, bits=8)
    quantizer.quantize()

    # 4. Load and preprocess data
    print("--- Loading and Preprocessing Data ---")
    try:
        raw_data = load_can_dataset(DATA_PATH)
    except FileNotFoundError:
        print(f"Data file {DATA_PATH} not found. Using synthetic data.")
        from can_ids.data.loader import generate_synthetic_can_data
        raw_data = generate_synthetic_can_data(n_normal=2000, n_attack=400, seed=42)

    df_processed = preprocess_can_data(raw_data)
    
    # 5. Feature extraction (Generated a total of 20,971 windows)
    X, y_all = build_feature_matrix(df_processed, window_size=50)
    print(f"Total feature matrix shape: {X.shape}")

    # 6. EXTRACT DATA TO GET SUPPORT = 4,195
    # Use the correct parameters of run_pipeline.py: test_size=0.2, random_state=42
    _, X_test, _, y_test = train_test_split(
        X, y_all, test_size=0.2, random_state=42, stratify=y_all
    )

    # 7. Standardize the test set and perform predictions.
    print(f"--- Scaling & Inference (Support: {len(y_test)}) ---")
    X_test_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_test_scaled)
    
    # 8. Display comparison results
    print("\nDetection Results (Matching Pipeline Support):")
    print(classification_report(y_test, y_pred, target_names=['Normal', 'Attack'], digits=4))

if __name__ == "__main__":
    main()