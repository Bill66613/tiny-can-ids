from can_ids.data import generate_synthetic_can_data
from tests.fixtures.scenario_config import ScenarioConfig, DatasetType
import numpy as np
import pandas as pd
from typing import Optional
from pathlib import Path
import logging


class Scenario:
    """Represents a test data scenario."""
    
    def __init__(self, name: str, config: ScenarioConfig, rng: np.random.Generator):
        self.name = name
        self.config = config
        self.rng = rng
        self.data: Optional[pd.DataFrame] = None

    def generate(self) -> pd.DataFrame:
        """Generate raw CAN data (Timestamp, ID, DLC, Data0-7, Flag)."""
        n_normal, n_attack = self.config.scenario_size.value
        
        # Adjust the quantity based on DatasetType
        if self.config.dataset_type == DatasetType.SYNTHETIC_EXTREME:
            n_attack = max(1, n_attack // 10) # Very few attacks
        elif self.config.dataset_type == DatasetType.SYNTHETIC_IMBALANCED:
            n_normal *= 2
            
        logger = logging.getLogger(__name__)
        logger.info(f"Generating scenario '{self.name}': {n_normal} normal, {n_attack} attack")
        
        # Call the data constructor from the can_ids.data module.
        self.data = generate_synthetic_can_data(
            n_normal=n_normal, 
            n_attack=n_attack, 
            seed=self.config.seed
        )
        return self.data

    def preprocess(self) -> pd.DataFrame:
        """Preprocess data and add labels (Normal=0, Attack=1)."""
        if self.data is None:
            self.generate()
            
        df = self.data.copy()
        # In the Car Hacking Dataset: 'R' is Normal, all other values ​​are Attack.
        df['label'] = df['Flag'].apply(lambda x: 0 if x == 'R' else 1)
        self.data = df
        return self.data

    def to_csv(self, path: Path) -> Path:
        """Save raw+labeled data as CSV for pipeline input."""
        if self.data is None:
            self.preprocess()
            
        path.parent.mkdir(parents=True, exist_ok=True)
        cols_to_save = [c for c in self.data.columns if c != 'label']
        self.data[cols_to_save].to_csv(path, index=False)
        return path

    def validate(self) -> bool:
        """Verify data integrity after preprocessing."""
        if self.data is None: return False
        
        required_cols = ['Timestamp', 'ID', 'DLC', 'Flag', 'label']
        for col in required_cols:
            if col not in self.data.columns:
                raise ValueError(f"Missing column: {col}")
        
        if self.data.isnull().values.any():
            raise ValueError("Data contains NaN values")
            
        return True