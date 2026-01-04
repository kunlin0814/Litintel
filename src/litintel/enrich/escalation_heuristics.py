"""
Escalation heuristics - deterministic gate for Shadow Judge.
Version: 1.0.1
"""
from typing import Dict, Any, Tuple, List, Union

# Keywords that suggest high relevance (positive signals)
HIGH_RELEVANCE_KEYWORDS = [
    "highly relevant", "directly relevant", "strong relevance",
    "significant", "important", "novel", "groundbreaking",
    "central", "key finding", "major contribution"
]

# Keywords that suggest low relevance (negative signals)
LOW_RELEVANCE_KEYWORDS = [
    "not relevant", "low relevance", "marginally relevant",
    "limited relevance", "tangential", "indirect",
    "unrelated", "out of scope"
]


def _get_config_value(config, key: str, default: Any) -> Any:
    """Get config value from either dict or Pydantic model."""
    if hasattr(config, key):
        return getattr(config, key, default)
    elif isinstance(config, dict):
        return config.get(key, default)
    return default


def should_escalate(
    nano_output: Dict[str, Any], 
    config: Any  # Can be Dict or EscalationTriggersConfig
) -> Tuple[bool, List[str]]:
    """
    Returns (should_escalate, triggered_rules) based on deterministic heuristics.
    Does NOT trust Nano's value judgments—only structural signals.
    
    Supports both dict config and typed EscalationTriggersConfig.
    """
    signals = []
    if not config:
        return False, []
    
    # H1: Short rationale (Nano uncertain but didn't say so)
    why_relevant = nano_output.get("WhyRelevant", "")
    min_rationale_len = _get_config_value(config, "min_rationale_length", 50)
    if len(why_relevant) < min_rationale_len:
        signals.append("H1_SHORT_RATIONALE")
    
    # H2: Score near threshold boundary
    score = nano_output.get("RelevanceScore", 0)
    score_range = _get_config_value(config, "score_range", [70, 79])
    if len(score_range) == 2:
        start, end = score_range
        if start <= score <= end:
            signals.append("H2_THRESHOLD_BOUNDARY")
    
    # H3: Text/Score inconsistency - high relevance words but low score
    study_summary = nano_output.get("StudySummary", "")
    
    # Combine texts for keyword search, handle potential None values
    text_content = ""
    if why_relevant:
        text_content += why_relevant.lower() + " "
    if study_summary:
        text_content += study_summary.lower()
        
    has_high_kw = any(kw in text_content for kw in HIGH_RELEVANCE_KEYWORDS)
    has_low_kw = any(kw in text_content for kw in LOW_RELEVANCE_KEYWORDS)
    
    # Thresholds for "High" and "Low" score mismatch
    # Can be overridden via config for tuning
    high_score_thresh = _get_config_value(config, "h3_high_score_thresh", 80)
    low_score_thresh = _get_config_value(config, "h3_low_score_thresh", 70)
    
    if has_high_kw and score < low_score_thresh:
        signals.append("H3_HIGH_TEXT_LOW_SCORE")
    if has_low_kw and score > high_score_thresh:
        signals.append("H3_LOW_TEXT_HIGH_SCORE")
    
    # H4: High relevance + low reuse inconsistency
    # Check if comp_methods was extracted
    comp = nano_output.get("comp_methods")
    if isinstance(comp, dict):
        reuse = comp.get("reuse_score_0to5", 0)
        # Type coercion just in case
        try:
            reuse = int(reuse)
        except (ValueError, TypeError):
            reuse = 0
            
        escalate_on_high_reuse = _get_config_value(config, "escalate_on_high_reuse", 4)
        
        # If highly relevant but reuse is very low (and not just missing)
        # Note: This heuristic assumes high relevance papers SHOULD have reuse potential 
        # for this specific pipeline (Methods Discovery / Tier 1). 
        # Modifying logic: If score is very high (>=85) but reuse is <= 1, that's suspicious for a methods pipeline.
        if score >= 85 and reuse <= 1:
            signals.append("H4_HIGH_RELEVANCE_LOW_REUSE")
            
    return len(signals) > 0, signals
