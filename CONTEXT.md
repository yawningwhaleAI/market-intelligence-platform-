# Scoutwise — Project Context

**Last updated:** 12 October 2026  
**Purpose:** Give a new contributor or AI coding assistant enough context to continue the current Scoutwise build.

## Product

Scoutwise is a founder-focused market intelligence product. The first release helps a founder describe a product, expand that brief into adjacent categories and search phrases, choose marketplaces and locations, see a cost estimate, and save the research plan. The initial coverage is Indian consumer products, with quick-commerce and ecommerce marketplace sources.

The product should treat category ideas as research prompts, not evidence of demand or market size. Founder-entered phrases and suggested scope remain editable.

### Who it is for and why it matters

Scoutwise is intended to help founders and early-stage startups make better-informed early market decisions without needing a dedicated research team. It turns an open-ended question like “what should I compare, where should I look, and what might the research cost?” into an editable, budget-aware workflow. The product should help a founder explore adjacent categories, competitors, product formats, prices, and geography, while being clear about what the available data can and cannot prove.

The project also serves as a practical portfolio build while Aryan prepares for Founder’s Office and Chief of Staff roles. It is meant to demonstrate operator skills relevant to those roles: turning ambiguity into a usable plan, prioritizing a small first release, connecting product, data, AI, and infrastructure decisions, keeping costs and risks visible, and building a repeatable decision-support workflow. These are goals for the project and its presentation; Scoutwise should not be described as already providing market conclusions or business outcomes that have not been validated.

## Current user flow

The website at `/` is account-first. New users create a Supabase Auth account (and confirm email if enabled); the callback establishes a Scoutwise HTTP-only session. Returning users sign in and the workspace reloads saved plans. From there:

1. Create a draft; it is written immediately and autosaves its brief, suggestions, selections, localities, budget, depth, and current step.
2. **Product brief:** product/idea, optional industry, and target audience.
3. **Explore scope:** suggested category family, product segments, comparison attributes, and editable search phrases.
4. **Choose coverage:** select Blinkit, Zepto, Instamart, Amazon, and/or Flipkart. Quick-commerce uses city/locality inputs; Amazon and Flipkart are national-only in the chosen actor config.
5. **Review and run:** set results per phrase and budget, review estimate, connect Apify, then launch the scan.
6. The scan detail polls actor status when opened. Completed datasets are normalized and saved to Supabase; past scans reopen from plan detail.

The location list is a starter set of localities. It does not verify platform availability, map dark-store density, or promise that every actor can serve a given locality. The interface says this explicitly.

## Implementation

- **Frontend:** static HTML, CSS, and vanilla JavaScript in `public/`.
- **Backend:** Python FastAPI in `backend/api/main.py`; `index.py` exposes the app for Vercel’s Python function routing.
- **Configuration:** YAML actor, locality, brand, and query files in `backend/config/`.
- **Apify client:** REST helpers in `backend/scrapers/apify_rest.py` and normalization helpers under `backend/processors/`.
- **Database/auth:** Supabase Auth REST endpoints and Postgres REST calls, with schema in `supabase/migrations/202610020001_scoutwise_foundation.sql`.
- **Auth confirmation:** Supabase confirmation links return to `/auth/callback`; the browser sends the URL-fragment session to the backend, which verifies it and sets HTTP-only cookies. Session checks refresh expired access tokens with the refresh cookie.
- **Hosting configuration:** `vercel.json` routes requests to `index.py`.

### Backend routes

| Route | Purpose |
|---|---|
| `GET /api/health` | Liveness check |
| `GET /api/meta` | Marketplace and locality options |
| `GET /api/integrations` | Safe configured-provider/configuration status; no secret values |
| `GET /api/session` | Current Supabase sign-in state |
| `GET /auth/callback` | Return page for Supabase email confirmation |
| `POST /api/suggestions` | Product-scope suggestions from AI providers or rule-based templates |
| `POST /api/estimate` | Cost and budget estimate for selected coverage |
| `POST /api/apify/validate` | Validate a user’s Apify token; encrypt and save it when signed in |
| `POST /api/auth/signup` | Create a Supabase Auth account |
| `POST /api/auth/login` | Sign in and set HTTP-only auth cookies |
| `POST /api/auth/session` | Verify email callback tokens and establish HTTP-only auth cookies |
| `POST /api/auth/logout` | Sign out and clear auth cookies |
| `POST /api/plans` | Save an owner-scoped research plan |
| `GET /api/plans` and `GET /api/plans/{project_id}` | List the signed-in user's plans and scan history |
| `PUT /api/plans/{project_id}` | Autosave a research draft |
| `GET /api/apify/status` | Check for the user's saved Apify connection |
| `POST /api/plans/{project_id}/scans` | Save a scan batch/run rows and start Apify actors |
| `GET /api/scans/{scan_id}` | Refresh run status, import datasets, and return saved results |

## Integrations and data

### Supabase

The user ran the foundation migration in Supabase SQL Editor and reported **“Success. No rows returned,”** which is the expected result for schema DDL. On 8 October 2026, signup returned “Could not reach Supabase Auth.” Diagnosis found the local `.env` `SUPABASE_URL` value had a duplicated `SUPABASE_URL=` prefix; it was corrected. A read-only Auth settings request using the configured publishable key returned HTTP 200 afterward, confirming that the configured project endpoint and key are accepted.

