import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest

from litintel.config import AppConfig


def _minimal_config_kwargs():
    """The smallest AppConfig that validates, so config tests stay focused."""
    return {
        "pipeline_tier": 1,
        "pipeline_name": "test",
        "discovery": {"mode": "KEYWORD", "queries": ["test"]},
        "ai": {"provider": "gemini", "prompt_template": "x"},
        "storage": {},
        "dedup": {},
    }


def test_methods_repo_path_defaults_to_none():
    cfg = AppConfig(**_minimal_config_kwargs())
    assert cfg.methods_repo_path is None


def test_methods_repo_path_round_trips():
    kwargs = _minimal_config_kwargs()
    kwargs["methods_repo_path"] = "~/GitHub/dotfiles-claude/skills/bioinfo-methods"
    cfg = AppConfig(**kwargs)
    assert cfg.methods_repo_path.endswith("skills/bioinfo-methods")


from pathlib import Path

from litintel.methodintel.records import (
    RecordError,
    ReferenceRecord,
    load_concept_records,
    parse_record,
    resolve_methods_root,
)

VALID = """---
id: 2026-08-02-traag2019-louvain-connectivity
concept: clustering
modality: ["scRNA"]
methods: ["Louvain", "Leiden"]
kind: benchmark
recorded: 2026-08-02
seed_rung: null
source_ref:
  kind: doi
  value: "10.1038/s41598-019-41695-z"
  note: "Traag, Waltman, van Eck 2019"
citation:
  first_author: "Traag"
  journal: "Sci Rep"
  year: 2019
confidence: high
---

Louvain can yield arbitrarily badly connected communities. Leiden guarantees
well-connected communities.
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_parse_record_reads_frontmatter_and_body(tmp_path):
    record = parse_record(_write(tmp_path, "r.md", VALID))

    assert record.id == "2026-08-02-traag2019-louvain-connectivity"
    assert record.concept == "clustering"
    assert record.modality == ["scRNA"]
    assert record.kind == "benchmark"
    assert record.citation.journal == "Sci Rep"
    assert record.body.startswith("Louvain can yield")
    assert "---" not in record.body


def test_null_concept_is_legal(tmp_path):
    text = VALID.replace("concept: clustering", "concept: null")
    assert parse_record(_write(tmp_path, "r.md", text)).concept is None


def test_citation_required_for_doi_source(tmp_path):
    text = VALID.replace(
        'citation:\n  first_author: "Traag"\n  journal: "Sci Rep"\n  year: 2019\n', ""
    )
    with pytest.raises(RecordError, match="citation"):
        parse_record(_write(tmp_path, "r.md", text))


def test_citation_not_required_for_personal_obs(tmp_path):
    text = VALID.replace(
        'kind: doi\n  value: "10.1038/s41598-019-41695-z"',
        'kind: personal_obs\n  value: "Apollo Stage 5"',
    ).replace(
        'citation:\n  first_author: "Traag"\n  journal: "Sci Rep"\n  year: 2019\n', ""
    ).replace("kind: benchmark", "kind: personal")
    assert parse_record(_write(tmp_path, "r.md", text)).citation is None


def test_seed_rung_required_when_kind_is_seed(tmp_path):
    text = VALID.replace("kind: benchmark", "kind: seed")
    with pytest.raises(RecordError, match="seed_rung"):
        parse_record(_write(tmp_path, "r.md", text))


def test_seed_rung_rejected_when_kind_is_not_seed(tmp_path):
    text = VALID.replace("seed_rung: null", "seed_rung: 2")
    with pytest.raises(RecordError, match="seed_rung"):
        parse_record(_write(tmp_path, "r.md", text))


def test_unknown_kind_is_rejected(tmp_path):
    text = VALID.replace("kind: benchmark", "kind: gossip")
    with pytest.raises(RecordError, match="kind"):
        parse_record(_write(tmp_path, "r.md", text))


def test_adaptation_is_a_legal_kind(tmp_path):
    text = VALID.replace("kind: benchmark", "kind: adaptation")
    assert parse_record(_write(tmp_path, "r.md", text)).kind == "adaptation"


def test_implementations_are_kept_separate_from_methods(tmp_path):
    """Algorithm and package are different axes (spec 5.2)."""
    text = VALID.replace(
        'methods: ["Louvain", "Leiden"]',
        'methods: ["Louvain", "Leiden"]\nimplementations: ["ArchR", "Scanpy"]',
    )
    record = parse_record(_write(tmp_path, "r.md", text))

    assert record.methods == ["Louvain", "Leiden"]
    assert record.implementations == ["ArchR", "Scanpy"]


def test_implementations_default_to_empty(tmp_path):
    assert parse_record(_write(tmp_path, "r.md", VALID)).implementations == []


def test_missing_frontmatter_fails_loud(tmp_path):
    with pytest.raises(RecordError, match="frontmatter"):
        parse_record(_write(tmp_path, "r.md", "just prose, no fence\n"))


def test_load_concept_records_sorted_by_id(tmp_path):
    shard = tmp_path / "references" / "clustering"
    shard.mkdir(parents=True)
    (shard / "b.md").write_text(VALID.replace("2026-08-02-traag", "2026-08-03-zzz"))
    (shard / "a.md").write_text(VALID)

    records = load_concept_records(tmp_path, "clustering")

    assert [r.id for r in records] == [
        "2026-08-02-traag2019-louvain-connectivity",
        "2026-08-03-zzz2019-louvain-connectivity",
    ]


def test_load_concept_records_missing_shard_returns_empty(tmp_path):
    assert load_concept_records(tmp_path, "nonexistent") == []


def test_parse_record_tolerates_leading_html_comment_line(tmp_path):
    """Real seed records on disk lead with '<!-- path -->' before the fence."""
    text = "<!-- references/_seeds/r.md -->\n" + VALID
    record = parse_record(_write(tmp_path, "r.md", text))
    assert record.id == "2026-08-02-traag2019-louvain-connectivity"


def test_resolve_methods_root_raises_when_none():
    with pytest.raises(RecordError, match="methods_repo_path"):
        resolve_methods_root(None)


def test_resolve_methods_root_raises_when_path_does_not_exist(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(RecordError, match="methods_repo_path"):
        resolve_methods_root(str(missing))


def test_resolve_methods_root_raises_when_path_is_a_file(tmp_path):
    a_file = tmp_path / "not-a-dir"
    a_file.write_text("x")
    with pytest.raises(RecordError, match="methods_repo_path"):
        resolve_methods_root(str(a_file))


def test_resolve_methods_root_expands_user(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / "GitHub" / "dotfiles" / "skills" / "bioinfo-methods").mkdir(
        parents=True
    )
    monkeypatch.setenv("HOME", str(fake_home))

    root = resolve_methods_root("~/GitHub/dotfiles/skills/bioinfo-methods")

    assert root == fake_home / "GitHub" / "dotfiles" / "skills" / "bioinfo-methods"


def test_resolve_methods_root_returns_path_for_valid_dir(tmp_path):
    assert resolve_methods_root(str(tmp_path)) == tmp_path
