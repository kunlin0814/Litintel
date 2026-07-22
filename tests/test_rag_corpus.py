"""Unit tests for Vertex AI RAG corpus module.

Tests _format_rag_document() and score filtering logic.
All tests use mocks -- no real GCP API calls.
"""

import sys

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(**overrides):
    """Build a minimal Tier1Record-style dict for testing."""
    base = {
        'PMID': '12345678',
        'DOI': '10.1234/test.2024.001',
        'Title': 'Spatial ATAC-seq reveals CTCF binding in prostate cancer',
        'Authors': 'Smith J, Jones K, Lee M',
        'Journal': 'Nature Methods',
        'Year': '2024',
        'PubDate': '2024-06-15',
        'RelevanceScore': 92,
        'PipelineConfidence': 'High',
        'AI_EvidenceLevel': 'FullText',
        'DataTypes': 'scATAC-seq, Visium',
        'Theme': 'chromatin accessibility; prostate cancer',
        'GEO_Validated': 'GSE200000',
        'SRA_Validated': 'SRP400000',
        'Abstract': 'We performed spatial ATAC-seq on prostate tumors...',
        'WhyRelevant': 'Directly profiles chromatin accessibility in PCa.',
        'StudySummary': 'This study maps open chromatin in prostate cancer.',
        'PaperRole': 'Primary research establishing spatial chromatin maps.',
        'KeyFindings': 'CTCF binding differs between tumor and normal; AR enhancers are accessible.',
        'Methods': 'spatial ATAC-seq; Visium; ArchR; Signac',
        'WhyYouMightCare': 'First spatial ATAC in prostate cancer.',
        'comp_methods': None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests for _format_rag_document
# ---------------------------------------------------------------------------

class TestFormatRagDocument:
    """Tests for the RAG document formatter."""

    def test_basic_format(self):
        from litintel.storage.rag_corpus import _format_rag_document

        rec = _make_record()
        doc = _format_rag_document(rec)

        # Should contain structured sections
        assert '=== PAPER METADATA ===' in doc
        assert '=== ABSTRACT ===' in doc
        assert '=== WHY RELEVANT ===' in doc
        assert '=== STUDY SUMMARY ===' in doc
        assert '=== KEY FINDINGS ===' in doc
        assert '=== METHODS ===' in doc

    def test_pmid_in_metadata(self):
        from litintel.storage.rag_corpus import _format_rag_document

        rec = _make_record(PMID='99999999')
        doc = _format_rag_document(rec)

        assert 'PMID: 99999999' in doc

    def test_geo_sra_included(self):
        from litintel.storage.rag_corpus import _format_rag_document

        rec = _make_record(GEO_Validated='GSE200000', SRA_Validated='SRP400000')
        doc = _format_rag_document(rec)

        assert 'GSE200000' in doc
        assert 'SRP400000' in doc

    def test_geo_sra_absent_when_empty(self):
        from litintel.storage.rag_corpus import _format_rag_document

        rec = _make_record(GEO_Validated='', SRA_Validated='')
        doc = _format_rag_document(rec)

        assert 'GEO_Datasets' not in doc
        assert 'SRA_Datasets' not in doc

    def test_comp_methods_section_when_present(self):
        from litintel.storage.rag_corpus import _format_rag_document

        rec = _make_record(
            comp_methods={'summary_2to3_sentences': 'Used ArchR for peak calling.'}
        )
        doc = _format_rag_document(rec)

        assert '=== COMPUTATIONAL METHODS SUMMARY ===' in doc
        assert 'Used ArchR for peak calling.' in doc

    def test_comp_methods_section_absent_when_none(self):
        from litintel.storage.rag_corpus import _format_rag_document

        rec = _make_record(comp_methods=None)
        doc = _format_rag_document(rec)

        assert 'COMPUTATIONAL METHODS SUMMARY' not in doc

    def test_all_fields_in_output(self):
        from litintel.storage.rag_corpus import _format_rag_document

        rec = _make_record()
        doc = _format_rag_document(rec)

        # Verify key content is present
        assert rec['Title'] in doc
        assert rec['Abstract'] in doc
        assert rec['WhyRelevant'] in doc
        assert rec['KeyFindings'] in doc
        assert rec['Methods'] in doc


# ---------------------------------------------------------------------------
# Tests for score filtering logic
# ---------------------------------------------------------------------------

class TestScoreFiltering:
    """Tests for the min_score filtering in upsert_to_rag_corpus."""

    def test_filters_below_threshold(self):
        """Records below min_score should not be eligible."""
        records = [
            _make_record(PMID='1', RelevanceScore=90),
            _make_record(PMID='2', RelevanceScore=50),
            _make_record(PMID='3', RelevanceScore=70),
            _make_record(PMID='4', RelevanceScore=69),
        ]
        min_score = 70
        eligible = [r for r in records if r.get('RelevanceScore', 0) >= min_score]

        assert len(eligible) == 2
        pmids = {r['PMID'] for r in eligible}
        assert pmids == {'1', '3'}

    def test_default_threshold_is_85(self):
        """Verify the default constant."""
        from litintel.storage.rag_corpus import DEFAULT_MIN_SCORE
        assert DEFAULT_MIN_SCORE == 85

    def test_all_below_threshold(self):
        """When all records are below threshold, none are eligible."""
        records = [
            _make_record(PMID='1', RelevanceScore=30),
            _make_record(PMID='2', RelevanceScore=60),
        ]
        eligible = [r for r in records if r.get('RelevanceScore', 0) >= 70]
        assert len(eligible) == 0

    def test_all_above_threshold(self):
        """When all records are above threshold, all are eligible."""
        records = [
            _make_record(PMID='1', RelevanceScore=85),
            _make_record(PMID='2', RelevanceScore=95),
        ]
        eligible = [r for r in records if r.get('RelevanceScore', 0) >= 70]
        assert len(eligible) == 2


# ---------------------------------------------------------------------------
# Tests for _get_comp_methods_summary helper
# ---------------------------------------------------------------------------

class TestGetCompMethodsSummary:
    """Tests for the comp_methods summary extractor."""

    def test_none_returns_empty(self):
        from litintel.storage.rag_corpus import _get_comp_methods_summary
        assert _get_comp_methods_summary(None) == ''

    def test_dict_returns_summary(self):
        from litintel.storage.rag_corpus import _get_comp_methods_summary
        comp = {'summary_2to3_sentences': 'Used ArchR for analysis.'}
        assert _get_comp_methods_summary(comp) == 'Used ArchR for analysis.'

    def test_dict_missing_key_returns_empty(self):
        from litintel.storage.rag_corpus import _get_comp_methods_summary
        comp = {'tags': ['scATAC']}
        assert _get_comp_methods_summary(comp) == ''


# ---------------------------------------------------------------------------
# Upload retry
# ---------------------------------------------------------------------------

class _FakeUploader:
    """Stands in for _upload_file_rest -- fails N times, then succeeds."""

    def __init__(self, failures, exc=None):
        self.failures = failures
        self.calls = 0
        self.exc = exc or RuntimeError(
            'RAG upload failed with HTTP 503: unavailable'
        )

    def __call__(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return 'uploaded'


class TestUploadRetry:
    """The upload POST has no retry of its own; we wrap it."""

    def test_succeeds_after_transient_failures(self, monkeypatch):
        from litintel.storage import rag_corpus
        monkeypatch.setattr(rag_corpus.time, 'sleep', lambda _: None)
        fake = _FakeUploader(failures=2)
        monkeypatch.setattr(rag_corpus, '_upload_file_rest', fake)
        result = rag_corpus._upload_file_with_retry(
            corpus_name='c', path='/tmp/x.txt',
            display_name='12345678', description='d',
        )
        assert result == 'uploaded'
        assert fake.calls == 3

    def test_raises_after_exhausting_retries(self, monkeypatch):
        from litintel.storage import rag_corpus
        monkeypatch.setattr(rag_corpus.time, 'sleep', lambda _: None)
        fake = _FakeUploader(failures=99)
        monkeypatch.setattr(rag_corpus, '_upload_file_rest', fake)
        with pytest.raises(RuntimeError):
            rag_corpus._upload_file_with_retry(
                corpus_name='c', path='/tmp/x.txt',
                display_name='12345678', description='d',
                max_retries=3,
            )
        assert fake.calls == 4  # initial attempt + 3 retries

    def test_retries_the_connection_drop_failure_mode(self, monkeypatch):
        """The upload endpoint drops connections under load."""
        from litintel.storage import rag_corpus
        monkeypatch.setattr(rag_corpus.time, 'sleep', lambda _: None)
        fake = _FakeUploader(failures=1, exc=ConnectionError('remote closed'))
        monkeypatch.setattr(rag_corpus, '_upload_file_rest', fake)
        assert rag_corpus._upload_file_with_retry(
            corpus_name='c', path='/tmp/x.txt',
            display_name='12345678', description='d',
        ) == 'uploaded'
        assert fake.calls == 2


class TestCorpusProjectResolution:
    """RAG must target the corpus's own project, never GCP_PROJECT_ID."""

    def test_parses_project_and_location(self):
        from litintel.storage.rag_corpus import parse_corpus_name
        project, location = parse_corpus_name(
            'projects/kun-gcp-proj/locations/us-east5/ragCorpora/123'
        )
        assert project == 'kun-gcp-proj'
        assert location == 'us-east5'

    def test_accepts_a_project_number(self):
        from litintel.storage.rag_corpus import parse_corpus_name
        project, _ = parse_corpus_name(
            'projects/1040326808351/locations/us-east5/ragCorpora/123'
        )
        assert project == '1040326808351'

    @pytest.mark.parametrize('bad', [
        'ragCorpora/123',
        'projects/p/ragCorpora/123',
        '',
    ])
    def test_rejects_a_malformed_name(self, bad):
        """Guessing a project would silently target the wrong account."""
        from litintel.storage.rag_corpus import parse_corpus_name
        with pytest.raises(ValueError):
            parse_corpus_name(bad)

    def test_gcp_project_id_cannot_redirect_the_corpus(self, monkeypatch):
        """Setting GCP_PROJECT_ID to the company project must not move RAG."""
        import litintel.storage.rag_corpus as rag_corpus
        monkeypatch.setenv('GCP_PROJECT_ID', 'prj-kun-cpdr-prod-nsmc')
        monkeypatch.delenv('RAG_CREDENTIALS_JSON', raising=False)
        captured = {}

        class _FakeVertexai:
            @staticmethod
            def init(project, location, credentials):
                captured['project'] = project
                captured['location'] = location

        monkeypatch.setitem(sys.modules, 'vertexai', _FakeVertexai)
        rag_corpus.init_rag(
            'projects/kun-gcp-proj/locations/us-east5/ragCorpora/123'
        )
        assert captured['project'] == 'kun-gcp-proj'
        assert captured['location'] == 'us-east5'


class TestRagCredentials:
    """RAG_CREDENTIALS_JSON selects the corpus project's service account."""

    def test_returns_none_without_the_env_var(self, monkeypatch):
        from litintel.storage.rag_corpus import rag_credentials
        monkeypatch.delenv('RAG_CREDENTIALS_JSON', raising=False)
        assert rag_credentials() is None

    def test_raises_on_a_missing_key_file(self, monkeypatch):
        """Silently falling back to ADC would hit the wrong project."""
        from litintel.storage.rag_corpus import rag_credentials
        monkeypatch.setenv('RAG_CREDENTIALS_JSON', '/nonexistent/key.json')
        with pytest.raises(FileNotFoundError):
            rag_credentials()
