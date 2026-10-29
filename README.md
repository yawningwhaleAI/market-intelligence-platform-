# Scoutwise

Scoutwise is a founder-focused market-intelligence workspace. Users create an account first, save a research plan as they work, estimate scan cost, launch selected Apify actors, and return to saved product observations and past scans.

## Local setup

1. Create a Supabase project and apply the migrations in `supabase/migrations/` in order. The research-execution migration has already been applied to the connected Scoutwise Supabase project.
2. Copy `.env.example` to `.env` in this repository root. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and a URL-safe base64 encryption key containing 32 random bytes. Optional OpenRouter and Gemini keys are only used on the server.
3. Install the pinned requirements in a Python 3.12 environment.
4. Start the app with `uvicorn index:app --reload --port 8000`.

Apify connections require the encryption key to be configured. User tokens are validated with Apify and encrypted before storage. The database uses the signed-in user's Supabase JWT and row-level security; no service-role key is used by the app.

## Current scope

- Research drafts autosave to `research_projects`; signing in later reloads the user's plans.
- Scan batches and actor runs are saved, configured Apify actors are started, and returned raw items plus normalized fields are persisted in `market_observations`.
- The results page shows product/brand, pack size, price/MRP, rating, stock, locality coverage, estimated cost, actor-reported cost, and run errors.
- Email confirmation can establish the Scoutwise HTTP-only session; login resumes the user's workspace.
- Result status and dataset import currently refresh when a user opens a scan. There is no scheduled background poller yet.
- Amazon and Flipkart use national scope. Quick-commerce localities are starter suggestions from the supplied project material, not verified serviceability or dark-store-density data.
- Blinkit needs coordinates for each chosen locality; Zepto accepts the locality list in one actor run; Instamart is limited to configured city mappings.
- Cost figures are estimates from the supplied pilot actor evaluations. Actual Apify charges can vary.
- Provider suggestions fall back to editable built-in category templates.

## Checks

Run `python -m unittest discover -s tests -p "test_*.py"` from the repository root.

