from tests.fixtures.scenario_config import DatasetType, ScenarioConfig, ScenarioSize
from tests.fixtures.scenario import Scenario
import numpy as np
from typing import Dict, List

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
    """Centralized test data provisioning system."""
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.scenarios: Dict[str, Scenario] = {}
        self._initialize_predefined_scenarios()
        
    def _initialize_predefined_scenarios(self):
        for name, config in DataFeederConfig.SCENARIOS.items():
            self.scenarios[name] = Scenario(name, config, self.rng)

    def get_scenario(self, name: str) -> Scenario:
        if name not in self.scenarios:
            raise ValueError(f"Unknown scenario: {name}. Available: {self.list_scenarios()}")
        return self.scenarios[name]

    def list_scenarios(self) -> List[str]:
        return list(self.scenarios.keys())

    def create_custom_scenario(self, name: str, size: ScenarioSize, **kwargs) -> Scenario:
        config = ScenarioConfig(scenario_size=size, **kwargs)
        scenario = Scenario(name, config, self.rng)
        self.scenarios[name] = scenario
        return scenario