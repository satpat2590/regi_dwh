"""
Company Enrichment Script

Fetches SIC codes and entity names from the SEC submissions endpoint,
maps them to sectors/industries using sic_to_sector.json, and produces
a persisted company_metadata.json for downstream consumers.

Usage:
    python enrich.py                          # Enrich the 21 pipeline tickers
    python enrich.py --tickers AAPL MSFT JPM  # Enrich specific tickers
    python enrich.py --all                    # Enrich every ticker in cik.json (slow)
"""

import argparse
import json
import os
import sys
import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from utils.session import RequestSession
from models import Company, Sector
from database import DatabaseManager


# The 21 tickers used across the analysis pipeline
PIPELINE_TICKERS = [
    'PLTR', 'MSFT', 'AAPL', 'NVDA',   # Tech
    'JPM', 'BAC', 'WFC',               # Finance
    'WMT', 'AMZN', 'COST',             # Retail
    'JNJ', 'UNH', 'PFE',              # Healthcare
    'XOM', 'CVX',                       # Energy
    'GOLD', 'VALE', 'FCX',            # Mining
    'CAT', 'GE',                        # Industrial
    'VZ'                                # Telecom
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


class SICMapper:
    """Maps SIC codes to sectors and industry groups."""

    def __init__(self):
        path = os.path.join(CONFIG_DIR, "sic_to_sector.json")
        with open(path, 'r') as f:
            data = json.load(f)
        self.ranges = data["ranges"]

    def lookup(self, sic_code: str) -> tuple[str, str]:
        """
        Given a SIC code string, return (sector, industry_group).
        Falls back to ("Unknown", "") if no match.
        """
        try:
            code = int(sic_code)
        except (ValueError, TypeError):
            return "Unknown", ""

        # Ranges are checked in order; more specific ranges listed later
        # take precedence (e.g., 7370-7379 overrides 7300-7389).
        best_match = None
        best_span = float('inf')

        for r in self.ranges:
            if r["start"] <= code <= r["end"]:
                span = r["end"] - r["start"]
                if span < best_span:
                    best_span = span
                    best_match = r

        if best_match:
            return best_match["sector"], best_match["industry_group"]

        return "Unknown", ""


def load_cik_map() -> dict:
    path = os.path.join(CONFIG_DIR, "cik.json")
    with open(path, 'r') as f:
        return json.load(f)


def load_fiscal_year_metadata() -> dict:
    path = os.path.join(REPORTS_DIR, "fiscal_year_metadata.json")
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: fiscal_year_metadata.json not found, FYE data will be empty")
        return {}


def load_existing_metadata() -> dict:
    """Load previously enriched metadata to avoid re-fetching."""
    path = os.path.join(CONFIG_DIR, "company_metadata.json")
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def fetch_company_info(reqsesh: RequestSession, cik: str) -> dict | None:
    """
    Fetch company info from SEC submissions endpoint.
    Returns dict with 'name', 'sic', 'sicDescription', etc.
    """
    cik_padded = cik.zfill(10)
    url = SUBMISSIONS_URL.format(cik=cik_padded)
    print(f"  Fetching: {url}")

    res = reqsesh.get(url)
    if res is None or res.status_code != 200:
        status = res.status_code if res else "No response"
        print(f"  Failed: {status}")
        return None

    return res.json()


def enrich_tickers(tickers: list[str]) -> None:
    """Main enrichment flow for a list of tickers."""
    start = datetime.datetime.now()

    cik_map = load_cik_map()
    fye_metadata = load_fiscal_year_metadata()
    existing = load_existing_metadata()
    sic_mapper = SICMapper()
    reqsesh = RequestSession()

    results = {}
    skipped = 0
    fetched = 0
    failed = 0

    print(f"\nEnriching {len(tickers)} tickers...\n")

    for i, ticker in enumerate(tickers, 1):
        if ticker not in cik_map:
            print(f"[{i}/{len(tickers)}] {ticker}: NOT in cik.json, skipping")
            failed += 1
            continue

        cik = cik_map[ticker]

        # Use cached data if already enriched with SIC code
        if ticker in existing and existing[ticker].get("sic_code"):
            print(f"[{i}/{len(tickers)}] {ticker}: Using cached metadata")
            results[ticker] = existing[ticker]
            # Update FYE if available
            if ticker in fye_metadata:
                results[ticker]["fye_month"] = fye_metadata[ticker].get("fiscal_year_end_month", "")
            skipped += 1
            continue

        # Fetch from SEC
        info = fetch_company_info(reqsesh, cik)
        if not info:
            print(f"[{i}/{len(tickers)}] {ticker}: Fetch failed")
            failed += 1
            continue

        sic_code = info.get("sic", "")
        sic_description = info.get("sicDescription", "")
        entity_name = info.get("name", "")

        # Map SIC to sector
        sector_name, industry_group = sic_mapper.lookup(sic_code)

        # Get FYE month
        fye_month = ""
        if ticker in fye_metadata:
            fye_month = fye_metadata[ticker].get("fiscal_year_end_month", "")

        # Validate through Pydantic model
        company = Company(
            ticker=ticker,
            cik=cik,
            entity_name=entity_name,
            sector=Sector(sector_name) if sector_name in Sector._value2member_map_ else Sector.UNKNOWN,
            industry=sic_description if sic_description else industry_group,
            sic_code=sic_code,
            fye_month=fye_month,
        )

        results[ticker] = company.model_dump()
        fetched += 1
        print(f"[{i}/{len(tickers)}] {ticker}: {entity_name} | SIC {sic_code} -> {sector_name} / {company.industry}")

    # Save results to JSON
    output_path = os.path.join(CONFIG_DIR, "company_metadata.json")
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    # Save results to SQLite
    db = DatabaseManager()
    companies = [Company(**data) for data in results.values()]
    db.upsert_companies(companies)
    db.close()

    elapsed = datetime.datetime.now() - start
    print(f"\nEnrichment complete in {elapsed}")
    print(f"  Fetched: {fetched} | Cached: {skipped} | Failed: {failed}")
    print(f"  Output:  {output_path}")
    print(f"  DB:      {db.db_path} ({len(companies)} companies)")


def main():
    parser = argparse.ArgumentParser(description="Enrich company metadata with SEC SIC codes")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to enrich")
    parser.add_argument("--all", action="store_true", help="Enrich ALL tickers in cik.json (slow)")
    args = parser.parse_args()

    if args.all:
        cik_map = load_cik_map()
        tickers = list(cik_map.keys())
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = PIPELINE_TICKERS

    enrich_tickers(tickers)


if __name__ == "__main__":
    main()
