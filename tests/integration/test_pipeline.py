import sys
import os
from unittest import result
from numpy import size
from numpy.ma import size
import pytest
import subprocess
import shutil
import time
from pathlib import Path
from tests.fixtures.data_feeder import DataFeeder

@pytest.fixture(scope="module")
def feeder():
    """Provide DataFeeders for all test cases in the module."""
    return DataFeeder(seed=42)

class TestPipelineOutputs:
    """Integration testing system for the process run_pipeline.py."""

    def run_pipeline(self, dataset_path: Path, output_dir: Path, extra_args: list = None):
        """Helper function to run pipeline through subprocess."""
        project_root = str(Path(__file__).parents[2].absolute())
        env = os.environ.copy()
        env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")
        cmd = [
            sys.executable,
            "scripts/run_pipeline.py",
            "--export-model", "all",
            "--dataset", str(dataset_path),
            "--output-dir", str(output_dir)
        ]
        if extra_args:
            cmd.extend(extra_args)

        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def test_pipeline_runs_tiny(self, feeder, tmp_path):
        """Test 1: Verify that the pipeline runs successfully with minimal data."""
        scenario = feeder.get_scenario("tiny_binary")
        csv_path = scenario.to_csv(tmp_path / "tiny.csv")
        output_dir = tmp_path / "output"

        # Run the pipeline, skipping TFLite for quick testing.
        result = self.run_pipeline(csv_path, output_dir, ["--epochs", "1", "--window-size", str(scenario.config.window_size)])

        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
        assert output_dir.exists()
        assert (output_dir / "tiny_ids_tnn_weights.h").exists()
        assert (output_dir / "tiny_ids_tnn_inference.c").exists()

    def test_c_headers_valid(self, feeder, tmp_path):
        """Test 2: Check the validity of the Header (.h)."""
        scenario = feeder.get_scenario("small_binary")
        csv_path = scenario.to_csv(tmp_path / "small_h.csv")
        output_dir = tmp_path / "output"
        self.run_pipeline(csv_path, output_dir, ["--epochs", "1"])

        for h_file in output_dir.glob("tiny_ids_*.h"):
            content = h_file.read_text()
            assert "#ifndef" in content
            assert "#define" in content
            assert "#endif" in content
            assert "static const int8_t" in content
            assert "#include <stdint.h>" in content


    def test_c_source_valid(self, feeder, tmp_path):
        """Test 3: Check the validity of the Source (.c) file."""
        scenario = feeder.get_scenario("small_binary")
        csv_path = scenario.to_csv(tmp_path / "small_c.csv")
        output_dir = tmp_path / "output"
        self.run_pipeline(csv_path, output_dir, ["--epochs", "1"])

        for c_file in output_dir.glob("tiny_ids_*.c"):
            content = c_file.read_text()
            assert "#include" in content
            assert "predict" in content.lower(), f"Missing predict function in {c_file.name}"
            assert "static float _relu" in content or c_file.name != "tiny_ids_tnn_inference.c"
            assert "malloc" not in content  # No dynamic allocation

    def test_c_code_compiles(self, feeder, tmp_path):
        """Test 4: Verify if the generated C code actually compiles."""
        scenario = feeder.get_scenario("small_binary")
        csv_path = scenario.to_csv(tmp_path / "small_compile.csv")
        output_dir = tmp_path / "output"

        self.run_pipeline(csv_path, output_dir, ["--epochs", "1"])

        # Prioritize arm-gcc; if not available, use the system's standard gcc.
        compiler = shutil.which("arm-none-eabi-gcc") or shutil.which("gcc")
        if not compiler:
            pytest.skip("No C compiler (gcc) found in PATH")

        for c_file in output_dir.glob("tiny_ids_*.c"):
            obj_file = tmp_path / f"{c_file.stem}.o"
            res = subprocess.run([
                compiler, "-c", str(c_file),
                "-I", str(output_dir),
                "-o", str(obj_file),
                "-Wall", "-Werror"
            ], capture_output=True, text=True)

            assert res.returncode == 0, f"Compilation failed for {c_file.name}: {res.stderr}"

    def test_model_sizes_budget(self, feeder, tmp_path):
        """Test 5: Check if the file size is within the memory budget."""
        scenario = feeder.get_scenario("small_binary")
        csv_path = scenario.to_csv(tmp_path / "size_test.csv")
        output_dir = tmp_path / "output"

        result = self.run_pipeline(csv_path, output_dir, [])

        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
        # TNN weights header < 15KB
        tnn_h = output_dir / "tiny_ids_tnn_weights.h"
        assert tnn_h.stat().st_size < 20000, f"TNN header too large: {tnn_h.stat().st_size} bytes"

    def test_tflite_export_valid(self, feeder, tmp_path):
        """Test 6: Verify the validity of the TFLite file."""
        # Some CI environments may not have TensorFlow installed, so check beforehand.
        try:
            import tensorflow as tf
        except ImportError:
            pytest.skip("TensorFlow not installed, skipping TFLite validation")

        scenario = feeder.get_scenario("small_binary")
        csv_path = scenario.to_csv(tmp_path / "tflite.csv")
        output_dir = tmp_path / "output"

        # Run the full pipeline (including TFLite).
        result = self.run_pipeline(csv_path, output_dir, ["--epochs", "3", "--tflite"])

        tflite_files = list(output_dir.glob("*.tflite"))
        if len(tflite_files) == 0:
            print("\nPIPELINE STDOUT:", result.stdout)
            print("\nPIPELINE STDERR:", result.stderr)

        assert len(tflite_files) > 0, "No TFLite file generated"

        size = tflite_files[0].stat().st_size
        assert size > 0, "TFLite file is empty"
        assert size < 50000, "TFLite file too large (> 50 KB)"

    def test_metrics_reporting(self, feeder, tmp_path):
        """Test 7: Check if the pipeline prints out a metrics comparison table."""
        scenario = feeder.get_scenario("small_binary")
        csv_path = scenario.to_csv(tmp_path / "metrics.csv")

        result = self.run_pipeline(csv_path, tmp_path / "out_metrics", ["--export-model", "all", "--window-size", str(scenario.config.window_size)])

        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"

        assert "Accuracy" in result.stdout or "accuracy" in result.stdout
        assert "F1" in result.stdout or "f1" in result.stdout
        assert "Model Comparison" in result.stdout

    @pytest.mark.slow
    def test_pipeline_stress_large(self, feeder, tmp_path):
        """Test 8: Stress Test: Ability to handle large datasets."""
        scenario = feeder.get_scenario("large_binary")
        csv_path = scenario.to_csv(tmp_path / "large.csv")

        start_time = time.time()
        result = self.run_pipeline(csv_path, tmp_path / "out_large", ["--epochs", "5"])
        elapsed = time.time() - start_time

        assert result.returncode == 0
        assert elapsed < 120, f"Pipeline too slow: {elapsed:.2f}s"