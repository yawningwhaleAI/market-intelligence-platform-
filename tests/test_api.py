import unittest

from fastapi.testclient import TestClient

from api.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_and_metadata(self):
        self.assertEqual(self.client.get("/api/health").json()["product"], "Scoutwise")
        meta = self.client.get("/api/meta").json()
        self.assertEqual({p["id"] for p in meta["platforms"]}, {"blinkit", "zepto", "instamart", "amazon", "flipkart"})
        self.assertEqual(len(meta["locations"]), 8)
        self.assertIn("do not verify", meta["location_note"].lower())

    def test_suggestion_and_estimate(self):
        result = self.client.post("/api/suggestions", json={"product": "sunscreen"})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()["search_phrases"])
        estimate = self.client.post("/api/estimate", json={"platforms": ["blinkit"], "queries": ["sunscreen"], "locations": [{"name": "Indiranagar", "city": "Bengaluru"}], "max_items_per_query": 20, "spend_cap_usd": 2})
        self.assertEqual(estimate.status_code, 200)
        self.assertTrue(estimate.json()["within_cap"])

    def test_auth_disabled_until_supabase_configured(self):
        result = self.client.post("/api/auth/signup", json={"email": "founder@example.test", "password": "a-safe-password"})
        if not __import__("os").getenv("SUPABASE_URL"):
            self.assertEqual(result.status_code, 503)


if __name__ == "__main__":
    unittest.main()
