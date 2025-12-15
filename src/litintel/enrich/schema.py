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
    AI_EvidenceLevel: str = "Abstract"  # FullText | Abstract | TitleOnly
    PipelineConfidence: str = "Low"     # Low | Medium | Medium-Ambiguous | High | Error
    
    # Decision Support
    WhyYouMightCare: Optional[str] = ""

    # Genomic Data Accessions (Dual-Confidence Strategy)
    GEO_Candidates: Optional[str] = ""      # Medium - blind regex from full-text
    GEO_Validated: Optional[str] = ""       # High - AI confirmed as study's own data
    SRA_Candidates: Optional[str] = ""      # Medium - blind regex from full-text
    SRA_Validated: Optional[str] = ""       # High - AI confirmed as study's own data
    # MeSH Terms
    MeSH_Headings: Optional[str] = ""  # MeSH with qualifiers
    MeSH_Terms: Optional[str] = ""      # All descriptor names
    MeSH_Major: Optional[str] = ""      # Major topics only

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
    # AI-Validated Accessions (subset of candidates confirmed as study's own data)
    GEO_Validated: str = ""
    SRA_Validated: str = ""

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
