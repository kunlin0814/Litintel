from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class BaseRecord(BaseModel):
    PMID: str
    DOI: Optional[str] = ""
    Title: str
    Abstract: str
    Authors: Optional[str] = ""
    Journal: Optional[str] = ""
    Year: Optional[str] = ""
    FullTextUsed: bool = False
    PipelineConfidence: str = "Low"

class Tier1Record(BaseRecord):
    """Schema for Prostate Cancer Triage (Gold Standard)"""
    RelevanceScore: int = 0
    WhyRelevant: str = ""
    StudySummary: str = ""
    PaperRole: str = ""
    Theme: str = ""  # Semicolon separated
    Methods: str = ""
    KeyFindings: str = ""
    DataTypes: str = ""
    Group: str = ""
    CellIdentitySignatures: str = ""
    PerturbationsUsed: str = ""

class Tier2Record(BaseRecord):
    """Schema for Methods Discovery"""
    RelevanceScore: int = 0
    WhyRelevant: str = ""
    StudySummary: str = ""
    PI_Group: str = ""
    ProblemArea: str = ""  # Multi-value allowed (semicolon sep)
    MethodName: str = ""
    MethodRole: str = ""
    InputsRequired: str = ""
    KeyParameters: str = ""
    AssumptionsFailureModes: str = ""
    EvidenceContext: str = ""
    DataTypes: str = ""
