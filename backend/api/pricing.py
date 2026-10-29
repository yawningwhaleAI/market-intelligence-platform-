"""Transparent, conservative scan estimates based on the supplied actor tests."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_ORDER = ("blinkit", "zepto", "instamart", "amazon", "flipkart")
LOCAL_PLATFORMS = frozenset(("blinkit", "zepto", "instamart"))
ESTIMATE_BUFFER = 1.5


def load_config(name: str) -> dict[str, Any]:
    path = BACKEND_ROOT / "config" / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _actor_rate(actor: dict[str, Any]) -> float:
    for key, value in actor.get("eval", {}).items():
        match = re.fullmatch(r"cost_usd_per_(\d+)", key)
        if match and int(match.group(1)) > 0:
            return max(0.0, float(value) / int(match.group(1)))
    return 0.0


def _item_limit(template: dict[str, Any], requested: int) -> int:
    limits = [
        int(template[key])
        for key in ("maxResults", "maxItemsPerQuery", "maxResultsPerQuery", "maxProducts")
        if isinstance(template.get(key), (int, float)) and template[key] > 0
    ]
    return min([requested, *limits]) if limits else requested


def estimate_scan(
    platforms: list[str],
    queries: list[str],
    locations: list[dict[str, Any]],
    max_items_per_query: int,
    spend_cap_usd: float,
) -> dict[str, Any]:
    """Estimate a run without claiming location-level coverage for national actors."""
    if not platforms or len(set(platforms)) != len(platforms):
        raise ValueError("Choose one or more unique platforms.")
    if any(platform not in PLATFORM_ORDER for platform in platforms):
        raise ValueError("One or more platforms are not supported.")
    if not queries or len(queries) > 10:
        raise ValueError("Choose between 1 and 10 search phrases.")
    if not 1 <= max_items_per_query <= 100:
        raise ValueError("Results per phrase must be between 1 and 100.")
    if not 0 < spend_cap_usd <= 100:
        raise ValueError("Budget must be greater than $0 and at most $100.")
    if any(platform in LOCAL_PLATFORMS for platform in platforms) and not locations:
        raise ValueError("Add at least one city locality for quick-commerce scans.")

    actors = load_config("actors.yaml").get("platforms", {})
    configured_cap = float(
        os.environ.get("SCOUTWISE_DEFAULT_RUN_CAP_USD")
        or load_config("actors.yaml").get("guardrails", {}).get("spend_cap_usd", 5.0)
    )
    cap = min(float(spend_cap_usd), configured_cap)
    rows: list[dict[str, Any]] = []
    estimated_total = 0.0
    buffered_total = 0.0

    for platform in PLATFORM_ORDER:
        if platform not in platforms:
            continue
        actor = actors[platform]
        request_limit = _item_limit(actor.get("input_template", {}), max_items_per_query)
        local = platform in LOCAL_PLATFORMS
        location_count = len(locations) if local else 1
        estimated_results = request_limit * len(queries) * location_count
        rate = _actor_rate(actor)
        estimated = rate * estimated_results
        buffered = estimated * ESTIMATE_BUFFER
        estimated_total += estimated
        buffered_total += buffered
        rows.append({
            "platform": platform,
            "actor_id": actor["chosen_actor"],
            "scope": "city/locality" if local else "national",
            "queries": len(queries),
            "locations": location_count,
            "max_items_per_query": request_limit,
            "estimated_results": estimated_results,
            "observed_usd_per_result": round(rate, 6),
            "estimated_cost_usd": round(estimated, 4),
            "buffered_estimate_usd": round(buffered, 4),
        })

    return {
        "estimated_cost_usd": round(estimated_total, 4),
        "buffered_estimate_usd": round(buffered_total, 4),
        "spend_cap_usd": round(cap, 4),
        "within_cap": buffered_total <= cap,
        "buffer_factor": ESTIMATE_BUFFER,
        "cost_basis": "Observed actor costs from the supplied pilot; actual charges can vary.",
        "coverage_note": "Amazon and Flipkart scans use national scope. Quick-commerce localities are actor inputs, not verified serviceability or dark-store-density data.",
        "platforms": rows,
    }
