"""Multi-source apartment scraper for Chicago 1BR listings."""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

import config


@dataclass
class Listing:
    """Standardized apartment listing."""
    title: str
    price: float
    address: str
    url: str
    source: str
    amenities: list = field(default_factory=list)
    lat: Optional[float] = None
    lon: Optional[float] = None
    description: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Listing":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _get_session() -> requests.Session:
    """Create a session with a random user agent."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(config.USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def _random_delay():
    """Sleep for a random interval to be respectful."""
    time.sleep(random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX))


def _matches_amenities(text: str) -> tuple:
    """Check if text contains required amenity keywords.

    Returns (passes_filter, list_of_matched_amenities).
    """
    text_lower = text.lower()
    matched = []

    for group_name, keywords in config.AMENITY_GROUPS.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append(group_name)
                break

    return len(matched) >= 2, list(set(matched))


def _extract_price(text: str) -> Optional[float]:
    """Extract price from text like '$1,200' or '1200/mo'."""
    match = re.search(r"\$[\d,]+", text)
    if match:
        try:
            price = float(match.group().replace("$", "").replace(",", ""))
            if 300 < price <= config.MAX_PRICE:
                return price
        except ValueError:
            pass
    return None


def scrape_craigslist() -> list:
    """Scrape Craigslist Chicago apartments via HTML search page.

    Parses the static search result list items which contain title, price,
    location, and direct links to individual listings.
    """
    listings = []
    session = _get_session()

    url = (
        "https://chicago.craigslist.org/search/chicago-il/apa"
        "?max_price={}&min_bedrooms=1&max_bedrooms=1".format(config.MAX_PRICE)
    )

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Build a lat/lon lookup from JSON-LD data
        coords_by_name = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld_data = json.loads(script.string)
                if not isinstance(ld_data, dict):
                    continue
                for item in ld_data.get("itemListElement", []):
                    entry = item.get("item", item) if isinstance(item, dict) else {}
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name", "")
                    lat = entry.get("latitude")
                    lon = entry.get("longitude")
                    if name and lat and lon:
                        try:
                            coords_by_name[name.strip().lower()] = (float(lat), float(lon))
                        except (ValueError, TypeError):
                            pass
            except (json.JSONDecodeError, AttributeError):
                continue

        # Parse the HTML result cards — each is an <li> with an <a> containing the link
        results = soup.select("li.cl-static-search-result")
        for result in results:
            try:
                link_el = result.find("a", href=True)
                if not link_el:
                    continue

                listing_url = link_el["href"]
                if not listing_url.startswith("http"):
                    listing_url = "https://chicago.craigslist.org" + listing_url

                title_el = result.select_one("div.title")
                title = title_el.get_text(strip=True) if title_el else link_el.get_text(strip=True)

                price_el = result.select_one("div.price")
                price_text = price_el.get_text(strip=True) if price_el else title
                price = _extract_price(price_text)
                if price is None:
                    continue

                location_el = result.select_one("div.location")
                location = location_el.get_text(strip=True) if location_el else ""
                address = "{}, Chicago, IL".format(location) if location else "Chicago, IL"

                # Look up coordinates from JSON-LD
                lat, lon = coords_by_name.get(title.strip().lower(), (None, None))

                combined = "{} {}".format(title, location)
                passes, matched_amenities = _matches_amenities(combined)

                listings.append(Listing(
                    title=title,
                    price=price,
                    address=address,
                    url=listing_url,
                    source="Craigslist",
                    amenities=matched_amenities,
                    lat=lat,
                    lon=lon,
                ))
            except Exception:
                continue

        _random_delay()
    except Exception as e:
        print("[Craigslist] Error: {}".format(e))

    print("[Craigslist] Found {} listings".format(len(listings)))
    return listings


def scrape_padmapper() -> list:
    """Scrape PadMapper for Chicago 1BR listings via __PRELOADED_STATE__ JSON.

    PadMapper embeds structured listing data in a window.__PRELOADED_STATE__
    variable. Listings are at state.currentSearch.listables.listables.
    """
    listings = []
    session = _get_session()

    url = "https://www.padmapper.com/apartments/chicago-il/1-beds/under-{}".format(
        config.MAX_PRICE
    )

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()

        # Extract __PRELOADED_STATE__ JSON
        match = re.search(
            r"window\.__PRELOADED_STATE__\s*=\s*(\{.+?\})\s*;",
            resp.text,
            re.DOTALL,
        )
        if not match:
            print("[PadMapper] Could not find __PRELOADED_STATE__")
            return listings

        try:
            state = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            print("[PadMapper] JSON parse error: {}".format(e))
            return listings

        # Listings are at: state.currentSearch.listables.listables
        search_data = state.get("currentSearch", {})
        listables_wrapper = search_data.get("listables", {})
        if not isinstance(listables_wrapper, dict):
            print("[PadMapper] Unexpected listables structure")
            return listings

        items = listables_wrapper.get("listables", [])
        if not isinstance(items, list):
            items = []

        for prop in items:
            if not isinstance(prop, dict):
                continue
            try:
                # Price: use min_price for the cheapest option
                price = None
                for pk in ["min_price", "max_price"]:
                    val = prop.get(pk)
                    if val is not None:
                        try:
                            price = float(val)
                            if price <= config.MAX_PRICE:
                                break
                        except (ValueError, TypeError):
                            pass

                if not price or price > config.MAX_PRICE or price < 300:
                    continue

                # Address
                addr_parts = [
                    prop.get("address", ""),
                    prop.get("city", ""),
                    prop.get("state", ""),
                ]
                address = ", ".join(p for p in addr_parts if p)
                if not address:
                    address = "Chicago, IL"

                # Title: prefer building_name, fall back to address
                building_name = prop.get("building_name") or prop.get("agent_name") or ""
                title = building_name if building_name else address

                # Coordinates
                lat = None
                lon = None
                try:
                    lat = float(prop["lat"]) if prop.get("lat") else None
                    lon = float(prop["lng"]) if prop.get("lng") else None
                except (ValueError, TypeError):
                    pass

                # URL — use padmapper_url or url field
                listing_url = prop.get("padmapper_url") or prop.get("url") or ""
                if listing_url and not listing_url.startswith("http"):
                    listing_url = "https://www.padmapper.com" + listing_url

                # Amenities — PadMapper provides amenity_tags and building_amenity_tags
                amenity_tags = prop.get("amenity_tags", []) or []
                building_tags = prop.get("building_amenity_tags", []) or []
                all_tags = amenity_tags + building_tags
                tags_text = " ".join(str(t) for t in all_tags)

                desc = prop.get("short_description") or ""
                combined = "{} {} {} {}".format(title, desc, address, tags_text)
                passes, matched_amenities = _matches_amenities(combined)

                listings.append(Listing(
                    title=title,
                    price=price,
                    address=address,
                    url=listing_url,
                    source="PadMapper",
                    amenities=matched_amenities,
                    lat=lat,
                    lon=lon,
                    description=tags_text[:500],
                ))
            except Exception:
                continue

        _random_delay()
    except Exception as e:
        print("[PadMapper] Error: {}".format(e))

    print("[PadMapper] Found {} listings".format(len(listings)))
    return listings


def scrape_zillow_api() -> list:
    """Fetch listings from Zillow via RapidAPI (requires RAPIDAPI_KEY)."""
    if not config.RAPIDAPI_KEY:
        print("[Zillow API] Skipped - no RAPIDAPI_KEY set")
        return []

    listings = []
    url = "https://zillow-com1.p.rapidapi.com/propertyExtendedSearch"
    params = {
        "location": "{}, {}".format(config.SEARCH_CITY, config.SEARCH_STATE),
        "home_type": "Apartments",
        "rentMinPrice": "0",
        "rentMaxPrice": str(config.MAX_PRICE),
        "bedsMin": "1",
        "bedsMax": "1",
        "status_type": "ForRent",
    }
    headers = {
        "X-RapidAPI-Key": config.RAPIDAPI_KEY,
        "X-RapidAPI-Host": "zillow-com1.p.rapidapi.com",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        props = data.get("props", [])
        for prop in props[:50]:
            try:
                price = prop.get("price")
                if not price or price > config.MAX_PRICE:
                    continue

                address = prop.get("address", "")
                desc = prop.get("description", "")
                combined = "{} {}".format(address, desc)
                passes, matched_amenities = _matches_amenities(combined)

                listings.append(Listing(
                    title=prop.get("addressStreet", address),
                    price=float(price),
                    address=address,
                    url="https://www.zillow.com{}".format(prop.get("detailUrl", "")),
                    source="Zillow",
                    amenities=matched_amenities,
                    lat=prop.get("latitude"),
                    lon=prop.get("longitude"),
                    description=desc[:500],
                ))
            except Exception:
                continue

    except Exception as e:
        print("[Zillow API] Error: {}".format(e))

    print("[Zillow API] Found {} listings".format(len(listings)))
    return listings


def scrape_all() -> list:
    """Run all scrapers and return combined deduplicated listings."""
    all_listings = []

    scrapers = [
        scrape_craigslist,
        scrape_padmapper,
        scrape_zillow_api,
    ]

    for scraper_fn in scrapers:
        try:
            results = scraper_fn()
            all_listings.extend(results)
        except Exception as e:
            print("[{}] Failed: {}".format(scraper_fn.__name__, e))

    # Deduplicate by (title, price) tuple
    seen = set()
    unique = []
    for listing in all_listings:
        key = (listing.title.lower().strip(), listing.price)
        if key not in seen:
            seen.add(key)
            unique.append(listing)

    print("\n[Total] {} unique listings from {} raw results".format(
        len(unique), len(all_listings)
    ))
    return unique


def save_listings(listings: list, path: str = config.LISTINGS_FILE):
    """Save listings to JSON file."""
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {
        "last_updated": datetime.now().isoformat(),
        "count": len(listings),
        "listings": [l.to_dict() for l in listings],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print("Saved {} listings to {}".format(len(listings), path))


def load_listings(path: str = config.LISTINGS_FILE) -> list:
    """Load listings from JSON file."""
    try:
        with open(path) as f:
            data = json.load(f)
        return [Listing.from_dict(d) for d in data.get("listings", [])]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


if __name__ == "__main__":
    print("Starting apartment scrape...")
    listings = scrape_all()
    if listings:
        save_listings(listings)
    else:
        print("No listings found. Sites may be blocking or selectors may need updating.")