On 8 October, the signup confirmation email redirected to `localhost`, which refused the connection. Code now sets `redirect_to` to `${SCOUTWISE_SITE_URL}/auth/callback`; local `.env` has this set to `http://127.0.0.1:8003` and `ENVIRONMENT=development`. The callback page exchanges the returned access/refresh tokens with the backend; the backend verifies the access token with Supabase before setting HTTP-only cookies. `GET /api/session` attempts refresh using the refresh cookie when the access token expires. The user must add `http://127.0.0.1:8003/auth/callback` to Supabase Auth → URL Configuration → Redirect URLs, then restart the app on port 8003 and request a new confirmation email for future signups. The previously clicked link may already have verified the account before its localhost redirect failed; try signing in with the existing account first. No successful end-to-end callback has been confirmed yet.

The foundation and research-execution migrations create/update:

- `research_projects` for user-owned briefs and scan scopes.
- `apify_connections` for a user’s encrypted Apify token and account label.
- `research_runs` for per-platform run status and estimate metadata.
- `research_scans` for idempotent scan batches, scope, estimate, and lifecycle.
- `market_observations` for collected platform payloads.

Migration `20261012063102_research_execution.sql` has been applied to the connected Supabase project; table/RLS metadata was verified. Policies scope records to `auth.uid()`. The app uses the publishable Supabase key and signed-in user's JWT, never a service-role key.

### Apify

The UI asks users for their own Apify token. The backend validates it with `GET https://api.apify.com/v2/users/me`, never returns or logs the token, and encrypts it with AES-GCM before database storage. Encryption requires `SCOUTWISE_CREDENTIAL_ENCRYPTION_KEY` (URL-safe base64 encoding of 32 random bytes). If the visitor has not signed in, validation may succeed but the connection is not saved.

**Latest observed status:** recent local server logs contained two HTTP 200 responses from the validation route, so those validation attempts succeeded. A later safe connectivity check reached Apify; a request without a token returned the expected 401, and a dummy token submitted through Scoutwise returned the expected 422. The user subsequently reported seeing an issue again; no new screenshot/error text was available at the time this file was written, so the current browser symptom is not confirmed as resolved.

### AI suggestions

The provider router in `backend/api/ai_providers.py` supports OpenRouter followed by Gemini, controlled by `AI_PROVIDER_ORDER`. If both providers fail or are unavailable, it returns rule-based templates from `backend/api/discovery.py`. Built-in profiles cover several D2C categories plus a generic consumer product fallback. AI suggestions do not assert market size or demand.

Provider names and keys have been configured locally, but previous live suggestion attempts fell back to templates when outbound provider requests failed. Recheck live provider responses in the current runtime before describing AI generation as verified.

### Cost estimation and actor scope

`backend/api/pricing.py` estimates based on the measured costs recorded in `backend/config/actors.yaml`, applies a 1.5x buffer, and compares the result with the lower of the user budget and configured default run cap (currently `$5` unless overridden). This is a pre-run estimate, not a guaranteed Apify charge or an account/monthly limit.

The configured actors cover Blinkit, Zepto, Instamart, Amazon.in, and Flipkart. Current locality and field coverage assumptions come from the bundled pilot notes. Amazon and Flipkart actors are national-only; quick-commerce actors accept locality/city-specific inputs with platform-specific limitations.

## Current limitations and remaining work

- A live, paid end-to-end Apify scan has not yet been run for verification. Start with one platform, one locality, and low depth before relying on actor field mappings.
- Status refresh and dataset import happen when a signed-in user opens a scan. Apify continues remotely if the browser closes; reopening resumes sync. A scheduled background poller is not configured.
- Current results are a saved product-row table. Richer price comparisons, charts, trends, brand views, and CSV export remain future product work.
- There is no verified dark-store-density map or platform serviceability lookup.
- A Vercel deployment has not been confirmed. Local dev is open on port 8003 in the user's browser.

## Local development

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill the required local environment values in .env.
python -m uvicorn index:app --reload --port 8000
```

Open `http://127.0.0.1:8000/`; the user's current browser session has also used port `8003`.

Required/optional environment variable names are documented in `.env.example`:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` (publishable/anon key only)
- `SCOUTWISE_SITE_URL` (local app origin for confirmation links; set to the production Vercel URL at deployment)
- `ENVIRONMENT=development` for local HTTP so auth cookies work; use a production value behind HTTPS
- `SCOUTWISE_CREDENTIAL_ENCRYPTION_KEY`
- Optional: `AI_PROVIDER_ORDER`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`
- Optional: `SCOUTWISE_DEFAULT_RUN_CAP_USD`

The real `.env` must stay local and must never be committed or pasted into chat. Do not put provider keys, Apify tokens, or Supabase secret/service-role keys in frontend code.

## Verification and repository state

The repository contains unit tests under `tests/` for API behavior, pricing, discovery, credential encryption, and AI-provider routing. Eleven local checks were reported passing earlier in the build conversation; they have not been rerun as part of preparing this context file.

At the time of writing, the current branch is `feat/scoutwise-foundation`. The project files are still untracked in Git (`??`); no commit, push, or Vercel deployment is confirmed. Preserve local `.env` while preparing the first commit and verify `.gitignore` excludes it.

## Suggested next steps

1. Verify signup/email confirmation/session persistence, saved-plan resume, and RLS isolation in the local UI.
2. Run one low-cost Apify scan (one platform/locality, low result depth), confirm actor success and imported observation rows, then verify history after sign-out/sign-in.
3. Compare Apify actual usage with the estimate; estimates are not guarantees.
4. Configure the production `SCOUTWISE_SITE_URL`, Supabase redirect URLs, encryption key, and Apify/AI settings in Vercel before deployment. Keep `.env` out of Git.
