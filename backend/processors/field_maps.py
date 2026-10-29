"""Map each chosen actor's raw item fields -> our raw_observations columns.

One mapping per platform (the Step 1 winning actor). Only fields the actor
actually returns are mapped; anything absent stays None (never fabricated).
`build_input` fills a platform's actors.yaml input_template with the queries
and one resolved locality.
"""
from __future__ import annotations

from typing import Any

# platform -> {raw_observations_column: actor_field_name}
FIELD_MAPS: dict[str, dict[str, str]] = {
    "blinkit": {
        "product_name_raw": "title", "brand_raw": "brand",
        "pack_size_raw": "packSize", "mrp_raw": "mrp", "price_raw": "price",
        "rating_raw": "rating", "review_count_raw": "ratingCount",
        "stock_status_raw": "inStock", "search_rank": "position",
        "query": "searchQuery", "url": "productUrl", "image_url": "imageUrl",
    },
    "zepto": {
        "product_name_raw": "name", "brand_raw": "brand",
        "pack_size_raw": "packSize", "mrp_raw": "mrp", "price_raw": "sellingPrice",
        "rating_raw": "rating", "review_count_raw": "ratingCount",
        "stock_status_raw": "inStock", "store_id": "storeId",
        "query": "sourceQuery", "url": "productUrl",
    },
    "instamart": {
        "product_name_raw": "name", "brand_raw": "brand",
        "pack_size_raw": "quantity", "mrp_raw": "mrp", "price_raw": "price",
        "rating_raw": "rating", "review_count_raw": "ratingCount",
        "stock_status_raw": "inStock", "is_sponsored": "isAd",
        "query": "sourceQuery", "url": "productUrl", "image_url": "imageUrl",
    },
    "amazon": {
        "product_name_raw": "title", "brand_raw": "brand",
        "mrp_raw": "listPrice", "price_raw": "price",
        "rating_raw": "rating", "review_count_raw": "reviewCount",
        "badge_raw": "badge", "search_rank": "position", "is_sponsored": "isSponsored",
        "query": "query", "url": "url", "image_url": "image",
    },
    "flipkart": {
        "product_name_raw": "title", "pack_size_raw": "subtitle",
        "mrp_raw": "mrp", "price_raw": "currentPrice",
        "rating_raw": "rating", "review_count_raw": "reviewCount",
        "stock_status_raw": "inStock", "query": "searchInput", "url": "url", "image_url": "imageUrl",
    },
}


# Some actors cap how many queries one run accepts.
MAX_QUERIES_PER_RUN: dict[str, int] = {"blinkit": 5}

# Instamart (solidcode) only accepts city from a fixed enum; the locality goes
# in `area`. Map our locations.yaml city names onto the actor's allowed values.
INSTAMART_CITY_ENUM = {
    "new delhi": "Delhi", "delhi": "Delhi", "gurugram": "Gurgaon",
    "gurgaon": "Gurgaon", "noida": "Noida", "greater noida": "Noida",
    "mumbai": "Mumbai", "bengaluru": "Bangalore", "bangalore": "Bangalore",
    "hyderabad": "Hyderabad", "chennai": "Chennai", "pune": "Pune",
    "kolkata": "Kolkata", "ahmedabad": "Ahmedabad",
}


def map_item(platform: str, item: dict) -> dict[str, Any]:
    """Return raw_observations column values for one actor item."""
    fm = FIELD_MAPS[platform]
    out: dict[str, Any] = {col: item.get(field) for col, field in fm.items()}
    # normalise booleans to 0/1 where present
    for b in ("stock_status_raw", "is_sponsored"):
        if isinstance(out.get(b), bool):
            out[b] = 1 if out[b] else 0
    return out


def build_input(platform: str, template: dict, queries: list[str], loc: dict) -> dict:
    """Fill an actors.yaml input_template with queries + one resolved locality.

    `loc` is a locality dict from locations.yaml (name, city, area, lat, lng).
    """
    inp = dict(template)
    if platform == "blinkit":
        inp["searchQueries"] = queries
        inp["locationName"] = f"{loc['name']}, {loc.get('city','')}".strip(", ")
        inp["latitude"] = loc.get("lat")
        inp["longitude"] = loc.get("lng")
    elif platform == "zepto":
        inp["locations"] = [f"{loc['name']}, {loc.get('city','')}".strip(", ")]
        inp["searchQueries"] = queries
    elif platform == "instamart":
        inp["searchQueries"] = queries
        city_raw = (loc.get("city") or "").strip().lower()
        if city_raw not in INSTAMART_CITY_ENUM:
            raise ValueError(f"Instamart does not have a configured city mapping for {loc.get('city') or 'this locality'}.")
        inp["city"] = INSTAMART_CITY_ENUM[city_raw]
        inp["area"] = loc.get("area", loc["name"])
    elif platform == "amazon":
        inp["queries"] = queries
    elif platform == "flipkart":
        inp["searchQueries"] = queries
    return inp

