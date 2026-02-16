"""Quality scoring for apartment listings based on price and distance to office."""

from __future__ import annotations

from typing import Optional, Tuple, List, Dict

from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

import config
from scraper import Listing


_geocoder = Nominatim(user_agent="apartment-screener")


def geocode_address(address: str) -> tuple[float | None, float | None]:
    """Geocode an address to (lat, lon). Returns (None, None) on failure."""
    if not address or address.strip() == "":
        return None, None

    # Ensure Chicago, IL is in the address for better results
    if "chicago" not in address.lower():
        address = f"{address}, Chicago, IL"

    try:
        location = _geocoder.geocode(address, timeout=10)
        if location:
            return location.latitude, location.longitude
    except (GeocoderTimedOut, GeocoderUnavailable, Exception) as e:
        print(f"[Geocode] Failed for '{address}': {e}")

    return None, None


def calculate_distance(lat: float, lon: float) -> float:
    """Calculate distance in miles from a point to the office."""
    office = (config.OFFICE_LAT, config.OFFICE_LON)
    point = (lat, lon)
    return geodesic(office, point).miles


def score_listing(listing: Listing) -> float:
    """Calculate quality score for a listing (0-1, higher is better).

    Score = price_score * PRICE_WEIGHT + distance_score * DISTANCE_WEIGHT
    """
    # Price score: lower price = higher score
    price_score = 1 - (listing.price / config.MAX_PRICE)
    price_score = max(0, min(1, price_score))

    # Distance score: need lat/lon
    if listing.lat is not None and listing.lon is not None:
        distance = calculate_distance(listing.lat, listing.lon)
        distance_score = 1 - min(distance / config.MAX_DISTANCE_MILES, 1)
    else:
        distance_score = 0.5  # neutral score if we can't geocode

    score = price_score * config.PRICE_WEIGHT + distance_score * config.DISTANCE_WEIGHT
    return round(score, 4)


def get_distance(listing: Listing) -> float | None:
    """Get distance in miles from listing to office."""
    if listing.lat is not None and listing.lon is not None:
        return round(calculate_distance(listing.lat, listing.lon), 2)
    return None


def score_and_rank(listings: list[Listing]) -> list[dict]:
    """Score all listings, geocode if needed, and return ranked results.

    Returns list of dicts with listing data + score + distance.
    """
    scored = []

    for listing in listings:
        # Geocode if we don't have coordinates
        if listing.lat is None or listing.lon is None:
            listing.lat, listing.lon = geocode_address(listing.address)

        distance = get_distance(listing)
        score = score_listing(listing)

        result = listing.to_dict()
        result["score"] = score
        result["distance_miles"] = distance
        scored.append(result)

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Add rank
    for i, item in enumerate(scored, 1):
        item["rank"] = i

    return scored


if __name__ == "__main__":
    from scraper import load_listings

    listings = load_listings()
    if not listings:
        print("No listings found. Run scraper.py first.")
    else:
        ranked = score_and_rank(listings)
        print(f"\nTop 10 listings by quality score:")
        print("-" * 80)
        for item in ranked[:10]:
            dist = f"{item['distance_miles']:.1f} mi" if item["distance_miles"] else "N/A"
            print(f"#{item['rank']} | ${item['price']:.0f}/mo | {dist} | "
                  f"Score: {item['score']:.3f} | {item['title'][:40]}")
