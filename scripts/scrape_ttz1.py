import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

MIN_YEAR = 2006
MAX_YEAR = 2026
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ttz1"
LINKS_FILE = Path(__file__).resolve().parent.parent / "links" / "ttz1_links.json"

# Additional pages that contain TTZ Trail results links
TTZ_TRAIL_RESULTS_PAGE = "https://ttz1.com/ttz-trail-results/"

DATA_DIR.mkdir(exist_ok=True)
LINKS_FILE.parent.mkdir(exist_ok=True)


def generate_year_links(min_year: int, max_year: int):
    """
    e.g. https://ttz1.com/category/results/2025/
    """
    return [
        f"https://ttz1.com/category/results/{y}/" for y in range(min_year, max_year + 1)
    ]


def get_ttz_trail_links(session: requests.Session) -> list[str]:
    """
    Scrape the TTZ Trail results page for links to individual tournament results.
    This page contains links to team trail events on various lakes (not just Tuesday nights).
    The page has tabs for different years - all content is in the HTML but hidden with CSS.
    """
    links = []
    logger.info(f"Fetching TTZ Trail results page: {TTZ_TRAIL_RESULTS_PAGE}")
    try:
        resp = session.get(TTZ_TRAIL_RESULTS_PAGE, timeout=10, headers=HEADERS)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch TTZ Trail results page: {e}")
        return links

    soup = BeautifulSoup(resp.content, "html.parser")

    # Non-result pages to skip
    skip_pages = {
        "calendar",
        "2026reg",
        "tuesday-nighters",
        "wednesday-nights",
        "events",
        "rules",
        "shop",
        "corpevents",
        "about-ttz",
        "contact-us",
        "category",
        "2019aoystandings",
        "2018-aoy-standings",
        "2017-aoy-standings",
        "2016-aoy-standings",
        "2015-aoy-standings",
        "2014-aoy-standings",
    }

    # Find all links that point to ttz1.com result pages
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Skip WordPress shortlinks
        if "wp.me" in href:
            continue
        # Match ttz1.com links (http or https)
        if re.match(r"https?://ttz1\.com/", href):
            # Skip the main results page itself and navigation links
            if href.rstrip("/") == TTZ_TRAIL_RESULTS_PAGE.rstrip("/"):
                continue
            if href in ["https://ttz1.com/", "http://ttz1.com/"]:
                continue
            # Skip non-result pages
            slug = href.rstrip("/").split("/")[-1]
            if slug in skip_pages or any(
                skip in href for skip in ["aoy-standings", "aoystandings"]
            ):
                continue
            # Normalize to https
            href = href.replace("http://ttz1.com", "https://ttz1.com")
            if href not in links:
                links.append(href)
                logger.debug(f"  + found TTZ Trail link: {href}")

    logger.info(f"Found {len(links)} TTZ Trail result links")
    return links


def get_tournament_links(session: requests.Session, year_urls):
    """
    Scrape each year page for links to individual tournament result pages.
    """
    all_links = []
    if LINKS_FILE.exists() and LINKS_FILE.stat().st_size:
        logger.info(f"Loading existing links from {LINKS_FILE}")
        all_links = json.loads(LINKS_FILE.read_text())

    for url in year_urls:
        logger.info(f"Fetching tournament list: {url}")
        try:
            resp = session.get(url, timeout=10, headers=HEADERS)
            if resp.status_code == 404:
                logger.warning(f"  Year page not found (404), skipping: {url}")
                continue
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning(f"  Failed to fetch {url}: {e}")
            continue

        soup = BeautifulSoup(resp.content, "html.parser")

        # each tournament is linked in an <h2><a href=...> block
        for h2 in soup.find_all("h2"):
            a = h2.find("a", href=True)
            if not a:
                continue
            link = a["href"]
            # ensure absolute URL
            if link.startswith("/"):
                link = f"https://ttz1.com{link}"
            if link not in all_links:
                all_links.append(link)
                logger.debug(f"  + found: {link}")
            else:
                logger.debug(f"  - already have: {link}")

    # persist
    LINKS_FILE.write_text(json.dumps(all_links, indent=2))
    logger.info(f"Saved {len(all_links)} tournament links to {LINKS_FILE}")
    return all_links


