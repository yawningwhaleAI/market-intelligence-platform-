"""Minimal Apify REST client over urllib (stdlib only).

Works through the session's egress proxy. Auth is an explicit Bearer header
when APIFY_TOKEN is set, otherwise it relies on a proxy-injected credential.
No third-party dependency, so it runs anywhere Python does.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.apify.com/v2"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def _token(override: str | None = None) -> str | None:
    if override is not None:
        return override.strip() or None
    t = os.environ.get("APIFY_TOKEN", "").strip()
    return t or None


def _request(path: str, method: str = "GET", body=None, retries: int = 0,
             token: str | None = None):
    """One API call. With retries>0, transient 5xx / network errors are retried
    with backoff (use for idempotent GET polling). 4xx are never retried here."""
    url = f"{API}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    attempt = 0
    while True:
        req = urllib.request.Request(url, data=data, method=method)
        tok = _token(token)
        if tok:
            req.add_header("Authorization", f"Bearer {tok}")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:  # noqa: S310 https only
                raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < retries:
                time.sleep(3 * (attempt + 1)); attempt += 1; continue
            raise
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(3 * (attempt + 1)); attempt += 1; continue
            raise


def actor_id(slug: str) -> str:
    """`username/actor` -> `username~actor` (the API path form)."""
    return slug.replace("/", "~")


def get_actor(slug: str, token: str | None = None) -> dict | None:
    return (_request(f"acts/{actor_id(slug)}", token=token) or {}).get("data")


def start_run(slug: str, run_input: dict, token: str | None = None) -> dict:
    """Start an actor run. Raises urllib.error.HTTPError on 4xx/5xx."""
    return _request(f"acts/{actor_id(slug)}/runs", "POST", run_input,
                    token=token)["data"]


def wait_for_run(run_id: str, poll_s: int = 4, timeout_s: int = 600,
                 token: str | None = None) -> dict:
    waited = 0
    while waited < timeout_s:
        time.sleep(poll_s)
        waited += poll_s
        run = _request(f"actor-runs/{run_id}", retries=4, token=token)["data"]
        if run["status"] in TERMINAL:
            return run
    return _request(f"actor-runs/{run_id}", retries=4, token=token)["data"]


def get_dataset_items(dataset_id: str, token: str | None = None) -> list[dict]:
    """Return all items (the /items endpoint yields a bare JSON list)."""
    items = _request(f"datasets/{dataset_id}/items", retries=4, token=token)
    return items if isinstance(items, list) else []


def run_actor(slug: str, run_input: dict, timeout_s: int = 600,
              token: str | None = None) -> dict:
    """Start, wait, and collect. Returns {status, cost_usd, items, run_id}.

    Starts exactly one run. A POST timeout is ambiguous and is not retried because
    retrying could create a second paid actor run. Idempotent GETs keep retries.
    """
    run = start_run(slug, run_input, token=token)
    run = wait_for_run(run["id"], timeout_s=timeout_s, token=token)
    items = (get_dataset_items(run["defaultDatasetId"], token=token)
             if run["status"] == "SUCCEEDED" else [])
    return {
        "status": run["status"],
        "cost_usd": float(run.get("usageTotalUsd") or 0.0),
        "items": items,
        "run_id": run["id"],
    }

