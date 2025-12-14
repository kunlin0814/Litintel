import unittest
import os
import sys
# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from litintel.utils.vocab import VocabNormalizer

class TestVocabNormalization(unittest.TestCase):
    def setUp(self):
        # We assume configs/controlled_vocab.yaml exists or we verify loading failure handling
        # For test, we can mock or rely on the real file created in Phase 1
        self.normalizer = VocabNormalizer("configs/controlled_vocab.yaml")

    def test_synonyms_map_to_canonical(self):
        # Config has: cell2location: Cell2location
        result = self.normalizer.normalize_method_name("cell2location")
        self.assertEqual(result, "Cell2location")
        
        # Case insensitive
        result = self.normalizer.normalize_method_name("CELL2LOCATION")
        self.assertEqual(result, "Cell2location")

    def test_multiple_methods(self):
        # "seurat; cell2loc" -> "Seurat; Cell2location"
        result = self.normalizer.normalize_method_name("seurat; cell2loc")
        self.assertEqual(result, "Seurat; Cell2location")

    def test_unknown_method(self):
        # "UnknownTool" -> "UnknownTool"
        result = self.normalizer.normalize_method_name("UnknownTool")
        self.assertEqual(result, "UnknownTool")

if __name__ == "__main__":
    unittest.main()
