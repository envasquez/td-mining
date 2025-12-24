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
TTZ_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ttz1"


def classify_ttz_trail(url: str, title: str) -> str:
    """
    Classify a TTZ tournament into its trail type based on URL and title.
    Returns one of: TTZ Team Trail, TTZ Tuesday Night, TTZ Wednesday Night,
    TTZ Thursday Night, TTZ Championship
    """
    url_lower = url.lower()
    title_lower = title.lower()

    # Check for championship
    if "championship" in url_lower or "championship" in title_lower:
        return "TTZ Championship"

    # Check for specific night events (including abbreviated forms)
    if "tuesday" in url_lower or "tuesday" in title_lower or "-tue-" in url_lower:
        return "TTZ Tuesday Night"
    if "wednesday" in url_lower or "wednesday" in title_lower or "-wed-" in url_lower:
        return "TTZ Wednesday Night"
    if "thursday" in url_lower or "thursday" in title_lower or "-thur-" in url_lower:
        return "TTZ Thursday Night"

    # Check URL patterns for year-based results (usually Tuesday night)
    # e.g., /category/results/2025/ pages link to Tuesday night events
    if "/category/results/" in url_lower:
        return "TTZ Tuesday Night"

    # If TTZ TRAIL is in the title/header, it's a team trail event
    if "ttz trail" in title_lower or "ttz-trail" in url_lower:
        return "TTZ Team Trail"

    # Default to Team Trail for ttz1.com results
    return "TTZ Team Trail"


def parse_date(metadata: dict, url: str) -> str | None:
    """
    Parse date from multiple possible sources in the metadata.
    Returns ISO format date string or None.
    """
    # Try full_results_header first (e.g., "2025 TTZ TRAIL – Buchanan Full Results – Jan. 25, 2025")
    header = metadata.get("full_results_header", "")
    if header:
        date = extract_date_from_text(header)
        if date:
            return date

    # Try event_header (e.g., "TTZ TRAIL – TRAVIS – Apr. 2nd, 2016")
    event_header = metadata.get("event_header", "")
    if event_header:
        date = extract_date_from_text(event_header)
        if date:
            return date

    # Try page_title
    title = metadata.get("page_title", "")
    if title:
        date = extract_date_from_text(title)
        if date:
            return date

    # Try published_date (WordPress datetime)
    published = metadata.get("published_date", "")
    if published:
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            return dt.date().isoformat()
        except (ValueError, TypeError):
            pass

    # Try to extract year from URL slug as last resort
    # e.g., https://ttz1.com/ttz2025buchanan/
    year_match = re.search(r"ttz(\d{4})", url.lower())
    if year_match:
        year = int(year_match.group(1))
        # Return January 1st of that year as placeholder
        return f"{year}-01-01"

    # Try to extract date from filename patterns like ttz-travis-tue-night-5-21-19
    # or ttz-austin-wed-night-8-25-16 (month-day-year format)
    filename_match = re.search(r"-(\d{1,2})-(\d{1,2})-(\d{2})(?:\.json)?(?:/)?$", url)
    if filename_match:
        month, day, year_short = filename_match.groups()
        year = int(year_short)
        # Convert 2-digit year to 4-digit (16 -> 2016, 23 -> 2023)
        if year < 50:
            year += 2000
        else:
            year += 1900
        try:
            return f"{year}-{int(month):02d}-{int(day):02d}"
        except ValueError:
            pass

    return None


def extract_date_from_text(text: str) -> str | None:
    """
    Extract a date from various text formats.
    """
    # Remove ordinal suffixes (1st, 2nd, 3rd, 4th, etc.)
    text_clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text)

    # Common date patterns
    patterns = [
        # "January 25, 2025" or "Jan. 25, 2025" or "Jan 25, 2025"
        (r"(Jan(?:uary)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Jan\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Jan\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Feb(?:ruary)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Feb\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Feb\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Mar(?:ch)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Mar\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Mar\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Apr(?:il)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Apr\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Apr\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(May\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Jun(?:e)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Jun\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Jun\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Jul(?:y)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Jul\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Jul\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Aug(?:ust)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Aug\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Aug\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Sep(?:tember)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Sep\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Sep\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Oct(?:ober)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Oct\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Oct\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Nov(?:ember)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Nov\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Nov\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        (r"(Dec(?:ember)?\.?\s+\d{1,2},?\s+\d{4})", "%B %d, %Y"),
        (r"(Dec\.?\s+\d{1,2},?\s+\d{4})", "%b. %d, %Y"),
        (r"(Dec\s+\d{1,2},?\s+\d{4})", "%b %d, %Y"),
        # Date range like "October 4-5, 2025" - take first date
        (r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2})-\d{1,2},?\s+(\d{4})", None),
    ]

    for pattern, fmt in patterns:
        match = re.search(pattern, text_clean, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Handle date ranges
            if fmt is None:
                # Extract month, day, year from range pattern
                range_match = re.search(
                    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})-\d{1,2},?\s+(\d{4})",
                    text_clean,
                    re.IGNORECASE,
                )
                if range_match:
                    month, day, year = (
                        range_match.group(1),
                        range_match.group(2),
                        range_match.group(3),
                    )
                    date_str = f"{month} {day}, {year}"
                    fmt = "%B %d, %Y"
                else:
                    continue

            # Clean up the date string
            date_str = date_str.replace(",", ", ").replace("  ", " ").strip()
            date_str = re.sub(r",\s*,", ",", date_str)

            # Try multiple format variations
            for try_fmt in [fmt, fmt.replace(".", ""), fmt.replace("%b.", "%b")]:
                try:
                    dt = datetime.strptime(date_str.strip(), try_fmt.strip())
                    return dt.date().isoformat()
                except ValueError:
                    continue

    return None


