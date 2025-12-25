#!/usr/bin/env python3
"""
Scraper for MediaBass tournament results.

This script:
1. Scrapes the MediaBass site to find Texas tournament divisions
2. Visits each division page to extract tournament results
3. Saves results as JSON files for later loading into the database
"""

import json
import logging
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

BASE_URL = "https://mediabass.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mediabass"

# Create directories
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Texas divisions to scrape (Teams and Individuals)
# Format: (division_code, display_name, is_team)
# URL structure: https://mediabass.com/{year_code}/TX/{division}/{N}.shtml
TEXAS_DIVISIONS = [
    # Teams - use actual MediaBass division codes
    ("AUSTIN", "Austin Teams", True),
    ("CENTRAL", "Central Teams", True),
    ("COWTOWN", "Cowtown Teams", True),
    ("DEEPEAST", "Deep East Teams", True),
    ("EAST", "East Teams", True),
    ("FORK", "Fork Teams", True),
    ("HEARTLAND", "Heartland Teams", True),
    ("NORTHEAST", "Northeast Teams", True),
    # Individuals - prefixed with 'I'
    ("IAUS", "Austin Individuals", False),
    ("ICENT", "Central Individuals", False),
    ("ICOW", "Cowtown Individuals", False),
    ("IDEEPEAST", "Deep East Individuals", False),
    ("IEAST", "East Individuals", False),
    ("IFORK", "Fork Individuals", False),
    ("IHEARTLAND", "Heartland Individuals", False),
    ("INE", "Northeast Individuals", False),
]

# Years to scrape (MediaBass uses 2kYY format for years 2000+)
# Start from 1998 which appears to be when TX divisions started
YEARS = list(range(1998, 2027))


def get_year_code(year: int) -> str:
    """Convert year to MediaBass URL format."""
    if year >= 2000:
        return f"2k{year % 100:02d}"
    return str(year)


