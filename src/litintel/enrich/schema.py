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
    PubDate: Optional[str] = ""  # Full date YYYY-MM-DD
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


class AnalysisStep(BaseModel):
    """Single step within an analysis block."""
    step: str = ""
    tool: str = ""
    rationale: str = ""

class AnalysisBlock(BaseModel):
    """An analysis block with purpose and steps."""
    analysis_name: str = ""
    purpose: str = ""
    steps: List[AnalysisStep] = []

class CompMethods(BaseModel):
    """Computational methods extracted from full-text papers.
    
    New structure uses 'analyses' blocks with purpose and rationale.
    """
    summary_2to3_sentences: str = ""
    analyses: List[AnalysisBlock] = []  # NEW: Replaces old workflow
    stats_models: List[str] = []  # Max 5
    tags: List[str] = []  # From controlled vocab
    reuse_score_0to5: int = 0

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
    # Computational Methods (full-text only)
    comp_methods: Optional[CompMethods] = None
    # Escalation tracking (Shadow Judge)
    EscalationTriggered: bool = False
    EscalationReason: str = ""


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
