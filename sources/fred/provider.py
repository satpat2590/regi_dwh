"""
FRED (Federal Reserve Economic Data) provider.

Fetches economic indicator series metadata and observations from the FRED API.
https://fred.stlouisfed.org/docs/api/fred/

No ABC needed — FRED is the sole source for this data.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.session import RequestSession

logger = logging.getLogger(__name__)

BASE_URL = "https://api.stlouisfed.org/fred"


class FredProvider:
    """Provider for FRED economic data series."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FRED_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "FRED API key required. Set FRED_API_KEY env var or pass api_key. "
                "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
            )
        self.session = RequestSession()
        self.name = "FRED"

    def get_series_info(self, series_id: str) -> Dict:
        """
        Fetch metadata for a FRED series.

        Returns:
            Dict with keys: series_id, title, units, frequency,
            seasonal_adj, last_updated, notes
        """
        url = f"{BASE_URL}/series"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
        }
        resp = self.session.get(url, params=params)
        if not resp:
            raise RuntimeError(f"Failed to fetch series info for {series_id}")

        data = resp.json()
        serieses = data.get("serieses", [])
        if not serieses:
            raise RuntimeError(f"No series found for {series_id}")

        s = serieses[0]
        return {
            "series_id": s.get("id", series_id),
            "title": s.get("title", ""),
            "units": s.get("units", ""),
            "frequency": s.get("frequency", ""),
            "seasonal_adj": s.get("seasonal_adjustment", ""),
            "last_updated": s.get("last_updated", ""),
            "notes": s.get("notes", ""),
        }

    def get_observations(
        self,
        series_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict]:
        """
        Fetch observations for a FRED series.

        Args:
            series_id: FRED series ID (e.g. 'GDP', 'UNRATE')
            start_date: Start date YYYY-MM-DD (optional)
            end_date: End date YYYY-MM-DD (optional)

        Returns:
            List of dicts with keys: series_id, date, value
            Missing values (FRED uses '.') are converted to None.
        """
        url = f"{BASE_URL}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
        }
        if start_date:
            params["observation_start"] = start_date
        if end_date:
            params["observation_end"] = end_date

        resp = self.session.get(url, params=params)
        if not resp:
            raise RuntimeError(f"Failed to fetch observations for {series_id}")

        data = resp.json()
        observations = []
        for obs in data.get("observations", []):
            raw_val = obs.get("value", ".")
            value = None if raw_val == "." else float(raw_val)
            observations.append({
                "series_id": series_id,
                "date": obs.get("date", ""),
                "value": value,
            })

        return observations
