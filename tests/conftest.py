"""Shared fixtures for the test suite."""

import os
import pytest
from unittest.mock import MagicMock

from database import DatabaseManager


@pytest.fixture
def tmp_db(tmp_path):
    """Fresh DatabaseManager backed by a real SQLite DB in tmp_path."""
    db_path = str(tmp_path / "test.db")
    db = DatabaseManager(db_path=db_path)
    yield db
    db.close()


@pytest.fixture
def mock_response():
    """Factory for mock HTTP responses."""
    def _make(status_code=200, json_data=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        # truthy when status_code == 200
        resp.__bool__ = lambda self: self.status_code == 200
        return resp
    return _make


@pytest.fixture
def sample_news_article():
    """Factory fixture — call with overrides to get an article dict."""
    def _make(**overrides):
        article = {
            "provider": "test",
            "source_name": "Test Source",
            "title": "Test Article Title",
            "description": "Test description",
            "url": "https://example.com/article-1",
            "published_at": "2025-01-15T10:00:00Z",
            "fetched_at": "2025-01-15T12:00:00Z",
            "category": "business",
            "sentiment": 0.5,
            "topics": ["economy"],
            "image_url": "https://example.com/img.jpg",
        }
        article.update(overrides)
        return article
    return _make


@pytest.fixture
def sample_fred_meta():
    """Sample FRED series metadata dict."""
    return {
        "series_id": "GDP",
        "title": "Gross Domestic Product",
        "units": "Billions of Dollars",
        "frequency": "Quarterly",
        "seasonal_adj": "Seasonally Adjusted Annual Rate",
        "last_updated": "2025-01-15",
        "notes": "GDP measures the value of goods and services.",
    }


@pytest.fixture
def sample_fred_observations():
    """Sample FRED observations list (includes a None value)."""
    return [
        {"series_id": "GDP", "date": "2024-01-01", "value": 27000.0},
        {"series_id": "GDP", "date": "2024-04-01", "value": 27500.0},
        {"series_id": "GDP", "date": "2024-07-01", "value": None},
    ]