def fetch_page(session: requests.Session, url: str) -> BeautifulSoup | None:
    """Fetch a page and return BeautifulSoup object."""
    try:
        response = session.get(url, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")
    except requests.RequestException as e:
        logger.debug(f"Error fetching {url}: {e}")
        return None


def parse_weight(value: str) -> float | None:
    """Parse weight from various formats."""
    if not value:
        return None

    value = str(value).strip()
    if not value or value == "-" or value.lower() == "dq":
        return None

    # Remove any non-numeric chars except . and -
    # Format: 15.45 (decimal pounds)
    match = re.search(r"(\d+\.?\d*)", value)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None

    return None


def parse_place(value: str) -> int | None:
    """Parse place from string."""
    if not value:
        return None

    match = re.search(r"(\d+)", str(value))
    if match:
        return int(match.group(1))
    return None


def parse_fish_count(value: str) -> int | None:
    """Parse fish count from string."""
    if not value:
        return None

    match = re.search(r"(\d+)", str(value))
    if match:
        return int(match.group(1))
    return None


def extract_results_from_page(
    soup: BeautifulSoup, is_team: bool
) -> tuple[list[dict], dict]:
    """Extract tournament results from a page."""
    results = []
    metadata = {}

    # Find tournament info - look for header/title elements
    # The page typically has tournament name and date in various places
    title = soup.find("title")
    if title:
        metadata["page_title"] = title.get_text(strip=True)

    # Look for date info - often in the page content
    # MediaBass pages have dates in various formats
    page_text = soup.get_text()

    # Try to find date patterns in the page
    date_patterns = [
        r"(\d{1,2}/\d{1,2}/\d{2,4})",  # MM/DD/YY or MM/DD/YYYY
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            metadata["date_text"] = match.group(1)
            break

    # Find lake name - often in headers or title
    lake_patterns = [
        r"Lake\s+(\w+(?:\s+\w+)?)",
        r"on\s+(\w+(?:\s+\w+)?)\s+Lake",
        r"at\s+(\w+(?:\s+\w+)?)",
    ]
    for pattern in lake_patterns:
        match = re.search(pattern, page_text, re.IGNORECASE)
        if match:
            metadata["lake_text"] = match.group(1)
            break

    # Find results table - MediaBass uses standard HTML tables
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Check if this looks like a results table
        header_row = rows[0]
        header_cells = header_row.find_all(["th", "td"])
        header_text = [cell.get_text(strip=True).lower() for cell in header_cells]

        # Look for typical result table headers
        has_place = any("place" in h or "pl" == h or "#" == h for h in header_text)
        has_weight = any(
            "weight" in h or "wt" in h or "lbs" in h or "pounds" in h
            for h in header_text
        )

        if not (has_place or has_weight):
            continue

        # Find column indices
        col_indices = {}
        for i, h in enumerate(header_text):
            if "place" in h or h == "pl" or h == "#":
                col_indices["place"] = i
            elif "angler 1" in h or "angler1" in h:
                col_indices["angler1"] = i
            elif "angler 2" in h or "angler2" in h:
                col_indices["angler2"] = i
            elif "angler" in h or "name" in h or "team" in h:
                if "angler" not in col_indices and "angler1" not in col_indices:
                    col_indices["angler"] = i
            elif ("bass" in h or h == "# bass") and "big" not in h:
                col_indices["fish"] = i
            elif ("weight" in h or "wt" in h or "lbs" in h or "pounds" in h) and (
                "big" not in h
            ):
                col_indices["weight"] = i
            elif "big" in h:
                col_indices["big_bass"] = i
            elif "win" in h or "prize" in h or "$" in h:
                col_indices["prize"] = i

        # If no explicit place column, assume first column
        if "place" not in col_indices:
            col_indices["place"] = 0

        # Process data rows
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            cell_values = [cell.get_text(strip=True) for cell in cells]

            # Skip empty rows or header-like rows
            if not any(cell_values):
                continue
            if cell_values[0].lower() in ["place", "pl", "#", ""]:
                continue

            result = {}

            # Extract place
            place_idx = col_indices.get("place", 0)
            if place_idx < len(cell_values):
                result["place"] = parse_place(cell_values[place_idx])

            # Extract angler(s) - check for separate columns first
            if "angler1" in col_indices:
                a1_idx = col_indices["angler1"]
                if a1_idx < len(cell_values):
                    result["angler1"] = cell_values[a1_idx].strip()
                if "angler2" in col_indices:
                    a2_idx = col_indices["angler2"]
                    if a2_idx < len(cell_values):
                        result["angler2"] = cell_values[a2_idx].strip()
                    else:
                        result["angler2"] = ""
                else:
                    result["angler2"] = ""
            elif "angler" in col_indices:
                angler_idx = col_indices["angler"]
                if angler_idx < len(cell_values):
                    angler_text = cell_values[angler_idx]
                    if is_team:
                        # Try to split team into two anglers
                        separators = [" / ", "/", " & ", " and ", " - "]
                        for sep in separators:
                            if sep in angler_text:
                                parts = angler_text.split(sep, 1)
                                result["angler1"] = parts[0].strip()
                                result["angler2"] = (
                                    parts[1].strip() if len(parts) > 1 else ""
                                )
                                break
                        else:
                            result["angler1"] = angler_text
                            result["angler2"] = ""
                    else:
                        result["angler1"] = angler_text
                        result["angler2"] = ""

            # Extract fish count
            fish_idx = col_indices.get("fish")
            if fish_idx is not None and fish_idx < len(cell_values):
                result["fish"] = parse_fish_count(cell_values[fish_idx])

            # Extract weight
            weight_idx = col_indices.get("weight")
            if weight_idx is not None and weight_idx < len(cell_values):
                result["weight"] = parse_weight(cell_values[weight_idx])

            # Extract big bass
            bb_idx = col_indices.get("big_bass")
            if bb_idx is not None and bb_idx < len(cell_values):
                result["big_bass"] = parse_weight(cell_values[bb_idx])

            # Only add if we have valid data
            if result.get("place") and (result.get("angler1") or result.get("weight")):
                results.append(result)

        # If we found results, break (use first valid table)
        if results:
            break

    return results, metadata


def get_tournament_pages(
    session: requests.Session, year: int, division: str
) -> list[str]:
    """Get all tournament page URLs for a division in a year."""
    year_code = get_year_code(year)
    pages = []

    # MediaBass uses N.shtml where N is tournament number (1, 2, 3, etc.)
    # We'll try pages 1-20 to cover a full season
    for n in range(1, 21):
        url = f"{BASE_URL}/{year_code}/TX/{division}/{n}.shtml"
        pages.append(url)

    return pages


def scrape_division(
    session: requests.Session, division: str, display_name: str, is_team: bool
) -> int:
    """Scrape all tournaments for a division across all years."""
    total_saved = 0

    for year in YEARS:
        pages = get_tournament_pages(session, year, division)

        for url in pages:
            soup = fetch_page(session, url)
            if soup is None:
                continue

            results, metadata = extract_results_from_page(soup, is_team)

            if not results:
                continue

            # Build output filename
            tournament_num = url.split("/")[-1].replace(".shtml", "")
            filename = f"{division}_{year}_{tournament_num}.json"

            # Add metadata
            metadata["source_url"] = url
            metadata["division"] = division
            metadata["display_name"] = display_name
            metadata["is_team"] = is_team
            metadata["year"] = year
            metadata["tournament_trail"] = "MediaBass Teams" if is_team else "MediaBass"

            data = {
                "metadata": metadata,
                "results": results,
            }

            output_file = DATA_DIR / filename
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved {len(results)} results to {filename}")
            total_saved += 1

            # Small delay to be respectful
            time.sleep(0.2)

    return total_saved


def main():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    total = 0

    for division, display_name, is_team in TEXAS_DIVISIONS:
        logger.info(f"Scraping {display_name} ({division})...")
        count = scrape_division(session, division, display_name, is_team)
        total += count
        logger.info(f"  -> Saved {count} tournaments for {display_name}")

    logger.info(f"Done! Total tournaments saved: {total}")


if __name__ == "__main__":
    main()
