"""Tests for linked accounts and external reputation."""
from __future__ import annotations

import uuid

import pytest

from src.external_reputation import (
    compute_github_reputation,
    compute_huggingface_reputation,
    compute_npm_reputation,
    compute_pypi_reputation,
)


def test_compute_github_reputation_empty():
    score, metrics = compute_github_reputation({}, [])
    assert score == 0.0
    assert metrics == {}


def test_compute_github_reputation_with_data():
    profile = {
        "followers": 50,
        "public_repos": 30,
        "created_at": "2020-01-01T00:00:00Z",
    }
    repos = [
        {
            "stargazers_count": 100,
            "forks_count": 20,
            "updated_at": "2026-03-01T00:00:00Z",
        },
        {
            "stargazers_count": 50,
            "forks_count": 5,
            "updated_at": "2025-01-01T00:00:00Z",
        },
    ]
    score, metrics = compute_github_reputation(profile, repos)
    assert 0.0 < score <= 1.0
    assert metrics["total_stars"] == 150
    assert metrics["total_forks"] == 25
    assert metrics["followers"] == 50
    assert metrics["repo_count"] == 2
    assert "component_scores" in metrics


def test_compute_npm_reputation_empty():
    score, metrics = compute_npm_reputation({})
    assert score == 0.0
    assert metrics == {}


def test_compute_npm_reputation_with_data():
    package_data = {
        "downloads": 5000,
        "versions": {"1.0.0": {}, "1.1.0": {}, "2.0.0": {}},
        "maintainers": [{"name": "alice"}, {"name": "bob"}],
    }
    score, metrics = compute_npm_reputation(package_data)
    assert 0.0 < score <= 1.0
    assert metrics["downloads"] == 5000
    assert metrics["versions"] == 3
    assert metrics["maintainers"] == 2


def test_compute_pypi_reputation_empty():
    score, metrics = compute_pypi_reputation({})
    assert score == 0.0
    assert metrics == {}


def test_compute_pypi_reputation_with_data():
    package_data = {
        "info": {
            "classifiers": ["Development Status :: 5 - Production/Stable"] * 5,
        },
        "releases": {"0.1": [], "0.2": [], "1.0": []},
        "downloads": 10000,
    }
    score, metrics = compute_pypi_reputation(package_data)
    assert 0.0 < score <= 1.0
    assert metrics["release_count"] == 3
    assert metrics["classifiers"] == 5


def test_compute_huggingface_reputation_empty():
    score, metrics = compute_huggingface_reputation({})
    assert score == 0.0
    assert metrics == {}


def test_compute_huggingface_reputation_with_data():
    model_data = {
        "downloads": 1000,
        "likes": 50,
        "cardData": {"some": "data"},
    }
    score, metrics = compute_huggingface_reputation(model_data)
    assert 0.0 < score <= 1.0
    assert metrics["downloads"] == 1000
    assert metrics["likes"] == 50
    assert metrics["has_model_card"] is True


def test_verification_weights():
    from src.external_reputation import VERIFICATION_WEIGHTS

    assert VERIFICATION_WEIGHTS["verified_oauth"] == 1.0
    assert VERIFICATION_WEIGHTS["verified_challenge"] == 0.85
    assert VERIFICATION_WEIGHTS["unverified_claim"] == 0.40
    assert VERIFICATION_WEIGHTS["pending"] == 0.0
