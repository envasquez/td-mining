#!/usr/bin/env python3
"""
Scraper for Team Trail Outdoors (TTO-TX) tournament results.

This script:
1. Scrapes the TTO results page to find tournament links
2. Visits each tournament page to find PDF result links
3. Downloads PDFs and extracts tournament result data using pdfplumber
4. Saves results as JSON files for later loading into the database
"""

import json
import logging
import re
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.tto-tx.com"
RESULTS_URL = f"{BASE_URL}/results/"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "tto"
LINKS_FILE = Path(__file__).resolve().parent.parent / "links" / "tto_links.json"
PDF_DIR = DATA_DIR / "pdfs"

# Create directories
DATA_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)


def get_tournament_links(session: requests.Session) -> list[dict]:
    """Scrape the results page to get all tournament links."""
    logger.info(f"Fetching tournament links from {RESULTS_URL}")
    response = session.get(RESULTS_URL, timeout=30)
    soup = BeautifulSoup(response.content, "html.parser")

    tournaments = []
    for link in soup.find_all("a", href=re.compile(r"/tournament/")):
        href = link.get("href", "")
        if href and "/tournament/" in href:
            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
            text = link.get_text(strip=True)
            if text and full_url not in [t["url"] for t in tournaments]:
                tournaments.append({"url": full_url, "name": text})

    logger.info(f"Found {len(tournaments)} tournament links")
    return tournaments


def get_pdf_links_from_tournament(session: requests.Session, url: str) -> list[str]:
    """Get PDF result links from a tournament page."""
    logger.info(f"Fetching PDF links from {url}")
    try:
        response = session.get(url, timeout=30)
        soup = BeautifulSoup(response.content, "html.parser")

        pdf_links = []
        for link in soup.find_all("a", href=re.compile(r"\.pdf", re.IGNORECASE)):
            href = link.get("href", "")
            if href:
                full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                link_text = link.get_text(strip=True).lower()
                if any(
                    kw in link_text or kw in href.lower()
                    for kw in ["result", "final", "standing"]
                ):
                    if full_url not in pdf_links:
                        pdf_links.append(full_url)

        return pdf_links
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return []


def download_pdf(session: requests.Session, url: str) -> Path | None:
    """Download a PDF file and return its local path."""
    filename = url.split("/")[-1]
    local_path = PDF_DIR / filename

    if local_path.exists():
        logger.info(f"PDF already exists: {filename}")
        return local_path

    try:
        logger.info(f"Downloading PDF: {filename}")
        response = session.get(url, timeout=60)
        response.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(response.content)
        return local_path
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        return None


def find_column_indices(header: list[str]) -> dict:
    """Find the indices of relevant columns in the header."""
    indices = {}
    header_lower = [str(h).lower().strip() if h else "" for h in header]

    for i, col in enumerate(header_lower):
        if "place" in col and "indices" not in indices:
            indices["place"] = i
        elif "angler" in col and "1" in col:
            indices["angler1_start"] = i
        elif "angler" in col and "2" in col:
            indices["angler2_start"] = i
        elif "team" in col or "name" in col:
            indices["team"] = i
        elif "net" in col and "weight" in col:
            indices["weight"] = i
        elif "weight" in col and "weight" not in indices:
            indices["weight"] = i
        elif "big" in col and "bass" in col:
            indices["big_bass"] = i
        elif col == "bb":
            indices["big_bass"] = i
        elif "fish" in col or col == "#":
            indices["fish"] = i

    return indices


def extract_results_from_pdf(pdf_path: Path) -> list[dict]:
    """Extract tournament results from a PDF file."""
    results = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue

                    # Find header row
                    header_idx = None
                    for i, row in enumerate(table):
                        if row and any(
                            cell and "place" in str(cell).lower() for cell in row
                        ):
                            header_idx = i
                            break

                    if header_idx is None:
                        continue

                    header = table[header_idx]
                    col_indices = find_column_indices(header)

                    if "place" not in col_indices:
                        continue

                    # Process data rows
                    for row in table[header_idx + 1 :]:
                        if not row or not any(row):
                            continue

                        result = parse_result_row(row, col_indices, header)
                        if result and result.get("place"):
                            # Avoid duplicates
                            if not any(
                                r["place"] == result["place"]
                                and r.get("angler1") == result.get("angler1")
                                for r in results
                            ):
                                results.append(result)

    except Exception as e:
        logger.error(f"Error extracting from {pdf_path}: {e}")

    return results


