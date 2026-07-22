import unittest
import sys
import os
from pydantic import ValidationError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from litintel.config import DriveConfig
from litintel.enrich.schema import Tier1Record
from litintel.pubmed.client import _ncbi_params, fetch_pmc_pdf_url, fetch_pmc_pdf


class MockResponse:
    def __init__(self, text: str, content: bytes = b"") -> None:
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        return None

class TestSchemaValidation(unittest.TestCase):
    def test_valid_tier1_record(self):
        data = {
            "PMID": "12345678",
            "Title": "Test Paper",
            "Abstract": "Abstract here.",
            "RelevanceScore": 90,
            "WhyRelevant": "Relevant because...",
            "StudySummary": "Summary.",
            "PaperRole": "Role Z",
            "Theme": "Theme A",
            "Methods": "Method B",
            "KeyFindings": "Finding C",
            "DataTypes": "scRNA-seq",
            "Group": "Lab X"
        }
        # Should raise no error
        rec = Tier1Record(**data)
        self.assertEqual(rec.PMID, "12345678")

    def test_invalid_relevance_score_type(self):
        # RelevanceScore must be int
        data = {
            "PMID": "123",
            "Title": "T",
            "Abstract": "A",
            "RelevanceScore": "High", # Invalid
        }
        with self.assertRaises(ValidationError):
            Tier1Record(**data)

    def test_missing_required_field_defaults(self):
        # BaseRecord requires PMID, Title, Abstract. Others have defaults.
        data = {
            "PMID": "123",
            "Title": "T",
            "Abstract": "A",
            # Missing RelevanceScore, etc.
        }
        # Should pass because Pydantic models define defaults (0, "")
        rec = Tier1Record(**data)
        self.assertEqual(rec.RelevanceScore, 0)
        
    def test_extra_fields_ignored_or_allowed(self):
        # Pydantic BaseConfig default is 'ignore' extra arguments usually, let's verify behavior
        data = {
            "PMID": "123",
            "Title": "T",
            "Abstract": "A",
            "ExtraField": "Should be ignored"
        }
        rec = Tier1Record(**data)
        # Verify ExtraField is not on object if strict? 
        # By default pydantic ignores.
        self.assertFalse(hasattr(rec, "ExtraField"))

    def test_drive_config_accepts_pdf_upload_settings(self):
        config = DriveConfig(
            enabled=True,
            upload_pdfs=True,
            pdf_min_score=88,
            pdf_folder_name="PDFs",
        )

        self.assertTrue(config.upload_pdfs)
        self.assertEqual(config.pdf_min_score, 88)
        self.assertEqual(config.pdf_folder_name, "PDFs")


def test_fetch_pmc_pdf_url_resolves_ftp_href_to_https(monkeypatch):
    xml = """
    <OA>
      <records returned-count="1" total-count="1">
        <record id="PMC123">
          <link format="tgz" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/a.tar.gz"/>
          <link format="pdf" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/a/test.PMC123.pdf"/>
        </record>
      </records>
    </OA>
    """

    def mock_get(url, params=None, timeout=30):
        assert params == {"id": "PMC123", "format": "pdf"}
        return MockResponse(xml)

    monkeypatch.setattr("litintel.pubmed.client.requests.get", mock_get)

    url = fetch_pmc_pdf_url("123")

    assert url == "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/a/test.PMC123.pdf"


def test_fetch_pmc_pdf_url_returns_none_when_no_pdf(monkeypatch):
    xml = """
    <OA>
      <records returned-count="1" total-count="1">
        <record id="PMC123">
          <link format="tgz" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/a.tar.gz"/>
        </record>
      </records>
    </OA>
    """

    def mock_get(url, params=None, timeout=30):
        return MockResponse(xml)

    monkeypatch.setattr("litintel.pubmed.client.requests.get", mock_get)

    assert fetch_pmc_pdf_url("PMC123") is None


def test_fetch_pmc_pdf_tries_deprecated_fallback(monkeypatch):
    oa_xml = """
    <OA>
      <records returned-count="1" total-count="1">
        <record id="PMC123">
          <link format="pdf" href="ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_pdf/a/test.PMC123.pdf"/>
        </record>
      </records>
    </OA>
    """
    calls = []

    def mock_get(url, params=None, headers=None, timeout=30):
        calls.append(url)
        if "oa.fcgi" in url:
            return MockResponse(oa_xml)
        if "/deprecated/" in url:
            return MockResponse("", content=b"%PDF test")
        raise RuntimeError("legacy path unavailable")

    monkeypatch.setenv("NCBI_EMAIL", "test@example.org")
    monkeypatch.setattr("litintel.pubmed.client.requests.get", mock_get)

    pdf = fetch_pmc_pdf("PMC123")

    assert pdf == b"%PDF test"
    assert any("/deprecated/" in url for url in calls)


def test_ncbi_params_requires_email(monkeypatch):
    """NCBI_EMAIL is mandatory -- a placeholder fallback would misattribute traffic."""
    monkeypatch.delenv("NCBI_EMAIL", raising=False)
    try:
        _ncbi_params()
    except ValueError as exc:
        assert "NCBI_EMAIL" in str(exc)
    else:
        raise AssertionError("_ncbi_params() must raise when NCBI_EMAIL is unset")


def test_ncbi_params_includes_api_key_when_set(monkeypatch):
    monkeypatch.setenv("NCBI_EMAIL", "test@example.org")
    monkeypatch.setenv("NCBI_API_KEY", "dummy-key")  # pragma: allowlist secret
    params = _ncbi_params({"db": "pubmed"})
    assert params["email"] == "test@example.org"
    assert params["api_key"] == "dummy-key"  # pragma: allowlist secret
    assert params["db"] == "pubmed"

if __name__ == "__main__":
    unittest.main()
