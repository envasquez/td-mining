import json
import logging
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


MIN_YEAR = 2006
MAX_YEAR = 2026
LINKS_FILE = Path(__file__).resolve().parent.parent / "links" / "basschamps_links.json"

TOURNAMENT_TYPE = "type=team"
ALL_LINKS = []
if os.path.exists(LINKS_FILE) and os.path.getsize(LINKS_FILE) > 0:
    with open(LINKS_FILE, mode="r", encoding="utf-8") as f:
        logger.info(f"Loading links from {LINKS_FILE}")
        ALL_LINKS = json.load(f)


def generate_annual_links(min_year, max_year):
    # Example annual link:
    # https://basschamps.com/resultsIntro.cfm?type=team&yearSelected=2006
    base_url = "https://basschamps.com/resultsIntro.cfm?"
    return [
        f"{base_url}{TOURNAMENT_TYPE}&yearSelected={y}"
        for y in range(min_year, max_year)
    ]


def get_tournament_links(s, urls):
    global ALL_LINKS

    base_url = "https://basschamps.com"
    for url in urls:
        response = s.get(url, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        logger.debug(f"\n\nGetting tournaments for: {url}")
        pattern = re.compile(
            r"^results\.cfm\?tournament_id=\d+&type=team&yearSelected=\d+$"
        )
        for link in soup.find_all("a", href=pattern):
            href = link["href"].replace("&amp;", "&")
            full_url = f"{base_url}/{href}&action=displayThisMany&page=recalculate&sortField=place&junior=no"
            if full_url not in ALL_LINKS:
                ALL_LINKS.append(full_url)
            else:
                logger.info(f"Link exists, skipping ... {full_url}")
    with open(LINKS_FILE, mode="w", encoding="utf-8") as f:
        json.dump(ALL_LINKS, f, indent=4)


def get_tournament_results(s, url):
    def _get_text_clean(c):
        return c.get_text(strip=True).replace("\xa0", "")

    def _parse_angler_cell(c):
        bs = BeautifulSoup(str(c), "html.parser")
        full_text = bs.get_text(separator="\n").strip()
        lines = [line.strip() for line in full_text.split("\n") if line.strip()]
        name = lines[0] if lines else ""
        strong_tags = bs.find_all("strong")
        if len(strong_tags) >= 2:
            city = strong_tags[0].get_text(strip=True)
            state = strong_tags[1].get_text(strip=True)
            hometown = f"{city}, {state}"
        else:
            hometown = ""
        return name.title(), hometown.title()

    def _parse_results_table():
        results = []
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if not cells or len(cells) < 9:
                continue  # skip malformed or irrelevant rows
            try:
                place = int(_get_text_clean(cells[0]))
            except ValueError:
                continue  # skip header rows or non-numeric places
            boat_cell = cells[1]
            img_tag = boat_cell.find("img")
            angler1, hometown1 = _parse_angler_cell(cells[3])
            angler2, hometown2 = _parse_angler_cell(cells[4])
            results.append(
                {
                    "place": place,
                    "skeeter_boat": True
                    if img_tag and "skeeter" in img_tag.get("src", "").lower()
                    else False,
                    "angler1": angler1,
                    "angler1_hometown": hometown1,
                    "angler2": angler2,
                    "angler2_hometown": hometown2,
                    "fish": int(_get_text_clean(cells[5])),
                    "big bass": float(_get_text_clean(cells[6])),
                    "Wt.": float(_get_text_clean(cells[7])),
                    "prize": _get_text_clean(cells[8]) if cells[8] else None,
                }
            )
        return results

    #
    # Get Tournament Results
    #
    try:
        response = s.get(url, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")

        metadata = {
            "Date": None,
            "Region": None,
            "Tournament": None,
            "Tournament Trail": None,
        }
        for row in soup.find_all("tr"):
            label_cell = row.find("td", class_="white", align="right")
            if label_cell and label_cell.text.strip().endswith(":"):
                label = label_cell.text.strip().replace(":", "")
                value_cell = row.find("td", class_="babyBlue")
                if value_cell and label in metadata:
                    metadata[label] = value_cell.get_text(strip=True)
        return {"metadata": metadata, "results": _parse_results_table()}
    except requests.RequestException as e:
        logger.error(f"Error parsing {url}: {e}")
        return None


def main():
    with requests.Session() as session:
        get_tournament_links(
            s=session, urls=generate_annual_links(min_year=MIN_YEAR, max_year=MAX_YEAR)
        )
        for url in ALL_LINKS:
            result = get_tournament_results(s=session, url=url)
            t_name = result["metadata"]["Tournament"].replace(" ", "_")
            t_date = result["metadata"]["Date"].replace(" ", "_").replace(",", "")
            filename = f"data/{t_name}_{t_date}.json"
            with open(filename, mode="w", encoding="utf-8") as f:
                json.dump(result, f, indent=4)
                logger.debug(f"Wrote {t_name} {t_date} results to: {filename}")


if __name__ == "__main__":
    sys.exit(main())