def extract_lake(metadata: dict, url: str) -> str | None:
    """
    Extract lake name from metadata or URL.
    """
    # Check all text sources for lake names
    sources = [
        metadata.get("full_results_header", ""),
        metadata.get("event_header", ""),
        metadata.get("page_title", ""),
        url,
    ]

    combined = " ".join(sources).lower()

    for identifier, lake_name in LAKES.items():
        if identifier in combined:
            return lake_name

    return None


def normalize_result(row: dict) -> dict:
    """
    Normalize varying column names to a standard format.
    """
    # Create case-insensitive lookup
    row_lower = {k.lower().strip(): v for k, v in row.items()}

    def get_value(keys: list):
        for key in keys:
            key_lower = key.lower().strip()
            if key_lower in row_lower:
                val = row_lower[key_lower]
                # Handle NaN values
                if isinstance(val, float) and val != val:  # NaN check
                    return None
                return val
        return None

    place = get_value(["PLACE", "PL", "PL.", "Pl"])
    angler1 = get_value(["ANGLER 1", "Angler 1", "ANGLER1", "Angler1"])
    angler2 = get_value(["ANGLER 2", "Angler 2", "ANGLER2", "Angler2"])
    fish = get_value(["# FISH", "FISH", "Fish", "#FISH", "# Fish"])
    big_bass = get_value(["BIG BASS", "Big Bass", "BIGBASS", "BB"])
    weight = get_value(
        [
            "TOTAL WEIGHT (lbs)",
            "TOTAL WEIGHT",
            "Total Weight",
            "Weight",
            "weight",
            "Wt.",
            "WT",
            "WEIGHT",
        ]
    )
    prize = get_value(["PRIZE", "Prize", "PAYOUT", "Payout"])

    # Handle big_bass that's stored as prize string like "$560"
    if big_bass and isinstance(big_bass, str) and big_bass.startswith("$"):
        big_bass = None

    return {
        "place": place,
        "angler1": angler1,
        "angler2": angler2,
        "fish": fish,
        "big_bass": big_bass,
        "weight": weight,
        "prize": prize,
    }


def load_ttz_data():
    """
    Load all TTZ tournament data from JSON files into the database.
    """
    if not TTZ_DATA_DIR.exists():
        logger.error(f"TTZ data directory not found: {TTZ_DATA_DIR}")
        return

    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.cursor()

    loaded = 0
    skipped = 0
    errors = 0

    try:
        for filepath in sorted(TTZ_DATA_DIR.glob("*.json")):
            # Skip AOY standings files
            if "aoy" in filepath.name.lower() or "standings" in filepath.name.lower():
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

            url = metadata.get("page_url", "")
            title = metadata.get("page_title", "")

            # Parse date
            date_str = parse_date(metadata, url)
            if not date_str:
                logger.warning(f"Could not parse date from {filepath.name}, skipping")
                skipped += 1
                continue

            # Extract lake
            lake = extract_lake(metadata, url)

            # Classify trail type
            trail = classify_ttz_trail(url, title)

            # Generate tournament name
            tournament_name = (
                metadata.get("full_results_header")
                or metadata.get("event_header")
                or title
                or filepath.stem
            )

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
                (date_str, lake, None, tournament_name, trail),
            )
            tournament_id = cursor.lastrowid
            logger.info(f"✅ Inserted tournament: {tournament_name} ({trail})")

            # Insert results
            for row in results:
                normalized = normalize_result(row)
                if normalized["place"] is None:
                    continue

                cursor.execute(
                    """
                    INSERT INTO results (
                        tournament_id, place, skeeter_boat, angler1, angler1_hometown,
                        angler2, angler2_hometown, fish, big_bass, weight, prize
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tournament_id,
                        normalized["place"],
                        None,  # skeeter_boat
                        normalized["angler1"],
                        None,  # angler1_hometown
                        normalized["angler2"],
                        None,  # angler2_hometown
                        normalized["fish"],
                        normalized["big_bass"],
                        normalized["weight"],
                        normalized["prize"],
                    ),
                )

            loaded += 1

    finally:
        conn.commit()
        conn.close()

    logger.info(f"🏁 Done! Loaded: {loaded}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    load_ttz_data()
