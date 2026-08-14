"""Central constants for LitIntel.

Defines repository-wide default model IDs and thinking levels so that fallback
values are maintained in a single place.
"""

# Default primary Gemini model for general pipeline inference
DEFAULT_GEMINI_MODEL: str = "gemini-3.7-flash"

# Default thinking level for reasoning-enabled models
DEFAULT_THINKING_LEVEL: str = "MEDIUM"

# Fallback / escalation model
DEFAULT_ESCALATE_MODEL: str = "gemini-3.7-flash"
