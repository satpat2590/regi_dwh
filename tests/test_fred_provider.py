"""Tests for FredProvider with mocked HTTP."""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.__bool__ = lambda self: self.status_code == 200
    return resp


def _make_provider(api_key="test-key"):
    """Create a FredProvider with mocked RequestSession."""
    with patch("sources.fred.provider.RequestSession"):
        from sources.fred.provider import FredProvider
        return FredProvider(api_key=api_key)


# ---------------------------------------------------------------------------
# get_series_info
# ---------------------------------------------------------------------------

class TestGetSeriesInfo:
    def test_parses_metadata(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "serieses": [{
                "id": "GDP",
                "title": "Gross Domestic Product",
                "units": "Billions of Dollars",
                "frequency": "Quarterly",
                "seasonal_adjustment": "Seasonally Adjusted",
                "last_updated": "2025-01-15",
                "notes": "Some notes",
            }]
        })
        result = provider.get_series_info("GDP")
        assert result["series_id"] == "GDP"
        assert result["title"] == "Gross Domestic Product"
        assert result["units"] == "Billions of Dollars"
        assert result["seasonal_adj"] == "Seasonally Adjusted"

    def test_correct_url_and_params(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "serieses": [{"id": "GDP"}]
        })
        provider.get_series_info("GDP")
        args, kwargs = provider.session.get.call_args
        assert "fred/series" in args[0]
        assert kwargs["params"]["series_id"] == "GDP"
        assert kwargs["params"]["api_key"] == "test-key"

    def test_empty_serieses_raises(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={"serieses": []})
        with pytest.raises(RuntimeError, match="No series found"):
            provider.get_series_info("BADID")

    def test_none_response_raises(self):
        provider = _make_provider()
        provider.session.get.return_value = None
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            provider.get_series_info("GDP")


# ---------------------------------------------------------------------------
# get_observations
# ---------------------------------------------------------------------------

class TestGetObservations:
    def test_numeric_values_to_float(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "observations": [
                {"date": "2024-01-01", "value": "27000.5"},
                {"date": "2024-04-01", "value": "27500.0"},
            ]
        })
        result = provider.get_observations("GDP")
        assert result[0]["value"] == pytest.approx(27000.5)
        assert result[1]["value"] == pytest.approx(27500.0)
        assert result[0]["series_id"] == "GDP"

    def test_dot_value_becomes_none(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={
            "observations": [{"date": "2024-07-01", "value": "."}]
        })
        result = provider.get_observations("GDP")
        assert result[0]["value"] is None

    def test_start_end_date_params(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={"observations": []})
        provider.get_observations("GDP", start_date="2024-01-01", end_date="2024-12-31")
        _, kwargs = provider.session.get.call_args
        assert kwargs["params"]["observation_start"] == "2024-01-01"
        assert kwargs["params"]["observation_end"] == "2024-12-31"

    def test_no_dates_omits_params(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={"observations": []})
        provider.get_observations("GDP")
        _, kwargs = provider.session.get.call_args
        assert "observation_start" not in kwargs["params"]
        assert "observation_end" not in kwargs["params"]

    def test_empty_observations(self):
        provider = _make_provider()
        provider.session.get.return_value = _make_response(json_data={"observations": []})
        assert provider.get_observations("GDP") == []

    def test_none_response_raises(self):
        provider = _make_provider()
        provider.session.get.return_value = None
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            provider.get_observations("GDP")


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_missing_key_raises(self):
        with patch("sources.fred.provider.RequestSession"):
            with patch.dict("os.environ", {}, clear=True):
                from sources.fred.provider import FredProvider
                with pytest.raises(ValueError, match="FRED API key required"):
                    FredProvider(api_key="")

    def test_reads_env_key(self):
        with patch("sources.fred.provider.RequestSession"):
            with patch.dict("os.environ", {"FRED_API_KEY": "env-key-123"}):
                from sources.fred.provider import FredProvider
                p = FredProvider()
                assert p.api_key == "env-key-123"
