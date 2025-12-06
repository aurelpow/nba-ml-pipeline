"""Test unified training module with both targets."""

import unittest
import os
import tempfile
from src.training.train import UnifiedModelTrainer


class TestUnifiedTraining(unittest.TestCase):
    """Test unified training for both points and fantasy_points targets."""
    
    def setUp(self):
        """Create temporary directory for test models."""
        self.temp_dir = tempfile.TemporaryDirectory()
    
    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def test_points_target_training(self):
        """Test training with points target."""
        print("\n🏀 Testing points prediction training...")
        
        model_path = os.path.join(self.temp_dir.name, "points_model.pkl")
        trainer = UnifiedModelTrainer(
            target="points",
            model_path=model_path,
            save_mode="local"
        )
        
        # Run without tuning for speed
        trainer.run(tune_params=False)
        
        # Verify model was saved
        self.assertTrue(os.path.exists(model_path))
        self.assertTrue(len(trainer.feature_cols) > 0)
        
        print(f"✅ Points model trained with {len(trainer.feature_cols)} features")
    
    def test_fantasy_target_training(self):
        """Test training with fantasy_points target."""
        print("\n⭐ Testing fantasy points prediction training...")
        
        model_path = os.path.join(self.temp_dir.name, "fantasy_model.pkl")
        trainer = UnifiedModelTrainer(
            target="fantasy_points",
            model_path=model_path,
            save_mode="local"
        )
        
        # Run without tuning for speed
        trainer.run(tune_params=False)
        
        # Verify model was saved
        self.assertTrue(os.path.exists(model_path))
        self.assertTrue(len(trainer.feature_cols) > 0)
        
        print(f"✅ Fantasy model trained with {len(trainer.feature_cols)} features")
    
    def test_invalid_target_raises_error(self):
        """Test that invalid target raises ValueError."""
        print("\n❌ Testing invalid target...")
        
        with self.assertRaises(ValueError):
            UnifiedModelTrainer(
                target="invalid_target",
                model_path="dummy.pkl",
                save_mode="local"
            )
        
        print("✅ Invalid target correctly rejected")


if __name__ == '__main__':
    unittest.main(verbosity=2)
