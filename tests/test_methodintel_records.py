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
