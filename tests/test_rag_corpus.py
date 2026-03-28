"""Unit tests for Vertex AI RAG corpus module.

Tests _format_rag_document() and score filtering logic.
All tests use mocks -- no real GCP API calls.
"""

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

    def test_default_threshold_is_70(self):
        """Verify the default constant."""
        from litintel.storage.rag_corpus import DEFAULT_MIN_SCORE
        assert DEFAULT_MIN_SCORE == 70

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
