import yaml
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class VocabNormalizer:
    def __init__(self, vocab_path: str = "configs/controlled_vocab.yaml"):
        self.problem_areas: List[str] = []
        self.data_types: List[str] = []
        self.method_synonyms: Dict[str, str] = {}
        
        try:
            with open(vocab_path, "r") as f:
                data = yaml.safe_load(f)
                self.problem_areas = data.get("problem_areas", [])
                self.data_types = data.get("data_types", [])
                # Normalize synonyms map to lowercase keys for case-insensitive lookup
                raw_synonyms = data.get("method_synonyms", {})
                self.method_synonyms = {k.lower(): v for k, v in raw_synonyms.items()}
        except Exception as e:
            logger.warning(f"Could not load vocab from {vocab_path}: {e}")

    def normalize_method_name(self, method_name: str) -> str:
        """Normalizes a method name using the synonym map."""
        if not method_name:
            return ""
        
        # Handle semicolon separated lists
        parts = [p.strip() for p in method_name.split(";") if p.strip()]
        normalized_parts = []
        
        for p in parts:
            # Check exact match (lowercase)
            canonical = self.method_synonyms.get(p.lower())
            if canonical:
                normalized_parts.append(canonical)
            else:
                # If not in synonyms, keep original (or capitalize?)
                # Requirement says "Normalization must be deterministic."
                # Let's just strip and keep original if not mapped.
                normalized_parts.append(p)
                
        return "; ".join(normalized_parts)

    def validate_problem_area(self, area: str) -> bool:
        return area in self.problem_areas
