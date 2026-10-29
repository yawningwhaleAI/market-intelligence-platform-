"""Build saved research scans into bounded Apify actor jobs and result rows."""
from __future__ import annotations

from typing import Any

from ..processors.field_maps import MAX_QUERIES_PER_RUN, build_input, map_item

LOCAL_PLATFORMS = {"blinkit", "zepto", "instamart"}
SUPPORTED_PLATFORMS = {"blinkit", "zepto", "instamart", "amazon", "flipkart"}


def build_actor_jobs(
    platforms: list[str],
    queries: list[str],
    locations: list[dict[str, Any]],
    depth: int,
    actor_configs: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build one job per local service area and grouped query set, or per ecommerce platform."""
    if not platforms or any(item not in SUPPORTED_PLATFORMS for item in platforms):
        raise ValueError("Choose one or more supported marketplaces.")
    if not queries or not 1 <= len(queries) <= 10:
        raise ValueError("Choose between 1 and 10 search phrases.")
    if not 1 <= depth <= 100:
        raise ValueError("Results per phrase must be between 1 and 100.")
    if any(item in LOCAL_PLATFORMS for item in platforms) and not locations:
        raise ValueError("Add at least one locality for quick-commerce scans.")
    platform_configs = actor_configs.get("platforms", {})
    jobs: list[dict[str, Any]] = []

    for platform in platforms:
        cfg = platform_configs.get(platform)
        if not cfg or not cfg.get("chosen_actor"):
            raise ValueError(f"The {platform} actor is not configured.")
        template = cfg.get("input_template", {})
        query_chunk_size = MAX_QUERIES_PER_RUN.get(platform, len(queries))
        query_groups = [queries[i:i + query_chunk_size] for i in range(0, len(queries), query_chunk_size)]
        # Zepto accepts multiple service areas in a single actor input.
        platform_locations = ([locations] if platform == "zepto" else locations) if platform in LOCAL_PLATFORMS else [{}]
        for location in platform_locations:
            resolved_locations = location if platform == "zepto" else [location]
            for resolved in resolved_locations:
                if platform in LOCAL_PLATFORMS and (not resolved.get("name") or not resolved.get("city")):
                    raise ValueError("Each selected locality must include its locality and city.")
                if platform == "blinkit" and (resolved.get("lat") is None or resolved.get("lng") is None):
                    raise ValueError(f"{resolved.get('name')}, {resolved.get('city')} is missing verified coordinates required by this Blinkit actor. Choose another locality or remove Blinkit.")
            for group in query_groups:
                actor_input = build_input(platform, template, group, resolved_locations[0] if platform == "zepto" else location)
                if platform == "zepto":
                    actor_input["locations"] = [f"{item['name']}, {item.get('city', '')}".strip(", ") for item in resolved_locations]
                _apply_depth(platform, actor_input, template, depth, len(group))
                jobs.append({
                    "platform": platform,
                    "actor_id": cfg["chosen_actor"],
                    "actor_input": actor_input,
                    "queries": group,
                    "location": resolved_locations if platform == "zepto" else (location if platform in LOCAL_PLATFORMS else None),
                })
    return jobs


def _apply_depth(platform: str, actor_input: dict[str, Any], template: dict[str, Any], depth: int, query_count: int) -> None:
    if platform == "blinkit":
        actor_input["maxResults"] = min(depth, int(template.get("maxResults", depth)))
    elif platform == "zepto":
        actor_input["maxItemsPerQuery"] = min(depth, int(template.get("maxItemsPerQuery", depth)))
        actor_input["maxItems"] = min(depth * query_count, int(template.get("maxItems", depth * query_count)))
    elif platform == "instamart":
        actor_input["maxResults"] = min(depth, int(template.get("maxResults", depth)))
    elif platform == "amazon":
        actor_input["maxResultsPerQuery"] = min(depth, int(template.get("maxResultsPerQuery", depth)))
    elif platform == "flipkart":
        actor_input["maxProducts"] = min(depth * query_count, int(template.get("maxProducts", depth * query_count)))


def observation_row(user_id: str, run: dict[str, Any], item_index: int, item: dict[str, Any]) -> dict[str, Any]:
    """Preserve the full actor item alongside mapped comparison fields."""
    mapped = map_item(run["platform"], item)
    return {
        "user_id": user_id,
        "run_id": run["id"],
        "platform": run["platform"],
        "item_index": item_index,
        "source_url": mapped.get("url"),
        "payload": {
            "normalized": mapped,
            "raw": item,
            "run_scope": run.get("run_scope") or {},
        },
    }
