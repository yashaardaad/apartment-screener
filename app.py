"""Streamlit dashboard for the apartment screener."""

import json
import os
from datetime import datetime

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import config
from scraper import Listing, load_listings, save_listings, scrape_all
from scoring import score_and_rank

st.set_page_config(
    page_title="Chicago Apartment Screener",
    page_icon="🏠",
    layout="wide",
)

st.title("Chicago Apartment Screener")
st.caption("1BR apartments under $1,500/mo near 22 W Washington St")


def get_last_updated() -> str:
    """Get timestamp of last data update."""
    try:
        with open(config.LISTINGS_FILE) as f:
            data = json.load(f)
        return data.get("last_updated", "Never")
    except (FileNotFoundError, json.JSONDecodeError):
        return "Never"


def load_and_score() -> list[dict]:
    """Load listings from disk and score them."""
    listings = load_listings()
    if not listings:
        return []
    return score_and_rank(listings)


# --- Sidebar ---
st.sidebar.header("Filters")

price_range = st.sidebar.slider(
    "Max Price ($/mo)",
    min_value=500,
    max_value=1500,
    value=1500,
    step=50,
)

max_distance = st.sidebar.slider(
    "Max Distance (miles)",
    min_value=1.0,
    max_value=15.0,
    value=15.0,
    step=0.5,
)

amenity_filters = {}
st.sidebar.subheader("Required Amenities")
for group_name in config.AMENITY_GROUPS:
    amenity_filters[group_name] = st.sidebar.checkbox(
        group_name.capitalize(),
        value=False,
    )

# --- Run Now ---
st.sidebar.divider()
if st.sidebar.button("Run Scraper Now", type="primary"):
    with st.spinner("Scraping listings... this may take a minute."):
        listings = scrape_all()
        if listings:
            save_listings(listings)
            st.sidebar.success(f"Found {len(listings)} listings!")
            st.rerun()
        else:
            st.sidebar.warning("No listings found. Try again later.")

# --- Main Content ---
last_updated = get_last_updated()
st.markdown(f"**Last updated:** {last_updated}")

ranked = load_and_score()

if not ranked:
    st.info(
        "No listings data found. Click **Run Scraper Now** in the sidebar to fetch listings, "
        "or run `python scraper.py` from the terminal."
    )
    st.stop()

# Apply filters
filtered = ranked.copy()
filtered = [r for r in filtered if r["price"] <= price_range]

if max_distance < 15.0:
    filtered = [
        r for r in filtered
        if r.get("distance_miles") is not None and r["distance_miles"] <= max_distance
    ]

active_amenity_filters = [name for name, checked in amenity_filters.items() if checked]
if active_amenity_filters:
    filtered = [
        r for r in filtered
        if all(af in r.get("amenities", []) for af in active_amenity_filters)
    ]

st.markdown(f"**Showing {len(filtered)} of {len(ranked)} listings**")

# --- Results Table ---
if filtered:
    df = pd.DataFrame(filtered)
    display_cols = ["rank", "title", "price", "distance_miles", "score", "amenities", "source", "url"]
    available_cols = [c for c in display_cols if c in df.columns]
    display_df = df[available_cols].copy()

    display_df.columns = [
        col.replace("_", " ").title() for col in display_df.columns
    ]

    st.dataframe(
        display_df,
        column_config={
            "Url": st.column_config.LinkColumn("Link", display_text="View"),
            "Price": st.column_config.NumberColumn("Price", format="$%.0f"),
            "Distance Miles": st.column_config.NumberColumn("Distance (mi)", format="%.1f"),
            "Score": st.column_config.NumberColumn("Score", format="%.3f"),
        },
        hide_index=True,
        use_container_width=True,
    )

    # --- Map View ---
    st.subheader("Map View")

    map_data = [r for r in filtered if r.get("lat") and r.get("lon")]

    m = folium.Map(
        location=[config.OFFICE_LAT, config.OFFICE_LON],
        zoom_start=11,
    )

    # Office marker
    folium.Marker(
        [config.OFFICE_LAT, config.OFFICE_LON],
        popup="Office: 22 W Washington St",
        icon=folium.Icon(color="red", icon="briefcase", prefix="fa"),
        tooltip="Office",
    ).add_to(m)

    # Listing markers
    for item in map_data:
        popup_html = (
            f"<b>{item['title'][:40]}</b><br>"
            f"${item['price']:.0f}/mo<br>"
            f"Score: {item['score']:.3f}<br>"
            f"<a href='{item['url']}' target='_blank'>View Listing</a>"
        )
        folium.Marker(
            [item["lat"], item["lon"]],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color="blue", icon="home", prefix="fa"),
            tooltip=f"${item['price']:.0f} - {item['title'][:25]}",
        ).add_to(m)

    st_folium(m, width=None, height=500, use_container_width=True)

    if not map_data:
        st.caption("No geocoded listings to show on map. Addresses will be geocoded during scoring.")
else:
    st.warning("No listings match your filters. Try adjusting the filters in the sidebar.")
