# Data Feeder System Design

## Overview

The **Data Feeder** is a centralized system that provisions test data to integration tests in a structured, reusable, and maintainable way.

### Key Principles

1. **Single Source of Truth** - All test data provisioning goes through feeder
2. **Reusable Fixtures** - Fixtures used by multiple tests
3. **Scenario-Based** - Different data sizes/scenarios (small, medium, large, edge cases)
4. **Reproducible** - Same seed = same data, always
5. **Type-Safe** - Clear data structure contracts

---

## Architecture Diagram

See [diagrams/01-data-feeder-architecture.puml](diagrams/01-data-feeder-architecture.puml) for the class diagram showing:
- **DataFeeder**: Central provisioning class with scenario management
- **Scenario**: Data generation and CSV export
- **ScenarioConfig**: Explicit configuration with ScenarioSize (enum) and DatasetType (enum)
- **Integration Tests**: How tests use the DataFeeder

---

## Data Feeder Class Design

### Interface

```python
class DataFeeder:
    """Centralized test data provisioning system."""
    
    def __init__(self, seed: int = 42):
        """Initialize feeder with scenarios."""
        
    def get_scenario(self, name: str) -> Scenario:
        """Get a pre-configured scenario.
        
        Args:
            name: Scenario name (e.g., "tiny_binary", "medium_multiclass")
            
        Returns:
            Scenario object ready to generate data
        """
        
    def list_scenarios(self) -> List[str]:
        """List all available scenarios."""
        
    def create_custom_scenario(
        self,
        scenario_size: ScenarioSize,
        dataset_type: DatasetType = DatasetType.SYNTHETIC_BALANCED,
        window_size: int = 50,
        seed: int = 42
    ) -> Scenario:
        """Create a custom data scenario on-the-fly."""
```

### Scenario Class

```python
class Scenario:
    """Represents a test data scenario."""
    
    def __init__(self, config: ScenarioConfig):
        """Initialize scenario with configuration."""
        
    def generate(self) -> Tuple[DataFrame, str]:
        """Generate raw CAN data.
        
        Returns:
            (raw_df, description)
        """
        
    def preprocess(self) -> DataFrame:
        """Preprocess data (add labels)."""
        
    def extract_features(self, window_size: int = 50) -> Tuple[ndarray, ndarray]:
        """Extract features using pipeline encoder.
        
        Returns:
            (X: (n_windows, 46), y: (n_windows,))
        """
        
    def to_csv(self, path: Path) -> Path:
        """Save raw data as CSV for pipeline input."""
        
    def validate(self) -> bool:
        """Validate data integrity."""
```

### ScenarioSize Enum

```python
from enum import Enum

class ScenarioSize(Enum):
    """Predefined scenario sizes with (normal, attack) counts."""
    TINY = (100, 20)
    SMALL = (500, 100)
    MEDIUM = (1500, 300)
    LARGE = (5000, 1000)
```

### DatasetType Enum

```python
class DatasetType(Enum):
    """Dataset generation type."""
    SYNTHETIC_BALANCED = "synthetic_balanced"
    SYNTHETIC_IMBALANCED = "synthetic_imbalanced"
    SYNTHETIC_EXTREME = "synthetic_extreme"
    REAL_SUBSET = "real_subset"
```

### ScenarioConfig Class

```python
class ScenarioConfig:
    """Configuration for a test scenario."""
    
    def __init__(
        self,
        scenario_size: ScenarioSize,
        seed: int = 42,
        window_size: int = 50,
        dataset_type: DatasetType = DatasetType.SYNTHETIC_BALANCED
    ):
        """Initialize scenario configuration.
        
        Args:
            scenario_size: Size category (TINY, SMALL, MEDIUM, LARGE)
            seed: Random seed for reproducibility
            window_size: Sliding window size for feature extraction
            dataset_type: Type of dataset to generate
        """
        self.scenario_size = scenario_size
        self.seed = seed
        self.window_size = window_size
        self.dataset_type = dataset_type
```
---

## Predefined Scenarios

### Binary Classification Scenarios

| Name | Normal | Attack | Window | Purpose |
|------|--------|--------|--------|---------|
| `tiny_binary` | 100 | 20 | 20 | Quick smoke test (5 sec) |
| `small_binary` | 500 | 100 | 50 | Standard unit test (10 sec) |
| `medium_binary` | 1500 | 300 | 50 | Full integration test (30 sec) |
| `large_binary` | 5000 | 1000 | 50 | Performance test (90 sec) |

### Edge Case Scenarios

| Name | Normal | Attack | Window | Purpose |
|------|--------|--------|--------|---------|
| `extreme_imbalance` | 10000 | 10 | 50 | Highly imbalanced (stress test) |
| `single_attack` | 500 | 1 | 50 | Minimal attack data |
| `high_attack_rate` | 100 | 900 | 50 | Attack-heavy scenario |
| `no_attack` | 500 | 0 | 50 | All normal (control) |

