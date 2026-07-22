"""Unit tests for the three-domain credential resolution.

The whole point of credentials.py is that Gemini, RAG, and Drive cannot bleed
into each other. These tests assert that isolation directly -- no network.
"""

import pytest

from litintel.credentials import (
    DOMAIN_DRIVE,
    DOMAIN_GEMINI,
    DOMAIN_RAG,
    describe_all,
    drive_target,
    gemini_target,
    rag_target,
)

_PERSONAL_CORPUS = 'projects/kun-gcp-proj/locations/us-east5/ragCorpora/123'


@pytest.fixture
def clean_env(monkeypatch):
    """Strip every identity var so each test states its own world."""
    for var in (
        'USE_VERTEX_AI', 'GCP_PROJECT_ID', 'GCP_LOCATION', 'GOOGLE_API_KEY',
        'VERTEX_RAG_CORPUS_NAME', 'RAG_CREDENTIALS_JSON',
        'GOOGLE_DRIVE_CLIENT_SECRET', 'GOOGLE_CLIENT_SECRETS_PATH',
        'GOOGLE_DRIVE_TOKEN_PATH',
    ):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


class TestDomainIsolation:
    """The company project must never reach RAG, and vice versa."""

    def test_gemini_and_rag_resolve_to_different_projects(self, clean_env):
        clean_env.setenv('GCP_PROJECT_ID', 'prj-kun-cpdr-prod-nsmc')
        clean_env.setenv('VERTEX_RAG_CORPUS_NAME', _PERSONAL_CORPUS)
        clean_env.setenv('RAG_CREDENTIALS_JSON', __file__)  # any existing file

        assert gemini_target()['project'] == 'prj-kun-cpdr-prod-nsmc'
        assert rag_target()['project'] == 'kun-gcp-proj'

    def test_rag_ignores_gcp_project_id_entirely(self, clean_env):
        """Unsetting GCP_PROJECT_ID must not change where RAG points."""
        clean_env.setenv('VERTEX_RAG_CORPUS_NAME', _PERSONAL_CORPUS)
        assert rag_target()['project'] == 'kun-gcp-proj'

        clean_env.setenv('GCP_PROJECT_ID', 'some-other-project')
        assert rag_target()['project'] == 'kun-gcp-proj'

    def test_rag_location_is_independent_of_gcp_location(self, clean_env):
        """GCP_LOCATION is 'global' for Gemini; the corpus is regional."""
        clean_env.setenv('GCP_LOCATION', 'global')
        clean_env.setenv('VERTEX_RAG_CORPUS_NAME', _PERSONAL_CORPUS)
        assert gemini_target()['location'] == 'global'
        assert rag_target()['location'] == 'us-east5'


class TestGeminiTarget:

    def test_flags_a_missing_project(self, clean_env):
        assert gemini_target()['ok'] is False

    def test_api_key_mode(self, clean_env):
        clean_env.setenv('USE_VERTEX_AI', 'false')
        clean_env.setenv('GOOGLE_API_KEY', 'x')  # pragma: allowlist secret
        target = gemini_target()
        assert target['mode'] == 'api_key'
        assert target['ok'] is True


class TestRagTarget:

    def test_disabled_without_a_corpus(self, clean_env):
        target = rag_target()
        assert target['mode'] == 'disabled'
        assert target['ok'] is True  # not configured is not an error

    def test_warns_when_falling_back_to_adc(self, clean_env):
        """Silent ADC fallback is how uploads started 403-ing."""
        clean_env.setenv('VERTEX_RAG_CORPUS_NAME', _PERSONAL_CORPUS)
        notes = ' '.join(rag_target()['notes'])
        assert 'RAG_CREDENTIALS_JSON is unset' in notes

    def test_fails_on_a_missing_key_file(self, clean_env):
        clean_env.setenv('VERTEX_RAG_CORPUS_NAME', _PERSONAL_CORPUS)
        clean_env.setenv('RAG_CREDENTIALS_JSON', '/nonexistent/key.json')
        assert rag_target()['ok'] is False

    def test_fails_on_a_malformed_corpus_name(self, clean_env):
        clean_env.setenv('VERTEX_RAG_CORPUS_NAME', 'ragCorpora/123')
        assert rag_target()['ok'] is False


class TestDriveTarget:

    def test_reports_unpinned_destinations(self, clean_env):
        """Unpinned IDs are what create duplicate Drive folders."""
        clean_env.setenv('GOOGLE_DRIVE_CLIENT_SECRET', __file__)
        notes = ' '.join(drive_target()['notes'])
        assert 'Unpinned destinations' in notes

    def test_token_path_is_overridable(self, clean_env):
        clean_env.setenv('GOOGLE_DRIVE_TOKEN_PATH', '/tmp/other_token.json')
        assert drive_target()['token'] == '/tmp/other_token.json'


def test_describe_all_covers_every_domain(clean_env):
    domains = [t['domain'] for t in describe_all()]
    assert domains == [DOMAIN_GEMINI, DOMAIN_RAG, DOMAIN_DRIVE]
