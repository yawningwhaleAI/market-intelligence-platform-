"""Scoutwise API and first-run workspace flow."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .ai_providers import suggest_with_providers
from .credentials import decrypt_secret, encrypt_secret
from .pricing import estimate_scan
from .research import observation_row, build_actor_jobs

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
PUBLIC = ROOT / "public"
load_dotenv(ROOT / ".env", override=False)
app = FastAPI(title="Scoutwise", version="0.1.0")
app.mount("/static", StaticFiles(directory=PUBLIC), name="static")


class Brief(BaseModel):
    product: str = Field(min_length=2, max_length=120)
    industry: str = Field(default="", max_length=120)
    audience: str = Field(default="", max_length=240)
    segments: list[str] = Field(default_factory=list, max_length=12)


class EstimateRequest(BaseModel):
    platforms: list[str] = Field(min_length=1, max_length=5)
    queries: list[str] = Field(min_length=1, max_length=10)
    locations: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    max_items_per_query: int = Field(default=20, ge=1, le=100)
    spend_cap_usd: float = Field(default=5, gt=0, le=100)


class ApifyConnect(BaseModel):
    token: str = Field(min_length=10, max_length=500)


class AuthPayload(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


class AuthSessionPayload(BaseModel):
    access_token: str = Field(min_length=20, max_length=5000)
    refresh_token: str = Field(min_length=20, max_length=1000)


class SavePlan(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    brief: dict[str, Any]
    scope: dict[str, Any]


class StartScan(BaseModel):
    idempotency_key: UUID


@app.get("/")
def home():
    return FileResponse(PUBLIC / "index.html")


@app.get("/auth/callback")
def auth_callback():
    # Supabase redirects the verified session to the SPA, which exchanges it
    # for HttpOnly cookies through the authenticated session endpoint below.
    return FileResponse(PUBLIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "product": "Scoutwise"}


@app.get("/api/integrations")
def integrations():
    from .ai_providers import configured_provider_names
    return {
        "ai_providers": configured_provider_names(),
        "supabase_auth": _supabase_configured(),
        "credential_encryption": bool(os.getenv("SCOUTWISE_CREDENTIAL_ENCRYPTION_KEY", "").strip()),
    }


@app.get("/api/meta")
def metadata():
    actors = yaml.safe_load((BACKEND / "config" / "actors.yaml").read_text(encoding="utf-8")) or {}
    locations = yaml.safe_load((BACKEND / "config" / "locations.yaml").read_text(encoding="utf-8")) or {}
    names = {"blinkit": "Blinkit", "zepto": "Zepto", "instamart": "Instamart", "amazon": "Amazon", "flipkart": "Flipkart"}
    platforms = [{"id": key, "name": names[key], "scope": "city/locality" if key in {"blinkit", "zepto", "instamart"} else "national"} for key in names if key in actors.get("platforms", {})]
    all_locations = locations.get("cities", locations.get("locations", []))
    return {"platforms": platforms, "locations": all_locations, "location_note": "Starter locality suggestions only. They do not verify serviceability or dark-store density."}


@app.post("/api/suggestions")
async def suggestions(brief: Brief):
    return await suggest_with_providers(brief.model_dump())


@app.post("/api/estimate")
def estimate(request: EstimateRequest):
    try:
        return estimate_scan(**request.model_dump())
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/apify/validate")
async def validate_apify(credentials: ApifyConnect, request: Request):
    """Validate user-owned Apify key; never echo or log the submitted secret."""
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            result = await client.get("https://api.apify.com/v2/users/me", headers={"Authorization": f"Bearer {credentials.token}"})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Apify. Try again shortly.") from exc
    if result.status_code == 401:
        raise HTTPException(status_code=422, detail="Apify did not accept this token. Check it in Apify Console and try again.")
    if result.status_code != 200:
        raise HTTPException(status_code=502, detail="Apify could not validate this token right now.")
    try:
        encrypted = encrypt_secret(credentials.token)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Credential storage is not configured yet.") from exc
    user = (result.json() or {}).get("data", {})
    access = request.cookies.get("scoutwise_access")
    signed_in_user = await _supabase_user(access) if access else None
    if not signed_in_user:
        return {"connected": True, "account_name": user.get("username") or user.get("email") or "Apify account", "saved": False, "message": "Validated. Sign in to securely save this connection."}
    if not _supabase_configured():
        raise HTTPException(status_code=503, detail="Supabase is not configured to save this connection.")
    row = {"user_id": signed_in_user["id"], "encrypted_token": encrypted, "account_label": user.get("username") or user.get("email") or "Apify account"}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            saved = await client.post(_supabase_url("/rest/v1/apify_connections?on_conflict=user_id"), headers={**_supabase_headers(access), "Prefer": "resolution=merge-duplicates,return=minimal"}, json=row)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not save the Apify connection to Supabase.") from exc
    if saved.status_code >= 400:
        raise HTTPException(status_code=502, detail="Apify was validated, but Supabase could not save it. Apply the Scoutwise database migration and retry.")
    return {"connected": True, "account_name": row["account_label"], "saved": True, "message": "Connected and encrypted in your Scoutwise account."}


@app.get("/api/session")
async def session(request: Request, response: Response):
    configured = _supabase_configured()
    token = request.cookies.get("scoutwise_access")
    if not configured or not token:
        return {"authenticated": False, "auth_configured": configured}
    user = await _supabase_user(token)
    if not user and request.cookies.get("scoutwise_refresh"):
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                refreshed = await client.post(
                    _supabase_url("/auth/v1/token?grant_type=refresh_token"),
                    headers=_supabase_headers(),
                    json={"refresh_token": request.cookies["scoutwise_refresh"]},
                )
            if refreshed.status_code == 200:
                tokens = refreshed.json()
                user = tokens.get("user") or await _supabase_user(tokens.get("access_token", ""))
                _set_auth_cookies(response, tokens)
            else:
                response.delete_cookie("scoutwise_access", path="/")
                response.delete_cookie("scoutwise_refresh", path="/")
        except (httpx.HTTPError, ValueError):
            # A temporary network failure should not destroy the refresh cookie.
            pass
    return {"authenticated": bool(user), "auth_configured": True, "email": (user or {}).get("email")}


def _supabase_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL", "").strip() and os.getenv("SUPABASE_ANON_KEY", "").strip())


def _supabase_headers(token: str | None = None) -> dict[str, str]:
    key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    return {"apikey": key, "Authorization": f"Bearer {token or key}", "Content-Type": "application/json"}


def _supabase_url(path: str) -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/") + path


async def _require_user(request: Request) -> tuple[dict[str, Any], str]:
    token = request.cookies.get("scoutwise_access")
    if not token:
        raise HTTPException(status_code=401, detail="Sign in to access your saved research.")
    user = await _supabase_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="Your session expired. Sign in again to continue.")
    return user, token


async def _supabase_rest(
    method: str,
    resource: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
    body: Any = None,
    prefer: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[Any, httpx.Headers]:
    headers = _supabase_headers(token)
    if prefer:
        headers["Prefer"] = prefer
    if extra_headers:
        headers.update(extra_headers)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(
                method,
                _supabase_url(f"/rest/v1/{resource}"),
                headers=headers,
                params=params,
                json=body,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Supabase to load your research data.") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Supabase could not save or load this research data. Check the database migration and RLS policies.")
    if response.status_code == 204 or not response.content:
        return None, response.headers
    try:
        return response.json(), response.headers
    except ValueError:
        return None, response.headers


async def _owned_plan(project_id: UUID, user_id: str, token: str) -> dict[str, Any]:
    rows, _ = await _supabase_rest(
        "GET", "research_projects", token,
        params={"select": "*", "id": f"eq.{project_id}", "user_id": f"eq.{user_id}", "limit": "1"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Research plan not found.")
    return rows[0]


async def _supabase_user(access_token: str) -> dict[str, Any] | None:
    if not _supabase_configured():
        return None
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(_supabase_url("/auth/v1/user"), headers=_supabase_headers(access_token))
        return response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


def _set_auth_cookies(response: Response, payload: dict[str, Any]) -> None:
    secure = os.getenv("ENVIRONMENT", "production").lower() != "development"
    if payload.get("access_token"):
        response.set_cookie("scoutwise_access", payload["access_token"], httponly=True, secure=secure, samesite="lax", max_age=int(payload.get("expires_in", 3600)), path="/")
    if payload.get("refresh_token"):
        response.set_cookie("scoutwise_refresh", payload["refresh_token"], httponly=True, secure=secure, samesite="lax", max_age=60 * 60 * 24 * 30, path="/")


@app.post("/api/auth/signup")
async def signup(data: AuthPayload, response: Response):
    if not _supabase_configured():
        raise HTTPException(status_code=503, detail="Connect the Supabase project before creating an account.")
    site_url = os.getenv("SCOUTWISE_SITE_URL", "").strip().rstrip("/")
    if not site_url:
        raise HTTPException(status_code=503, detail="Set SCOUTWISE_SITE_URL to this Scoutwise app's URL before creating an account.")
    redirect_url = f"{site_url}/auth/callback"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            result = await client.post(_supabase_url("/auth/v1/signup") + "?" + urlencode({"redirect_to": redirect_url}), headers=_supabase_headers(), json={"email": data.email.strip(), "password": data.password})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Supabase Auth.") from exc
    if result.status_code >= 400:
        raise HTTPException(status_code=422, detail="Supabase could not create this account. Check the email and password, or try signing in.")
    body = result.json()
    _set_auth_cookies(response, body)
    return {"created": True, "authenticated": bool(body.get("access_token")), "confirmation_required": not bool(body.get("access_token"))}


@app.post("/api/auth/session")
async def establish_auth_session(data: AuthSessionPayload, response: Response):
    """Verify callback tokens with Supabase, then keep them in HttpOnly cookies."""
    if not _supabase_configured():
        raise HTTPException(status_code=503, detail="Supabase Auth is not configured.")
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            refreshed = await client.post(
                _supabase_url("/auth/v1/token?grant_type=refresh_token"),
                headers=_supabase_headers(),
                json={"refresh_token": data.refresh_token},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not complete sign-in with Supabase. Try the email link again.") from exc
    if refreshed.status_code != 200:
        raise HTTPException(status_code=401, detail="This email confirmation link is invalid or expired. Request a new confirmation email.")
    tokens = refreshed.json()
    user = tokens.get("user") or await _supabase_user(tokens.get("access_token", ""))
    if not user or not tokens.get("access_token") or not tokens.get("refresh_token"):
        raise HTTPException(status_code=401, detail="Supabase could not establish a session. Sign in to continue.")
    _set_auth_cookies(response, tokens)
    return {"authenticated": True, "email": user.get("email")}


@app.post("/api/auth/login")
async def login(data: AuthPayload, response: Response):
    if not _supabase_configured():
        raise HTTPException(status_code=503, detail="Connect the Supabase project before signing in.")
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            result = await client.post(_supabase_url("/auth/v1/token?grant_type=password"), headers=_supabase_headers(), json={"email": data.email.strip(), "password": data.password})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Supabase Auth.") from exc
    if result.status_code >= 400:
        raise HTTPException(status_code=401, detail="Email or password was not accepted.")
    body = result.json()
    _set_auth_cookies(response, body)
    return {"authenticated": True, "email": (body.get("user") or {}).get("email")}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("scoutwise_access")
    if token and _supabase_configured():
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(_supabase_url("/auth/v1/logout"), headers=_supabase_headers(token))
        except httpx.HTTPError:
            pass
    response.delete_cookie("scoutwise_access", path="/")
    response.delete_cookie("scoutwise_refresh", path="/")
    return {"authenticated": False}


@app.post("/api/plans")
async def save_plan(data: SavePlan, request: Request):
    user, access = await _require_user(request)
    row = {"user_id": user["id"], "name": data.name.strip(), "brief": data.brief, "scope": data.scope, "lifecycle_status": "draft"}
    saved, _ = await _supabase_rest("POST", "research_projects", access, body=row, prefer="return=representation")
    if not saved:
        raise HTTPException(status_code=502, detail="Supabase did not return the saved research plan.")
    return {"saved": True, "id": saved[0]["id"], "name": row["name"], "lifecycle_status": "draft"}


@app.get("/api/plans")
async def list_plans(request: Request):
    user, access = await _require_user(request)
    rows, _ = await _supabase_rest(
        "GET", "research_projects", access,
        params={"select": "id,name,brief,scope,lifecycle_status,created_at,updated_at", "user_id": f"eq.{user['id']}", "order": "updated_at.desc", "limit": "100"},
    )
    return {"plans": rows or []}


@app.get("/api/apify/status")
async def apify_status(request: Request):
    user, access = await _require_user(request)
    rows, _ = await _supabase_rest(
        "GET", "apify_connections", access,
        params={"select": "account_label,updated_at", "user_id": f"eq.{user['id']}", "limit": "1"},
    )
    return {"connected": bool(rows), "account_label": rows[0].get("account_label") if rows else None}


@app.get("/api/plans/{project_id}")
async def get_plan(project_id: UUID, request: Request):
    user, access = await _require_user(request)
    plan = await _owned_plan(project_id, user["id"], access)
    scans, _ = await _supabase_rest(
        "GET", "research_scans", access,
        params={"select": "id,status,estimate,created_at,completed_at", "project_id": f"eq.{project_id}", "user_id": f"eq.{user['id']}", "order": "created_at.desc", "limit": "20"},
    )
    return {"plan": plan, "scans": scans or []}


@app.put("/api/plans/{project_id}")
async def update_plan(project_id: UUID, data: SavePlan, request: Request):
    user, access = await _require_user(request)
    await _owned_plan(project_id, user["id"], access)
    body = {"name": data.name.strip(), "brief": data.brief, "scope": data.scope, "updated_at": datetime.now(timezone.utc).isoformat()}
    rows, _ = await _supabase_rest(
        "PATCH", "research_projects", access,
        params={"id": f"eq.{project_id}", "user_id": f"eq.{user['id']}"}, body=body, prefer="return=representation",
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Research plan not found.")
    return {"saved": True, "id": str(project_id), "name": body["name"], "lifecycle_status": rows[0].get("lifecycle_status", "draft")}


async def _saved_apify_token(user_id: str, access: str) -> str:
    rows, _ = await _supabase_rest(
        "GET", "apify_connections", access,
        params={"select": "encrypted_token", "user_id": f"eq.{user_id}", "limit": "1"},
    )
    if not rows:
        raise HTTPException(status_code=409, detail="Connect your Apify account before starting a scan.")
    try:
        return decrypt_secret(rows[0]["encrypted_token"])
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="The saved Apify connection cannot be unlocked. Reconnect Apify and try again.") from exc


async def _start_apify_job(client: httpx.AsyncClient, token: str, job: dict[str, Any]) -> dict[str, Any]:
    actor_path = job["actor_id"].replace("/", "~")
    try:
        response = await client.post(
            f"https://api.apify.com/v2/acts/{actor_path}/runs",
            headers={"Authorization": f"Bearer {token}"},
            json=job["actor_input"],
        )
    except httpx.HTTPError:
        return {"ok": False, "message": "Could not reach Apify to start this actor."}
    if response.status_code not in (200, 201):
        try:
            detail = response.json().get("error", {}).get("message", "")
        except ValueError:
            detail = ""
        return {"ok": False, "message": str(detail).strip()[:240] or f"Apify could not start the {job['platform']} actor (HTTP {response.status_code})."}
    try:
        run = response.json().get("data", {})
    except ValueError:
        run = {}
    if not run.get("id"):
        return {"ok": False, "message": "Apify did not return an actor run ID."}
    return {"ok": True, "run": run}


@app.post("/api/plans/{project_id}/scans")
async def start_scan(project_id: UUID, data: StartScan, request: Request):
    user, access = await _require_user(request)
    plan = await _owned_plan(project_id, user["id"], access)
    scope = plan.get("scope") or {}
    brief = plan.get("brief") or {}
    platforms = scope.get("platforms") or []
    queries = scope.get("queries") or []
    locations = scope.get("locations") or []
    depth = int(scope.get("max_items_per_query") or 20)
    saved_estimate = scope.get("estimate") or {}
    budget = float(saved_estimate.get("spend_cap_usd") or scope.get("spend_cap_usd") or 5)
    if not brief.get("product"):
        raise HTTPException(status_code=422, detail="Add a product idea to this research plan before scanning.")
    try:
        estimate = estimate_scan(platforms, queries, locations, depth, budget)
        if not estimate["within_cap"]:
            raise HTTPException(status_code=409, detail="This scan is over your configured spend cap. Reduce localities, phrases, or result depth first.")
        actor_configs = yaml.safe_load((BACKEND / "config" / "actors.yaml").read_text(encoding="utf-8")) or {}
        jobs = build_actor_jobs(platforms, queries, locations, depth, actor_configs)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if len(jobs) > 36:
        raise HTTPException(status_code=422, detail="This scan creates too many actor jobs. Reduce the number of localities or marketplaces.")
    apify_token = await _saved_apify_token(user["id"], access)

    # Replayed requests with the same key return the prior scan rather than
    # starting additional paid Apify runs.
    prior, _ = await _supabase_rest(
        "GET", "research_scans", access,
        params={"select": "id,status", "user_id": f"eq.{user['id']}", "idempotency_key": f"eq.{data.idempotency_key}", "limit": "1"},
    )
    if prior:
        return {"scan_id": prior[0]["id"], "status": prior[0]["status"], "reused": True}

    scan_body = {
        "user_id": user["id"], "project_id": str(project_id),
        "idempotency_key": str(data.idempotency_key), "status": "queued",
        "scope": {"product": brief["product"], "platforms": platforms, "queries": queries, "locations": locations},
        "estimate": estimate,
    }
    scan_rows, _ = await _supabase_rest("POST", "research_scans", access, body=scan_body, prefer="return=representation")
    if not scan_rows:
        prior, _ = await _supabase_rest(
            "GET", "research_scans", access,
            params={"select": "id,status", "user_id": f"eq.{user['id']}", "idempotency_key": f"eq.{data.idempotency_key}", "limit": "1"},
        )
        if prior:
            return {"scan_id": prior[0]["id"], "status": prior[0]["status"], "reused": True}
        raise HTTPException(status_code=502, detail="Could not save this scan to Supabase.")
    scan_id = scan_rows[0]["id"]

    jobs_to_save = [{
        "user_id": user["id"], "project_id": str(project_id), "scan_id": scan_id,
        "platform": job["platform"], "status": "queued", "estimate": {"actor_id": job["actor_id"]},
        "run_scope": {"job_index": index, "location": job["location"], "queries": job["queries"], "actor_id": job["actor_id"]},
    } for index, job in enumerate(jobs)]
    saved_runs, _ = await _supabase_rest("POST", "research_runs", access, body=jobs_to_save, prefer="return=representation")
    if not saved_runs or len(saved_runs) != len(jobs):
        await _supabase_rest("PATCH", "research_scans", access, params={"id": f"eq.{scan_id}"}, body={"status": "failed", "completed_at": datetime.now(timezone.utc).isoformat()})
        raise HTTPException(status_code=502, detail="Could not prepare the actor runs in Supabase.")
    saved_runs.sort(key=lambda row: (row.get("run_scope") or {}).get("job_index", 0))

    semaphore = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=httpx.Timeout(22, connect=8)) as apify_client:
        async def start_one(job: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await _start_apify_job(apify_client, apify_token, job)
        results = await asyncio.gather(*(start_one(job) for job in jobs))

    started = failed = 0
    updates = []
    for db_run, result in zip(saved_runs, results, strict=True):
        if result["ok"]:
            actor_run = result["run"]
            run_status = "running" if str(actor_run.get("status", "")).upper() == "RUNNING" else "queued"
            updates.append(_supabase_rest(
                "PATCH", "research_runs", access,
                params={"id": f"eq.{db_run['id']}", "user_id": f"eq.{user['id']}"},
                body={"actor_run_id": actor_run["id"], "default_dataset_id": actor_run.get("defaultDatasetId"), "status": run_status, "started_at": actor_run.get("startedAt")},
            ))
            started += 1
        else:
            updates.append(_supabase_rest(
                "PATCH", "research_runs", access,
                params={"id": f"eq.{db_run['id']}", "user_id": f"eq.{user['id']}"},
                body={"status": "failed", "error_message": result["message"], "completed_at": datetime.now(timezone.utc).isoformat()},
            ))
            failed += 1
    await asyncio.gather(*updates)
    status = "running" if started else "failed"
    await _supabase_rest("PATCH", "research_scans", access, params={"id": f"eq.{scan_id}", "user_id": f"eq.{user['id']}"}, body={"status": status})
    await _supabase_rest(
        "PATCH", "research_projects", access,
        params={"id": f"eq.{project_id}", "user_id": f"eq.{user['id']}"},
        body={"lifecycle_status": "running" if started else "failed", "updated_at": datetime.now(timezone.utc).isoformat()},
    )
    return {"scan_id": scan_id, "status": status, "actor_jobs": len(jobs), "started": started, "failed_to_start": failed, "estimate": estimate}


async def _refresh_scan_runs(user_id: str, access: str, apify_token: str, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [row for row in runs if row.get("actor_run_id") and row.get("status") in {"queued", "running"}]
    if not active:
        return runs
    async with httpx.AsyncClient(timeout=httpx.Timeout(22, connect=8)) as client:
        async def fetch_run(row: dict[str, Any]) -> tuple[dict[str, Any], httpx.Response | None]:
            try:
                response = await client.get(
                    f"https://api.apify.com/v2/actor-runs/{row['actor_run_id']}",
                    headers={"Authorization": f"Bearer {apify_token}"},
                )
                return row, response
            except httpx.HTTPError:
                return row, None

        remote_runs = await asyncio.gather(*(fetch_run(row) for row in active))
        datasets_processed = 0
        for row, response in remote_runs:
            if response is None:
                continue
            if response.status_code >= 400:
                message = "Apify could not return this run. Check that the connected account still has access."
                await _supabase_rest("PATCH", "research_runs", access, params={"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"}, body={"status": "failed", "error_message": message, "completed_at": datetime.now(timezone.utc).isoformat()})
                row.update(status="failed", error_message=message)
                continue
            try:
                remote = response.json().get("data", {})
            except ValueError:
                continue
            remote_status = str(remote.get("status", "")).upper()
            if remote_status in {"READY", "RUNNING", "WAITING_FOR_INPUT"}:
                mapped = "running" if remote_status == "RUNNING" else "queued"
                await _supabase_rest("PATCH", "research_runs", access, params={"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"}, body={"status": mapped})
                row["status"] = mapped
                continue
            finished = remote.get("finishedAt") or datetime.now(timezone.utc).isoformat()
            if remote_status != "SUCCEEDED":
                message = "The Apify actor did not finish successfully. Inspect its run in Apify, then retry the scan."
                await _supabase_rest("PATCH", "research_runs", access, params={"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"}, body={"status": "failed", "error_message": message, "completed_at": finished, "actual_cost_usd": remote.get("usageTotalUsd")})
                row.update(status="failed", error_message=message, actual_cost_usd=remote.get("usageTotalUsd"))
                continue

            dataset_id = remote.get("defaultDatasetId") or row.get("default_dataset_id")
            if not dataset_id:
                continue
            if datasets_processed >= 4:
                continue
            try:
                dataset_response = await client.get(
                    f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                    headers={"Authorization": f"Bearer {apify_token}"},
                    params={"format": "json", "limit": "1000", "offset": "0"},
                )
                dataset_response.raise_for_status()
                items = dataset_response.json()
                if not isinstance(items, list):
                    items = []
                for offset in range(0, len(items), 100):
                    batch = [
                        observation_row(user_id, row, offset + i, item)
                        for i, item in enumerate(items[offset:offset + 100])
                        if isinstance(item, dict)
                    ]
                    if batch:
                        await _supabase_rest(
                            "POST", "market_observations", access,
                            params={"on_conflict": "run_id,item_index"}, body=batch,
                            prefer="resolution=merge-duplicates,return=minimal",
                        )
            except (httpx.HTTPError, ValueError, TypeError):
                # Keep the actor run retryable if its dataset is temporarily unavailable.
                continue
            await _supabase_rest(
                "PATCH", "research_runs", access,
                params={"id": f"eq.{row['id']}", "user_id": f"eq.{user_id}"},
                body={"status": "succeeded", "default_dataset_id": dataset_id, "item_count": len(items), "actual_cost_usd": remote.get("usageTotalUsd"), "completed_at": finished, "error_message": None},
            )
            row.update(status="succeeded", default_dataset_id=dataset_id, item_count=len(items), actual_cost_usd=remote.get("usageTotalUsd"), completed_at=finished, error_message=None)
            datasets_processed += 1
    return runs


@app.get("/api/scans/{scan_id}")
async def get_scan(scan_id: UUID, request: Request, offset: int = 0, limit: int = 200):
    user, access = await _require_user(request)
    scans, _ = await _supabase_rest(
        "GET", "research_scans", access,
        params={"select": "*", "id": f"eq.{scan_id}", "user_id": f"eq.{user['id']}", "limit": "1"},
    )
    if not scans:
        raise HTTPException(status_code=404, detail="Research scan not found.")
    scan = scans[0]
    run_rows, _ = await _supabase_rest(
        "GET", "research_runs", access,
        params={"select": "id,platform,actor_run_id,default_dataset_id,status,estimate,run_scope,item_count,actual_cost_usd,error_message,started_at,completed_at", "scan_id": f"eq.{scan_id}", "user_id": f"eq.{user['id']}", "order": "created_at.asc", "limit": "100"},
    )
    runs = run_rows or []
    if any(row.get("actor_run_id") and row.get("status") in {"queued", "running"} for row in runs):
        try:
            apify_token = await _saved_apify_token(user["id"], access)
            runs = await _refresh_scan_runs(user["id"], access, apify_token, runs)
        except HTTPException:
            # Preserve visibility of saved status if the account needs reconnecting.
            pass

    statuses = [row.get("status") for row in runs]
    active = any(status in {"queued", "running"} for status in statuses)
    succeeded = sum(status == "succeeded" for status in statuses)
    failed = sum(status == "failed" for status in statuses)
    if active:
        status = "running"
    elif succeeded and failed:
        status = "partial"
    elif succeeded:
        status = "succeeded"
    else:
        status = "failed"
    completed_at = None if active else (scan.get("completed_at") or datetime.now(timezone.utc).isoformat())
    if scan.get("status") != status or (not active and not scan.get("completed_at")):
        await _supabase_rest("PATCH", "research_scans", access, params={"id": f"eq.{scan_id}", "user_id": f"eq.{user['id']}"}, body={"status": status, "completed_at": completed_at})
        scan["status"] = status
        scan["completed_at"] = completed_at
    lifecycle = "running" if active else ("partial" if succeeded and failed else "completed" if succeeded else "failed")
    await _supabase_rest("PATCH", "research_projects", access, params={"id": f"eq.{scan['project_id']}", "user_id": f"eq.{user['id']}"}, body={"lifecycle_status": lifecycle, "updated_at": datetime.now(timezone.utc).isoformat()})

    observations: list[dict[str, Any]] = []
    total = 0
    if runs:
        run_ids = [row["id"] for row in runs]
        page_size = min(max(limit, 1), 200)
        page_offset = max(offset, 0)
        obs, headers = await _supabase_rest(
            "GET", "market_observations", access,
            params={"select": "id,run_id,platform,observed_at,payload,source_url", "user_id": f"eq.{user['id']}", "run_id": "in.(" + ",".join(run_ids) + ")", "order": "observed_at.desc", "limit": str(page_size), "offset": str(page_offset)},
            prefer="count=exact", extra_headers={"Range": f"{page_offset}-{page_offset + page_size - 1}"},
        )
        observations = [{
            "id": row["id"], "run_id": row["run_id"], "platform": row["platform"],
            "observed_at": row["observed_at"], "source_url": row.get("source_url"),
            "normalized": (row.get("payload") or {}).get("normalized", {}),
            "run_scope": (row.get("payload") or {}).get("run_scope", {}),
        } for row in (obs or [])]
        try:
            content_range = headers.get("content-range", "")
            total = int(content_range.rsplit("/", 1)[1]) if "/" in content_range else len(observations)
        except (ValueError, IndexError):
            total = len(observations)
    item_count = sum(int(row.get("item_count") or 0) for row in runs)
    actual_cost = round(sum(float(row.get("actual_cost_usd") or 0) for row in runs), 6)
    return {
        "scan": {"id": scan["id"], "project_id": scan["project_id"], "status": status, "estimate": scan.get("estimate", {}), "created_at": scan["created_at"], "completed_at": scan.get("completed_at")},
        "runs": runs, "items": observations, "item_count": item_count, "items_total": total,
        "actual_cost_usd": actual_cost, "active": active, "offset": page_offset if runs else 0,
        "limit": min(max(limit, 1), 200),
    }
