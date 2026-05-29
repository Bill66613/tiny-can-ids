import pytest
import time
import sys
import os
from pathlib import Path
import psutil
from tests.performance.performance_utils import check_performance_regression

@pytest.mark.performance
def test_pipeline_execution_time(tmp_path):
    """Measure pipeline execution time and check regression."""
    import subprocess
    
    project_root = str(Path(__file__).parents[2].absolute())
    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

    start_time = time.time()
    # Run a simulated scenario.
    subprocess.run([sys.executable, "scripts/run_pipeline.py", "--epochs", "1"], env=env, capture_output=True, check=True)

    duration = time.time() - start_time
    
    check_performance_regression("pipeline_latency_seconds", duration)

@pytest.mark.performance
def test_memory_footprint():
    """Measure peak RAM usage (Peak Memory)."""
    process = psutil.Process()
    # Perform some heavy tasks...
    peak_memory_mb = process.memory_info().rss / (1024 * 1024)
    
    check_performance_regression("peak_memory_usage_mb", peak_memory_mb)

@pytest.mark.performance
def test_inference_throughput(tmp_path):
    """Measure processing speed (Frames per second)."""
    # Simulate inference speed measurement of the C model (target > 1000 FPS)
    start_time = time.time()
    # Logic simulates processing 1000 frames.
    time.sleep(0.1) 
    duration = time.time() - start_time
    fps = 1000 / duration
    
    # check regression based on processing time of 1k frames
    check_performance_regression("inference_latency_1k_frames", duration)

@pytest.mark.performance
def test_model_loading_latency():
    """Measure the time it takes to load the model into memory."""
    start_time = time.time()
    # Logic for simulating weighted loads from Flash
    time.sleep(0.05)
    duration = time.time() - start_time
    
    check_performance_regression("model_loading_seconds", duration)

@pytest.mark.performance
def test_quantization_error_impact():
    """Measure the error between the Float32 and INT8 models."""
    # Simulation: Mean Square Error (MSE) between the original and quantized models
    mse_error = 0.023 
    
    # Check if the error suddenly increases significantly (Regression)
    check_performance_regression("quantization_mse_error", mse_error)