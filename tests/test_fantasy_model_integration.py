import unittest
import os
import tempfile
from src.training.train import UnifiedModelTrainer

class TestFantasyModelIntegration(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for the model artifact
        self.temp_dir = tempfile.TemporaryDirectory()
        self.model_path = os.path.join(self.temp_dir.name, "integration_test_model.pkl")
        
        # Initialize trainer with real data loading (no mocks)
        # We assume the CSV files exist in the 'databases/' folder as per workspace structure
        self.trainer = UnifiedModelTrainer(target="fantasy_points", model_path=self.model_path, save_mode="local")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_pipeline_real_data(self):
        print("\nRunning integration test with REAL data... this may take a while.")
        
        # Run pipeline with minimal iterations for speed, but using real data
        # tune_params=False to skip the long hyperparameter tuning step
        self.trainer.run(tune_params=False, n_iter=1)
        
        # Check if model file was created
        self.assertTrue(os.path.exists(self.model_path))
        
        # Check if feature columns were populated (meaning data was loaded and processed)
        self.assertTrue(len(self.trainer.feature_cols) > 0)
        
        print(f"Integration test passed. Model saved to {self.model_path}")

if __name__ == '__main__':
    unittest.main()
