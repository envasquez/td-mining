#!/usr/bin/env python3
"""
Load TTO (Team Trail Outdoors) tournament data from JSON files into the database.
"""

import json
import logging
import re
import sqlite3
from pathlib import Path

from lakes import LAKES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

DB_FILE = Path(__file__).resolve().parent.parent / "tournaments.db"
TTO_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "tto"


def extract_lake(metadata: dict) -> str | None:
    """Extract lake name from metadata."""
    lake_raw = metadata.get("lake", "")
    if not lake_raw or lake_raw == "Unknown":
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
    """Parse date from metadata or filename."""
    # First try the date field from metadata
    date_str = metadata.get("date")
    if date_str and len(date_str) == 10:  # Full ISO date YYYY-MM-DD
        return date_str

    # Try to extract from filename patterns
    # Patterns: 6.15.24, 5.4.2024, 8.10.24
    patterns = [
        (r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", "mdy"),  # 6.15.24 or 6.15.2024
        (r"-(\d{1,2})-(\d{1,2})-(\d{2,4})", "mdy"),  # -6-15-24
        (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),  # 2024-06-15 (ISO format)
    ]

    for pattern, fmt in patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groups()
            if fmt == "mdy":
                month, day, year = groups
                if len(year) == 2:
                    year = f"20{year}" if int(year) < 50 else f"19{year}"
                try:
                    return f"{year}-{int(month):02d}-{int(day):02d}"
                except ValueError:
                    continue
            elif fmt == "ymd":
                return f"{groups[0]}-{groups[1]}-{groups[2]}"

    # Try extracting year from filename
    year_match = re.search(r"(\d{4})", filename)
    if year_match:
        year = year_match.group(1)
        if 2010 <= int(year) <= 2030:
            return f"{year}-01-01"  # Placeholder date

    return None


def generate_tournament_name(metadata: dict, filename: str) -> str:
    """Generate a tournament name from available data."""
    name = metadata.get("tournament_name", "")
    if name and name != "View Results":
        return name

    lake = metadata.get("lake", "Unknown")
    date = metadata.get("date", "")

    if date:
        return f"TTO {lake} - {date}"

    # Use filename
    clean_name = filename.replace("-", " ").replace("_", " ").title()
    return f"TTO {clean_name}"


def load_tto_data():
    """Load all TTO tournament data from JSON files into the database."""
    if not TTO_DATA_DIR.exists():
        logger.error(f"TTO data directory not found: {TTO_DATA_DIR}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    loaded = 0
    skipped = 0
    errors = 0

    try:
        for filepath in sorted(TTO_DATA_DIR.glob("*.json")):
            # Skip standings/AOY files
            if any(
                x in filepath.name.lower() for x in ["standing", "aoy", "ytd", "points"]
            ):
                logger.debug(f"Skipping standings file: {filepath.name}")
                skipped += 1
                continue

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
            date_str = parse_date(metadata, filepath.stem)
            if not date_str:
                logger.warning(f"Could not parse date from {filepath.name}, skipping")
                skipped += 1
                continue

            # Extract lake
            lake = extract_lake(metadata)

            # Generate tournament name
            tournament_name = generate_tournament_name(metadata, filepath.stem)

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
                (date_str, lake, "Texas", tournament_name, "TTO Team Trail"),
            )
            tournament_id = cursor.lastrowid
            logger.info(f"✅ Inserted tournament: {tournament_name}")

            # Insert results
            for row in results:
                place = row.get("place")
                if place is None:
                    continue

                angler1 = row.get("angler1") or row.get("team", "")
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
    load_tto_data()
