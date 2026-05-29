import os
import sys
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from litintel.methodintel.schema import EvidenceClaim, SourceRef, SourceRefKind
from litintel.methodintel.verify import verify_evidence_claims


_FAKE_PUBMED_XML = """
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">31178118</PMID>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
""".strip()


def test_pmid_claim_marked_verified_when_pubmed_returns_pmid():
    claim = EvidenceClaim(
        statement="Leiden guarantees well-connected communities.",
        source_ref=SourceRef(kind=SourceRefKind.PMID, value="31178118"),
    )

    with patch(
        "litintel.methodintel.verify.fetch_details",
        return_value=_FAKE_PUBMED_XML,
    ) as mock_fetch:
        verified = verify_evidence_claims([claim])

    assert verified[0].verified is True
    mock_fetch.assert_called_once_with(["31178118"])


def test_pmid_claim_marked_unverified_when_pubmed_omits_pmid():
    claim = EvidenceClaim(
        statement="Unsupported claim.",
        source_ref=SourceRef(kind=SourceRefKind.PMID, value="99999999"),
    )

    with patch(
        "litintel.methodintel.verify.fetch_details",
        return_value="<PubmedArticleSet></PubmedArticleSet>",
    ):
        verified = verify_evidence_claims([claim])

    assert verified[0].verified is False


def test_non_pmid_claim_left_unverified():
    claim = EvidenceClaim(
        statement="Personal observation from spatial ATAC pilot.",
        source_ref=SourceRef(kind=SourceRefKind.PERSONAL_OBS, value="2026-04 Apollo pilot"),
    )

    with patch("litintel.methodintel.verify.fetch_details") as mock_fetch:
        verified = verify_evidence_claims([claim])

    assert verified[0].verified is None
    mock_fetch.assert_not_called()


def test_empty_claim_list_does_not_call_pubmed():
    with patch("litintel.methodintel.verify.fetch_details") as mock_fetch:
        verified = verify_evidence_claims([])

    assert verified == []
    mock_fetch.assert_not_called()


def test_mixed_pmid_and_non_pmid_claims_single_fetch_call():
    pmid_claim = EvidenceClaim(
        statement="Leiden guarantees well-connected communities.",
        source_ref=SourceRef(kind=SourceRefKind.PMID, value="31178118"),
    )
    obs_claim = EvidenceClaim(
        statement="Personal observation from spatial ATAC pilot.",
        source_ref=SourceRef(kind=SourceRefKind.PERSONAL_OBS, value="2026-04 Apollo pilot"),
    )

    with patch(
        "litintel.methodintel.verify.fetch_details",
        return_value=_FAKE_PUBMED_XML,
    ) as mock_fetch:
        verified = verify_evidence_claims([pmid_claim, obs_claim])

    assert verified[0].verified is True
    assert verified[1].verified is None
    mock_fetch.assert_called_once_with(["31178118"])