def parse_result_row(row: list, col_indices: dict, header: list) -> dict | None:
    """Parse a result row into a structured dict."""
    if not row or not any(row):
        return None

    result = {}

    # Extract place
    place_idx = col_indices.get("place", 0)
    if place_idx < len(row):
        place_val = str(row[place_idx]).strip() if row[place_idx] else ""
        match = re.search(r"(\d+)", place_val)
        if match:
            result["place"] = int(match.group(1))
        else:
            return None

    # Extract anglers - handle split columns (first name, last name)
    if "angler1_start" in col_indices:
        a1_idx = col_indices["angler1_start"]
        # Check if there's a None column after (indicating split first/last)
        if a1_idx + 1 < len(header) and header[a1_idx + 1] is None:
            first = (
                str(row[a1_idx]).strip() if a1_idx < len(row) and row[a1_idx] else ""
            )
            last = (
                str(row[a1_idx + 1]).strip()
                if a1_idx + 1 < len(row) and row[a1_idx + 1]
                else ""
            )
            result["angler1"] = f"{first} {last}".strip()
        else:
            result["angler1"] = (
                str(row[a1_idx]).strip() if a1_idx < len(row) and row[a1_idx] else ""
            )

    if "angler2_start" in col_indices:
        a2_idx = col_indices["angler2_start"]
        if a2_idx + 1 < len(header) and header[a2_idx + 1] is None:
            first = (
                str(row[a2_idx]).strip() if a2_idx < len(row) and row[a2_idx] else ""
            )
            last = (
                str(row[a2_idx + 1]).strip()
                if a2_idx + 1 < len(row) and row[a2_idx + 1]
                else ""
            )
            result["angler2"] = f"{first} {last}".strip()
        else:
            result["angler2"] = (
                str(row[a2_idx]).strip() if a2_idx < len(row) and row[a2_idx] else ""
            )

    # Fallback to team column if no angler columns
    if "angler1" not in result and "team" in col_indices:
        team_idx = col_indices["team"]
        result["team"] = (
            str(row[team_idx]).strip() if team_idx < len(row) and row[team_idx] else ""
        )

    # Extract weight
    if "weight" in col_indices:
        weight_idx = col_indices["weight"]
        if weight_idx < len(row):
            result["weight"] = parse_weight(row[weight_idx])

    # Extract big bass
    if "big_bass" in col_indices:
        bb_idx = col_indices["big_bass"]
        if bb_idx < len(row):
            result["big_bass"] = parse_weight(row[bb_idx])

    # Extract fish count
    if "fish" in col_indices:
        fish_idx = col_indices["fish"]
        if fish_idx < len(row) and row[fish_idx]:
            match = re.search(r"(\d+)", str(row[fish_idx]))
            if match:
                result["fish"] = int(match.group(1))

    return result if result.get("place") else None


def parse_weight(value) -> float | None:
    """Parse weight from various formats."""
    if not value:
        return None

    value = str(value).strip()
    if not value:
        return None

    # Format: 15.45 (decimal pounds)
    match = re.match(r"^(\d+)\.(\d+)$", value)
    if match:
        return float(value)

    # Format: 15-08 (pounds-ounces)
    match = re.match(r"^(\d+)-(\d+)$", value)
    if match:
        lbs = int(match.group(1))
        oz = int(match.group(2))
        return round(lbs + oz / 16, 2)

    # Just a number
    match = re.search(r"(\d+\.?\d*)", value)
    if match:
        return float(match.group(1))

    return None


def extract_tournament_info_from_url(url: str) -> dict:
    """Extract lake name and other info from tournament URL."""
    match = re.search(r"/tournament/([^/]+)/?", url)
    if match:
        slug = match.group(1)
        slug = re.sub(r"-\d+$", "", slug)
        lake = slug.replace("-", " ").title()
        return {"lake": lake, "slug": slug}
    return {}


def extract_date_from_filename(filename: str) -> str | None:
    """Try to extract date from PDF filename."""
    # Patterns like: 6.15.24, 5.4.2024, JUNE-14-2025
    patterns = [
        r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})",  # 6.15.24
        r"(\d{1,2})-(\d{1,2})-(\d{2,4})",  # 6-15-24
        r"(\d{4})",  # Just year
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groups()
            if len(groups) == 3:
                month, day, year = groups
                if len(year) == 2:
                    year = f"20{year}"
                return f"{year}-{int(month):02d}-{int(day):02d}"
            elif len(groups) == 1:
                return groups[0]  # Just return year

    return None


def save_results(
    tournament_url: str, pdf_url: str, results: list[dict], tournament_name: str
) -> None:
    """Save extracted results to JSON file."""
    if not results:
        return

    tournament_info = extract_tournament_info_from_url(tournament_url)
    pdf_name = pdf_url.split("/")[-1].replace(".pdf", "")
    date = extract_date_from_filename(pdf_name)

    data = {
        "metadata": {
            "source_url": tournament_url,
            "pdf_url": pdf_url,
            "tournament_name": tournament_name,
            "lake": tournament_info.get("lake", "Unknown"),
            "tournament_trail": "TTO Team Trail",
            "date": date,
        },
        "results": results,
    }

    output_file = DATA_DIR / f"{pdf_name}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved {len(results)} results to {output_file}")


def main():
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )

    # Get tournament links
    tournaments = get_tournament_links(session)

    # Save tournament links
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tournaments, f, indent=2)
    logger.info(f"Saved {len(tournaments)} tournament links to {LINKS_FILE}")

    # Process each tournament
    for tournament in tournaments:
        url = tournament["url"]
        name = tournament["name"]
        pdf_links = get_pdf_links_from_tournament(session, url)

        for pdf_url in pdf_links:
            pdf_path = download_pdf(session, pdf_url)
            if pdf_path:
                results = extract_results_from_pdf(pdf_path)
                if results:
                    save_results(url, pdf_url, results, name)
                else:
                    logger.warning(f"No results extracted from {pdf_path}")

    logger.info("Done scraping TTO results")


if __name__ == "__main__":
    main()
