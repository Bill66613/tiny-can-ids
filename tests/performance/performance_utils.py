import os
import numpy as np
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
BASELINE_FILE = BASE_DIR / "baseline.json"

ACTIVE_DIR = os.getenv("PERF_BASELINE_DIR", str(BASE_DIR / ".perf_cache"))
ACTIVE_BASELINE = Path(ACTIVE_DIR) / "active_baseline.json"

def _load_data():
    Path(ACTIVE_DIR).mkdir(parents=True, exist_ok=True)
    # Prioritize retrieving from the Active Cache first; if it's not there, retrieve from the Reference Repo.
    if ACTIVE_BASELINE.exists():
        with open(ACTIVE_BASELINE, "r") as f:
            return json.load(f)
    elif BASELINE_FILE.exists():
        with open(BASELINE_FILE, "r") as f:
            return json.load(f)
    return {}

def calculate_thresholds(history: list) -> tuple:
    """Calculate the threshold μ + 2σ from the test history."""
    if not history: return 0, 0
    mu = np.mean(history)
    sigma = np.std(history)
    return mu, mu + 2 * sigma

def check_performance_regression(test_name: str, current_value: float):
    """
    Compare the current value with the historical threshold.
    If it exceeds μ + 2σ -> Test fails.
    """
    data = _load_data()

    history = data.get(test_name, [])
    
    if len(history) >= 5: # Only begin checking after you have at least 5 samples.
        mu, threshold = calculate_thresholds(history)
        if current_value > threshold:
            raise AssertionError(
                f"REGRESSION DETECTED in {test_name}!\n"
                f"Current: {current_value:.4f} | Limit: {threshold:.4f} (μ={mu:.4f})"
            )

    # Update history (keeps up to the 20 most recent records)
    history.append(current_value)
    data[test_name] = history[-20:]
    
    with open(ACTIVE_BASELINE, "w") as f:
        json.dump(data, f, indent=4)