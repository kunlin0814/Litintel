"""Pydantic schemas for Tier C output.

Three stages produce three structured outputs:

  Stage 1  EvidenceMap         non-interpretive extraction from PDF (multimodal)
  Stage 2  Synthesis           figure-anchored claims (text-only, from EvidenceMap)
  Stage 3  VerificationReport  figure-level grounding check (text-only)

A thin TierCRecord captures the subset of fields surfaced to Notion. The full
three-stage JSON is written to Drive as <PMID>_tierC.json.

Schemas mirror the OmniScope JSON contract verbatim where possible so the system
prompts in prompts.py can be ported without translation.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage 1: EvidenceMap
# ---------------------------------------------------------------------------

class Identity(BaseModel):
    title: str = "UNKNOWN"
    DOI: str = "UNKNOWN"
    PMID: str = "UNKNOWN"
    journal: str = "UNKNOWN"
    year: Optional[int] = None


class Biometrics(BaseModel):
    cohorts: List[str] = []
    datasets: List[str] = []


class Figure(BaseModel):
    id: str  # e.g. "Fig 1", "Extended Data Fig 3"
    panel_ids: List[str] = []
    page: Optional[int] = None
    caption: str = ""


class Anchor(BaseModel):
    id: str  # e.g. "anc_001"
    type: str = ""  # figure_citation | factual_statement | table_caption | method_line
    page: Optional[int] = None
    figure_id: Optional[str] = None
    panel_id: Optional[str] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    sentence: str = ""
    pre: str = ""
    post: str = ""
    text: str = ""


class BioinfoMethod(BaseModel):
    method_name: str = ""
    category: str = ""  # preprocessing|QC|clustering|integration|differential_expression|spatial|motif|classification|statistics|other
    tool_package: str = ""
    version: str = "UNKNOWN"
    parameters: str = "UNKNOWN"
    page_hint: Optional[int] = None


class Methods(BaseModel):
    BioinfoMethods: List[BioinfoMethod] = []


class EvidenceMap(BaseModel):
    version: str = "Stage1B_v1.1.3_relaxed_panel"
    identity: Identity = Identity()
    biometrics: Biometrics = Biometrics()
    figures: List[Figure] = []
    anchors: List[Anchor] = []
    methods: Methods = Methods()


# ---------------------------------------------------------------------------
# Stage 2: Synthesis
# ---------------------------------------------------------------------------

class TopFinding(BaseModel):
    rank: int = 0
    headline: str = ""
    figures: List[str] = []        # e.g. ["Fig 3"]
    panels: List[str] = []         # optional
    anchors: List[str] = []        # anchor ids
    methodsUsed: List[str] = []
    citationSupport: str = "none"  # strong | weak | none


class StoryEdge(BaseModel):
    fromFigure: str
    toFigure: str
    rhetoricalLink: str = ""


class PanelEntry(BaseModel):
    panel: str = ""
    mainIdea: str = ""
    claim: str = ""
    computations: List[str] = []
    databases: List[str] = []
    stats: List[str] = []
    textSupport: List[str] = []  # anchor ids


class FigurePanels(BaseModel):
    figure_id: str
    panels: List[PanelEntry] = []


class Weakness(BaseModel):
    type: str = "other"  # design|power|batch|external_validity|computational_limit|data_bias|interpretability|other
    description: str = ""
    figure: Optional[str] = None
    anchorSupport: List[str] = []
    confidence: str = "implied"  # explicit | implied


class MethodPrimer(BaseModel):
    name: str = ""
    isStandard: bool = False
    primer: Optional[str] = None  # required iff isStandard=False


class Synthesis(BaseModel):
    TopFindings: List[TopFinding] = []
    StoryMap: List[StoryEdge] = []
    Panels: List[FigurePanels] = []
    Weaknesses: List[Weakness] = []
    MethodPrimers: List[MethodPrimer] = []


# ---------------------------------------------------------------------------
# Stage 3: VerificationReport
# ---------------------------------------------------------------------------

class FindingVerification(BaseModel):
    rank: int = 0
    status: str = "unsupported"  # supported | supported_with_issues | unsupported
    figure_status: str = "mismatch"  # match | mismatch
    comments: List[str] = []
    citationSupport_verified: str = "absent"  # direct | indirect | absent


class StoryVerification(BaseModel):
    fromFigure: str = ""
    toFigure: str = ""
    status: str = "mismatch_from"  # match | mismatch_from | mismatch_to
    comments: List[str] = []


class PanelVerification(BaseModel):
    figure_id: str
    status: str = "unsupported_figure_id"  # supported | supported_with_issues | unsupported_figure_id
    missingFields: List[str] = []
    comments: List[str] = []


class MethodVerification(BaseModel):
    name: str = ""
    status: str = "unsupported"
    comment: str = ""


class WeaknessVerification(BaseModel):
    type: str = "other"
    status: str = "unsupported"
    supportLevel_verified: str = "unsupported"  # explicit | implied | unsupported
    comments: List[str] = []


class MethodMatch(BaseModel):
    reported: List[str] = []
    found_packages: List[str] = []
    found_platforms: List[str] = []
    missing: List[str] = []


class FieldSupport(BaseModel):
    textSupport: str = "absent"      # direct | indirect | absent
    computations: str = "absent"
    databases: str = "absent"
    stats: str = "absent"


class VerificationReport(BaseModel):
    TopFindings: List[FindingVerification] = []
    StoryMap: List[StoryVerification] = []
    Panels: List[PanelVerification] = []
    MethodPrimers: List[MethodVerification] = []
    Weaknesses: List[WeaknessVerification] = []
    methodMatch: MethodMatch = MethodMatch()
    fieldSupport: FieldSupport = FieldSupport()


# ---------------------------------------------------------------------------
# Combined output written to Drive as <PMID>_tierC.json
# ---------------------------------------------------------------------------

class TierCArtifact(BaseModel):
    """Bundle of all three stages written to Drive per paper."""
    pmid: Optional[str] = None
    doi: Optional[str] = None
    source: str = "PMC_OA"  # PMC_OA | Manual_Inbox
    evidence_map: EvidenceMap
    synthesis: Synthesis
    verification: VerificationReport


# ---------------------------------------------------------------------------
# Notion-facing summary
# ---------------------------------------------------------------------------

class TierCRecord(BaseModel):
    """Compact summary upserted into the Tier 1 Notion row."""
    PMID: Optional[str] = None
    DOI: Optional[str] = None
    TierC_Status: str = "complete"        # complete | skipped_no_pdf | failed
    TierC_Source: str = "PMC_OA"           # PMC_OA | Manual_Inbox
    TierC_DriveLink: str = ""
    TierC_FigureCount: int = 0
    TierC_AnchorCount: int = 0
    TierC_MethodCount: int = 0
    TierC_TopFindings: str = ""            # "; "-joined headlines for top 3
    TierC_VerificationStatus: str = "unsupported"  # all_supported | some_issues | unsupported
    TierC_Error: str = ""                  # populated only if Status=failed
