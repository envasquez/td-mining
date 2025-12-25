#!/usr/bin/env python3
"""
Load MediaBass tournament data from JSON files into the database.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from lakes import LAKES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

DB_FILE = Path(__file__).resolve().parent.parent / "tournaments.db"
MEDIABASS_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mediabass"


def extract_lake(metadata: dict) -> str | None:
    """Extract lake name from metadata."""
    lake_raw = metadata.get("lake_text", "")
    if not lake_raw:
        # Try to extract from page title
        title = metadata.get("page_title", "")
        if "Lake" in title:
            match = re.search(r"Lake\s+(\w+)", title)
            if match:
                lake_raw = match.group(1)

    if not lake_raw:
        return None

    # Normalize the lake name using LAKES mapping
    lake_lower = lake_raw.lower()
    for identifier, lake_name in LAKES.items():
        if identifier in lake_lower:
            return lake_name

    # Return as-is if not in mapping (add "Lake" prefix if needed)
    if not lake_raw.lower().startswith("lake"):
        return f"Lake {lake_raw}"
    return lake_raw


def parse_date(metadata: dict, filename: str) -> str | None:
    """Parse date from metadata or derive from year."""
    # Try date_text field first (formats like "December 14, 2025" or "12/14/25")
    date_text = metadata.get("date_text", "")
    if date_text:
        # Try MM/DD/YY or MM/DD/YYYY format
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", date_text)
        if match:
            month, day, year = match.groups()
            if len(year) == 2:
                year = f"20{year}" if int(year) < 50 else f"19{year}"
            try:
                return f"{year}-{int(month):02d}-{int(day):02d}"
            except ValueError:
                pass

        # Try "Month Day, Year" format
        date_patterns = [
            (
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
                "%B %d %Y",
            ),
            (
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})",
                "%b %d %Y",
            ),
        ]
        for pattern, fmt in date_patterns:
            match = re.search(pattern, date_text, re.IGNORECASE)
            if match:
                try:
                    month, day, year = match.groups()
                    date_str = f"{month} {day} {year}"
                    dt = datetime.strptime(date_str, fmt)
                    return dt.date().isoformat()
                except ValueError:
                    continue

    # Fall back to year from metadata + tournament number
    year = metadata.get("year")
    if year:
        # Extract tournament number from filename to estimate month
        # Tournaments typically run monthly, so tournament 1 = January, etc.
        match = re.search(r"_(\d+)\.json$", filename)
        if match:
            tournament_num = int(match.group(1))
            # Most divisions have ~12 tournaments per year
            month = min(tournament_num, 12)
            return f"{year}-{month:02d}-01"
        return f"{year}-01-01"

    return None


def generate_tournament_name(metadata: dict, filename: str) -> str:
    """Generate a tournament name from available data."""
    division = metadata.get("display_name", "")
    lake = metadata.get("lake_text", "")
    year = metadata.get("year", "")

    if lake and division:
        return f"MediaBass {division} - {lake} ({year})"
    if division:
        return f"MediaBass {division} ({year})"

    # Fallback to filename
    return f"MediaBass {filename.replace('.json', '').replace('_', ' ')}"


def load_mediabass_data():
    """Load all MediaBass tournament data from JSON files into the database."""
    if not MEDIABASS_DATA_DIR.exists():
        logger.error(f"MediaBass data directory not found: {MEDIABASS_DATA_DIR}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    loaded = 0
    skipped = 0
    errors = 0

    try:
        for filepath in sorted(MEDIABASS_DATA_DIR.glob("*.json")):
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON in {filepath.name}: {e}")
                errors += 1
                continue

            metadata = data.get("metadata", {})
            results = data.get("results", [])

            if not results:
                logger.debug(f"No results in {filepath.name}, skipping")
                skipped += 1
                continue

            # Parse date
            date_str = parse_date(metadata, filepath.name)
            if not date_str:
                logger.warning(f"Could not parse date from {filepath.name}, skipping")
                skipped += 1
                continue

            # Extract lake
            lake = extract_lake(metadata)

            # Get tournament trail
            trail = metadata.get("tournament_trail", "MediaBass")

            # Generate tournament name
            tournament_name = generate_tournament_name(metadata, filepath.name)

            # Check if already exists
            cursor.execute(
                "SELECT id FROM tournaments WHERE date = ? AND tournament = ?",
                (date_str, tournament_name),
            )
            if cursor.fetchone():
                logger.debug(f"Already exists: {tournament_name} on {date_str}")
                skipped += 1
                continue

            # Insert tournament
            cursor.execute(
                """
                INSERT INTO tournaments (date, lake, region, tournament, tournament_trail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (date_str, lake, "Texas", tournament_name, trail),
            )
            tournament_id = cursor.lastrowid
            logger.info(f"✅ Inserted tournament: {tournament_name}")

            # Insert results
            for row in results:
                place = row.get("place")
                if place is None:
                    continue

                angler1 = row.get("angler1", "")
                angler2 = row.get("angler2", "")
                weight = row.get("weight")
                fish = row.get("fish")
                big_bass = row.get("big_bass")

                cursor.execute(
                    """
                    INSERT INTO results (
                        tournament_id, place, skeeter_boat, angler1, angler1_hometown,
                        angler2, angler2_hometown, fish, big_bass, weight, prize
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tournament_id,
                        place,
                        None,  # skeeter_boat
                        angler1,
                        None,  # angler1_hometown
                        angler2,
                        None,  # angler2_hometown
                        fish,
                        big_bass,
                        weight,
                        None,  # prize
                    ),
                )

            loaded += 1

    finally:
        conn.commit()
        conn.close()

    logger.info(f"🏁 Done! Loaded: {loaded}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    load_mediabass_data()
