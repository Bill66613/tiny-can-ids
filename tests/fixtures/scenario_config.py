from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ScenarioSize(Enum):
    """Predefined scenario sizes: (n_normal, n_attack)."""
    TINY = (500, 100)
    SMALL = (1000, 200)
    MEDIUM = (3000, 600)
    LARGE = (5000, 1000)

class DatasetType(Enum):
    """Dataset generation type."""
    SYNTHETIC_BALANCED = "synthetic_balanced"
    SYNTHETIC_IMBALANCED = "synthetic_imbalanced"
    SYNTHETIC_EXTREME = "synthetic_extreme"
    REAL_SUBSET = "real_subset"

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