def get_tournament_results(session: requests.Session, url: str):
    """
    Visit a ttz1 tournament page and extract:
      - metadata (title, date)
      - the full results table via pandas.read_html
    """
    logger.info(f"Parsing results from {url}")
    try:
        resp = session.get(url, timeout=10, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        # --- Metadata from the page ---
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # The next <h3> contains the "Full Results" header, including date and location
        full_results_h3 = soup.find("h3", string=re.compile("Full Results"))
        meta_text = full_results_h3.get_text(" ", strip=True) if full_results_h3 else ""

        # Also look for date in other h3/h4 tags that contain lake and date info
        event_header = ""
        for tag in soup.find_all(["h3", "h4", "h2"]):
            text = tag.get_text(" ", strip=True)
            # Look for patterns like "TTZ TRAIL – Lake – Date" or containing month names
            if "TTZ" in text and any(
                month in text
                for month in [
                    "January",
                    "February",
                    "March",
                    "April",
                    "May",
                    "June",
                    "July",
                    "August",
                    "September",
                    "October",
                    "November",
                    "December",
                    "Jan",
                    "Feb",
                    "Mar",
                    "Apr",
                    "Jun",
                    "Jul",
                    "Aug",
                    "Sep",
                    "Oct",
                    "Nov",
                    "Dec",
                ]
            ):
                event_header = text
                break

        # Also check for published date in WordPress meta
        published_date = ""
        time_tag = soup.find("time", class_="entry-date")
        if time_tag and time_tag.get("datetime"):
            published_date = time_tag.get("datetime")

        metadata = {
            "page_url": url,
            "page_title": title,
            "full_results_header": meta_text,
            "event_header": event_header,
            "published_date": published_date,
        }

        # --- Results table ---
        # Use pandas to pull the first HTML table on the page
        dfs = pd.read_html(resp.content)
        if not dfs:
            logger.warning(f"No tables found on {url}")
            results = []
        else:
            df = dfs[0]
            # standardize column names (strip whitespace)
            df.columns = [c.strip() for c in df.columns]
            results = df.to_dict(orient="records")

        return {"metadata": metadata, "results": results}

    except Exception as e:
        logger.error(f"Failed to parse {url}: {e}")
        return None


def main():
    with requests.Session() as session:
        # 1) build link list from year pages (Tuesday/Wednesday night events)
        year_urls = generate_year_links(MIN_YEAR, MAX_YEAR)
        all_links = get_tournament_links(session, year_urls)

        # 2) Also get TTZ Trail links (team trail events on various lakes)
        trail_links = get_ttz_trail_links(session)
        for link in trail_links:
            if link not in all_links:
                all_links.append(link)
                logger.info(f"  + added TTZ Trail link: {link}")

        # Save updated links
        LINKS_FILE.write_text(json.dumps(all_links, indent=2))
        logger.info(f"Total links after adding TTZ Trail: {len(all_links)}")

        # 3) scrape each tournament and write JSON
        for url in all_links:
            data = get_tournament_results(session, url)
            if not data:
                continue

            # Skip pages without proper results (no PLACE column)
            results = data.get("results", [])
            if results:
                first_row = results[0]
                has_place = any(
                    k.upper() in ["PLACE", "PL", "PL."] for k in first_row.keys()
                )
                if not has_place:
                    logger.info(f"Skipping non-results page: {url}")
                    continue

            # Generate filename: prefer header, fall back to URL slug
            header = data["metadata"].get("full_results_header", "")
            if header:
                safe = re.sub(r"[^\w\-]+", "_", header)
            else:
                # Extract slug from URL
                slug = url.rstrip("/").split("/")[-1]
                safe = re.sub(r"[^\w\-]+", "_", slug)

            if not safe:
                logger.warning(f"Could not generate filename for {url}, skipping")
                continue

            filename = DATA_DIR / f"{safe}.json"
            filename.write_text(json.dumps(data, indent=2))
            logger.info(f"Wrote results to {filename}")


if __name__ == "__main__":
    sys.exit(main())
