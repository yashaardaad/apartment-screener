"""Central configuration for the apartment screener."""

import os

# Office location: 22 W Washington St, Chicago, IL
OFFICE_LAT = 41.8827
OFFICE_LON = -87.6300

# Search criteria
MAX_PRICE = 1500
BEDROOMS = 1
BATHROOMS = 1
SEARCH_CITY = "Chicago"
SEARCH_STATE = "IL"
SEARCH_RADIUS_MILES = 15

# Required amenities (keywords to match in listing descriptions)
REQUIRED_AMENITIES = [
    "in-unit laundry",
    "washer",  # alternate keyword for laundry
    "internet",
    "parking",
    "ac",
    "air conditioning",
    "central air",
]

# Amenity groups — a listing must match at least one keyword per group
AMENITY_GROUPS = {
    "laundry": ["in-unit laundry", "washer", "dryer", "w/d in unit", "in unit laundry"],
    "internet": ["internet", "wi-fi", "wifi", "high-speed", "fiber"],
    "parking": ["parking", "garage", "carport"],
    "ac": ["ac", "a/c", "air conditioning", "central air", "hvac"],
}

# Scoring weights
PRICE_WEIGHT = 0.5
DISTANCE_WEIGHT = 0.5
MAX_DISTANCE_MILES = SEARCH_RADIUS_MILES

# SMS notifications (Textbelt free tier: 1 text/day)
TEXTBELT_URL = "https://textbelt.com/text"
TEXTBELT_KEY = "textbelt"  # free key
SMS_RECIPIENT = os.environ.get("SMS_RECIPIENT", "")

# Optional RapidAPI key for Zillow
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

# Data persistence
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LISTINGS_FILE = os.path.join(DATA_DIR, "listings.json")

# Scraping settings
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]
REQUEST_DELAY_MIN = 2
REQUEST_DELAY_MAX = 5
