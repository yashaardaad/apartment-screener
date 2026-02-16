"""Multi-source apartment scraper for Chicago 1BR listings."""

from __future__ import annotations

import json
import random
import re
import time
import xml.etree.ElementTree as ET
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
    amenities: list[str] = field(default_factory=list)
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


def _matches_amenities(text: str) -> tuple[bool, list[str]]:
    """Check if text contains required amenity keywords.

    Returns (passes_filter, list_of_matched_amenities).
    A listing passes if it matches at least one keyword from each amenity group.
    """
    text_lower = text.lower()
    matched = []
    groups_matched = 0

    for group_name, keywords in config.AMENITY_GROUPS.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append(group_name)
                groups_matched += 1
                break

    # Require at least 2 out of 4 amenity groups to keep results useful
    return groups_matched >= 2, list(set(matched))


def _extract_price(text: str) -> Optional[float]:
    """Extract price from text like '$1,200' or '1200/mo'."""
    match = re.search(r"\$?([\d,]+)", text.replace(",", ""))
    if match:
        try:
            price = float(match.group(1).replace(",", ""))
            if 300 < price <= config.MAX_PRICE:
                return price
        except ValueError:
            pass
    return None


def scrape_apartments_com() -> list[Listing]:
    """Scrape Apartments.com for Chicago 1BR listings."""
    listings = []
    session = _get_session()
    url = (
        f"https://www.apartments.com/1-bedrooms-under-{config.MAX_PRICE}/"
        f"{config.SEARCH_CITY.lower()}-{config.SEARCH_STATE.lower()}/"
    )

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Apartments.com uses placard-content for listing cards
        cards = soup.select("li.mortar-wrapper article.placard")
        if not cards:
            cards = soup.select("div.placard-content")

        for card in cards[:50]:  # limit to avoid overloading
            try:
                title_el = card.select_one("span.js-placardTitle, .property-title")
                price_el = card.select_one("p.property-pricing, span.property-rents")
                address_el = card.select_one("div.property-address, p.property-address")
                link_el = card.select_one("a.property-link") or card.find("a", href=True)

                if not (title_el and price_el):
                    continue

                title = title_el.get_text(strip=True)
                price = _extract_price(price_el.get_text(strip=True))
                if price is None:
                    continue

                address = address_el.get_text(strip=True) if address_el else ""
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.apartments.com" + link

                # Collect all text for amenity matching
                card_text = card.get_text(" ", strip=True)
                passes, matched_amenities = _matches_amenities(card_text)

                listings.append(Listing(
                    title=title,
                    price=price,
                    address=address,
                    url=link,
                    source="Apartments.com",
                    amenities=matched_amenities,
                    description=card_text[:500],
                ))
            except Exception:
                continue

        _random_delay()
    except Exception as e:
        print(f"[Apartments.com] Error: {e}")

    print(f"[Apartments.com] Found {len(listings)} listings")
    return listings


def scrape_craigslist() -> list[Listing]:
    """Scrape Craigslist Chicago apartments via RSS feed."""
    listings = []
    session = _get_session()

    # Craigslist RSS feed for apartments in Chicago
    url = (
        "https://chicago.craigslist.org/search/apa"
        f"?max_price={config.MAX_PRICE}&min_bedrooms=1&max_bedrooms=1"
        "&format=rss"
    )

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        ns = {"rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"}

        items = root.findall(".//item")
        for item in items[:50]:
            try:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")

                if title_el is None or link_el is None:
                    continue

                title_text = title_el.text or ""
                price = _extract_price(title_text)
                if price is None:
                    continue

                desc_text = desc_el.text if desc_el is not None else ""
                combined_text = f"{title_text} {desc_text}"
                passes, matched_amenities = _matches_amenities(combined_text)

                listings.append(Listing(
                    title=title_text,
                    price=price,
                    address="Chicago, IL",  # CL doesn't always include address
                    url=link_el.text or "",
                    source="Craigslist",
                    amenities=matched_amenities,
                    description=desc_text[:500] if desc_text else "",
                ))
            except Exception:
                continue

        _random_delay()
    except Exception as e:
        print(f"[Craigslist] Error: {e}")

    print(f"[Craigslist] Found {len(listings)} listings")
    return listings


