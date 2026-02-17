"""Tests for FredPipeline — mocked provider + real DB."""

import datetime
import pytest
from unittest.mock import patch, MagicMock

from database import DatabaseManager


def _make_mock_provider():
    """Create a mock FredProvider."""
    provider = MagicMock()
    provider.name = "FRED"
    provider.get_series_info.return_value = {
        "series_id": "GDP",
        "title": "Gross Domestic Product",
        "units": "Billions of Dollars",
        "frequency": "Quarterly",
        "seasonal_adj": "Seasonally Adjusted",
        "last_updated": "2025-01-15",
        "notes": "GDP notes",
    }
    provider.get_observations.return_value = [
        {"series_id": "GDP", "date": "2024-01-01", "value": 27000.0},
        {"series_id": "GDP", "date": "2024-04-01", "value": 27500.0},
    ]
    return provider


@pytest.fixture
def pipeline_db(tmp_path):
    """Yield db_path for pipeline tests. Pre-create schema."""
    db_path = str(tmp_path / "pipeline.db")
    db = DatabaseManager(db_path=db_path)
    yield db, db_path
    db.close()


class TestFredPipeline:
    """Test FredPipeline with mocked provider and real DB."""

    def _run_pipeline(self, db_path, mock_provider, series_ids=None, force=False):
        """Run FredPipeline.__init__ with mocks in place."""
        series_ids = series_ids or ["GDP"]
        with patch("sources.fred.pipeline.FredProvider", return_value=mock_provider), \
             patch("sources.fred.pipeline.DatabaseManager", side_effect=lambda *a, **kw: DatabaseManager(db_path=db_path)), \
             patch("sources.fred.pipeline.log"), \
             patch("sources.fred.pipeline.load_dotenv"):

            from sources.fred.pipeline import FredPipeline
            FredPipeline(series_ids=series_ids, days=365, force=force)

        # Return a fresh connection for assertions
        return DatabaseManager(db_path=db_path)

    def test_end_to_end(self, pipeline_db):
        db, db_path = pipeline_db
        mock_provider = _make_mock_provider()
        result_db = self._run_pipeline(db_path, mock_provider)
        rows = result_db.query("SELECT * FROM fred_observations ORDER BY date")
        assert len(rows) >= 2
        assert rows[0]["series_id"] == "GDP"
        result_db.close()

    def test_metadata_persisted(self, pipeline_db):
        db, db_path = pipeline_db
        mock_provider = _make_mock_provider()
        result_db = self._run_pipeline(db_path, mock_provider)
        meta = result_db.query("SELECT * FROM fred_series_meta WHERE series_id = 'GDP'")
        assert len(meta) == 1
        assert meta[0]["title"] == "Gross Domestic Product"
        result_db.close()

    def test_cache_skip(self, pipeline_db):
        """If latest observation is today, provider should not be called."""
        db, db_path = pipeline_db
        db.upsert_fred_series_meta({"series_id": "GDP", "title": "GDP"})
        db.upsert_fred_observations([{
            "series_id": "GDP",
            "date": datetime.date.today().isoformat(),
            "value": 28000.0,
        }])
        mock_provider = _make_mock_provider()
        self._run_pipeline(db_path, mock_provider, force=False)
        mock_provider.get_series_info.assert_not_called()

    def test_force_override(self, pipeline_db):
        """force=True should call provider even if cache is fresh."""
        db, db_path = pipeline_db
        db.upsert_fred_series_meta({"series_id": "GDP", "title": "GDP"})
        db.upsert_fred_observations([{
            "series_id": "GDP",
            "date": datetime.date.today().isoformat(),
            "value": 28000.0,
        }])
        mock_provider = _make_mock_provider()
        self._run_pipeline(db_path, mock_provider, force=True)
        mock_provider.get_series_info.assert_called_once()

    def test_error_resilience(self, pipeline_db):
        """Provider exception should not crash the pipeline."""
        db, db_path = pipeline_db
        mock_provider = _make_mock_provider()
        mock_provider.get_series_info.side_effect = RuntimeError("API down")
        # Should not raise
        self._run_pipeline(db_path, mock_provider, series_ids=["GDP", "UNRATE"])
