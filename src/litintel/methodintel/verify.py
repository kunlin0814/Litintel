"""Evidence-claim verification for MethodIntel dossiers.

Resolves PMID `source_ref` values against the existing PubMed client and
sets the `verified` flag on each `EvidenceClaim`. Non-PMID source kinds
are left with `verified=None` -- their verification is out of scope for
this module.

The point of this verifier is structural: claims without a resolvable
source MUST be visible in the final dossier so a human reviewer can act
on them. Hallucinated benchmark numbers are the failure mode this
module exists to prevent.
"""

from __future__ import annotations

import re
from typing import Iterable, List

from litintel.methodintel.schema import EvidenceClaim, SourceRefKind
from litintel.pubmed.client import fetch_details


_PMID_TAG = re.compile(r"<PMID[^>]*>(\d+)</PMID>")


def verify_evidence_claims(claims: Iterable[EvidenceClaim]) -> List[EvidenceClaim]:
    """Return a list of EvidenceClaim copies with `verified` populated.

    PMID claims are batched into a single `fetch_details` call and each
    PMID is checked against the returned XML body. Non-PMID claims are
    not verified here and retain `verified=None`.
    """
    claims_list = list(claims)
    pmid_indexes = [
        idx for idx, claim in enumerate(claims_list)
        if claim.source_ref.kind == SourceRefKind.PMID
    ]

    if not pmid_indexes:
        return [claim.model_copy() for claim in claims_list]

    pmids = [claims_list[idx].source_ref.value for idx in pmid_indexes]
    xml_body = fetch_details(pmids)
    returned = set(_PMID_TAG.findall(xml_body or ""))

    out: List[EvidenceClaim] = []
    for idx, claim in enumerate(claims_list):
        if claim.source_ref.kind == SourceRefKind.PMID:
            out.append(claim.model_copy(update={
                "verified": claim.source_ref.value in returned,
            }))
        else:
            out.append(claim.model_copy())
    return out
