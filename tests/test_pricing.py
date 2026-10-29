import unittest

from api.pricing import estimate_scan


class PricingTests(unittest.TestCase):
    def test_local_and_national_platform_costs_use_distinct_geographic_scopes(self):
        estimate = estimate_scan(
            platforms=["blinkit", "amazon"],
            queries=["face serum", "vitamin c serum"],
            locations=[
                {"name": "Bandra West", "city": "Mumbai"},
                {"name": "Powai", "city": "Mumbai"},
                {"name": "Thane West", "city": "Mumbai"},
            ],
            max_items_per_query=20,
            spend_cap_usd=20,
        )

        self.assertEqual(estimate["estimated_cost_usd"], 0.384)
        self.assertEqual(estimate["buffered_estimate_usd"], 0.576)
        self.assertEqual(estimate["platforms"][0]["locations"], 3)
        self.assertEqual(estimate["platforms"][1]["locations"], 1)
        self.assertEqual(estimate["platforms"][1]["scope"], "national")

    def test_rejects_unknown_platform(self):
        with self.assertRaises(ValueError):
            estimate_scan(["unknown"], ["tea"], [], 20, 5)


if __name__ == "__main__":
    unittest.main()