### Multi-Class Scenarios (Future)

| Name | Classes | Purpose |
|------|---------|---------|
| `multiclass_small` | [Normal, DoS, Fuzzy, Gear, RPM] | Multi-class test |
| `multiclass_medium` | [Normal, DoS, Fuzzy, Gear, RPM] | Full multi-class |

---

## Data Feeder Usage in Tests

### Example 1: Simple Integration Test

```python
@pytest.fixture(scope="module")
def feeder():
    return DataFeeder(seed=42)

def test_pipeline_with_feeder(feeder, tmp_path):
    """Test pipeline using data feeder."""
    # Get test scenario
    scenario = feeder.get_scenario("small_binary")
    
    # Generate and save data
    raw_df = scenario.generate()
    csv_path = scenario.to_csv(tmp_path / "test_data.csv")
    
    # Run pipeline via subprocess
    result = subprocess.run([
        "python", "-m", "scripts.run_pipeline",
        "--dataset", str(csv_path),
        "--output-dir", str(tmp_path / "output"),
        "--epochs", "5"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
    
    # Validate outputs
    assert (tmp_path / "output" / "tiny_ids_tnn_weights.h").exists()
    assert (tmp_path / "output" / "tiny_ids_tnn.c").exists()
```

### Example 2: Parameterized Test with Multiple Scenarios

```python
@pytest.mark.parametrize("scenario_name", [
    "tiny_binary",
    "small_binary",
    "medium_binary"
])
def test_pipeline_multiple_scenarios(feeder, scenario_name, tmp_path):
    """Test pipeline with different data scenarios."""
    scenario = feeder.get_scenario(scenario_name)
    # ... run test
```

### Example 3: Edge Case Testing

```python
def test_pipeline_extreme_imbalance(feeder, tmp_path):
    """Test pipeline robustness with extreme imbalance."""
    scenario = feeder.get_scenario("extreme_imbalance")
    # ... run test with edge case
```

---

## Data Feeder Implementation Structure

```python
# tests/conftest.py (or tests/data_feeder.py)

class DataFeederConfig:
    SCENARIOS = {
        # Tiny (5 sec)
        "tiny_binary": ScenarioConfig(
            scenario_size=ScenarioSize.TINY, seed=1, window_size=20
        ),
        # Small (10 sec)
        "small_binary": ScenarioConfig(
            scenario_size=ScenarioSize.SMALL, seed=42, window_size=50
        ),
        # Medium (30 sec)
        "medium_binary": ScenarioConfig(
            scenario_size=ScenarioSize.MEDIUM, seed=999, window_size=50
        ),
        # Large (90 sec)
        "large_binary": ScenarioConfig(
            scenario_size=ScenarioSize.LARGE, seed=777, window_size=50
        ),
        # Edge cases
        "extreme_imbalance": ScenarioConfig(
            scenario_size=ScenarioSize.LARGE,
            seed=123,
            window_size=50,
            dataset_type=DatasetType.SYNTHETIC_EXTREME
        ),
        "no_attack": ScenarioConfig(
            scenario_size=ScenarioSize.SMALL, seed=456, window_size=50
        ),
    }

class DataFeeder:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.scenarios = {}
        self._initialize_scenarios()
        
    def _initialize_scenarios(self):
        for name, config in DataFeederConfig.SCENARIOS.items():
            self.scenarios[name] = Scenario(config, self.rng)
            
    def get_scenario(self, name: str) -> Scenario:
        if name not in self.scenarios:
            raise ValueError(f"Unknown scenario: {name}")
        return self.scenarios[name]
        
    def list_scenarios(self) -> List[str]:
        return list(self.scenarios.keys())
```

---

## Benefits of Data Feeder

| Benefit | Before | After |
|---------|--------|-------|
| **Code Duplication** | Data gen scattered | Centralized in feeder |
| **Data Consistency** | Different seeds | Reproducible by design |
| **Maintainability** | Hard to update | Single place to change |
| **Discoverability** | Unknown scenarios | `feeder.list_scenarios()` |
| **Testing Variations** | Limited sizes | Multiple predefined scenarios |
| **Documentation** | Implicit | Explicit scenario configs |

---

## Data Flow Diagram

See [diagrams/02-data-flow.puml](diagrams/02-data-flow.puml) for the workflow showing:
1. DataFeeder initializes with predefined scenarios
2. Scenario is selected and data generated
3. Data preprocessed and features extracted
4. Integration test provisions CSV and runs pipeline
5. Pipeline execution is validated

---

The DataFeeder system provides test data for:

- **Integration Test Suite**: Validates run_pipeline.py outputs across all scenarios
- **Automation Framework**: Enables CI/CD testing with consistent, reproducible data

See [02-integration-pipeline-design.md](02-integration-pipeline-design.md) and [03-automation-framework.md](03-automation-framework.md) for integration and CI/CD details.