def scrape_zillow_api() -> list[Listing]:
    """Fetch listings from Zillow via RapidAPI (requires RAPIDAPI_KEY)."""
    if not config.RAPIDAPI_KEY:
        print("[Zillow API] Skipped - no RAPIDAPI_KEY set")
        return []

    listings = []
    url = "https://zillow-com1.p.rapidapi.com/propertyExtendedSearch"
    params = {
        "location": f"{config.SEARCH_CITY}, {config.SEARCH_STATE}",
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
                combined = f"{address} {desc}"
                passes, matched_amenities = _matches_amenities(combined)

                listings.append(Listing(
                    title=prop.get("addressStreet", address),
                    price=float(price),
                    address=address,
                    url=f"https://www.zillow.com{prop.get('detailUrl', '')}",
                    source="Zillow",
                    amenities=matched_amenities,
                    lat=prop.get("latitude"),
                    lon=prop.get("longitude"),
                    description=desc[:500],
                ))
            except Exception:
                continue

    except Exception as e:
        print(f"[Zillow API] Error: {e}")

    print(f"[Zillow API] Found {len(listings)} listings")
    return listings


def scrape_rentcom() -> list[Listing]:
    """Scrape Rent.com for Chicago 1BR listings."""
    listings = []
    session = _get_session()
    url = (
        f"https://www.rent.com/illinois/{config.SEARCH_CITY.lower()}-apartments"
        f"/bedrooms-1/price-to-{config.MAX_PRICE}"
    )

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select("div[data-tid='property-card'], div.listing-card")
        for card in cards[:50]:
            try:
                title_el = card.select_one("[data-tid='property-title'], .property-name")
                price_el = card.select_one("[data-tid='price'], .price-range")
                address_el = card.select_one("[data-tid='property-address'], .property-address")
                link_el = card.find("a", href=True)

                if not (title_el and price_el):
                    continue

                title = title_el.get_text(strip=True)
                price = _extract_price(price_el.get_text(strip=True))
                if price is None:
                    continue

                address = address_el.get_text(strip=True) if address_el else ""
                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.rent.com" + link

                card_text = card.get_text(" ", strip=True)
                passes, matched_amenities = _matches_amenities(card_text)

                listings.append(Listing(
                    title=title,
                    price=price,
                    address=address,
                    url=link,
                    source="Rent.com",
                    amenities=matched_amenities,
                    description=card_text[:500],
                ))
            except Exception:
                continue

        _random_delay()
    except Exception as e:
        print(f"[Rent.com] Error: {e}")

    print(f"[Rent.com] Found {len(listings)} listings")
    return listings


def scrape_all() -> list[Listing]:
    """Run all scrapers and return combined deduplicated listings."""
    all_listings = []

    scrapers = [
        scrape_apartments_com,
        scrape_craigslist,
        scrape_zillow_api,
        scrape_rentcom,
    ]

    for scraper_fn in scrapers:
        try:
            results = scraper_fn()
            all_listings.extend(results)
        except Exception as e:
            print(f"[{scraper_fn.__name__}] Failed: {e}")

    # Deduplicate by (title, price) tuple
    seen = set()
    unique = []
    for listing in all_listings:
        key = (listing.title.lower().strip(), listing.price)
        if key not in seen:
            seen.add(key)
            unique.append(listing)

    print(f"\n[Total] {len(unique)} unique listings from {len(all_listings)} raw results")
    return unique


def save_listings(listings: list[Listing], path: str = config.LISTINGS_FILE):
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
    print(f"Saved {len(listings)} listings to {path}")


def load_listings(path: str = config.LISTINGS_FILE) -> list[Listing]:
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
