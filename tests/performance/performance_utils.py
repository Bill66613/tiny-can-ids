import numpy as np
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
BASELINE_FILE = BASE_DIR / "baseline.json"

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
    if not BASELINE_FILE.exists():
        with open(BASELINE_FILE, "w") as f:
            json.dump({}, f)

    with open(BASELINE_FILE, "r") as f:
        data = json.load(f)

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
    
    with open(BASELINE_FILE, "w") as f:
        json.dump(data, f, indent=4)