import unittest

from api.discovery import suggest_scope


class DiscoveryTests(unittest.TestCase):
    def test_known_category_suggests_adjacent_product_segments(self):
        result = suggest_scope("vitamin c face serum", "beauty")

        self.assertEqual(result["category_family"], "Beauty & personal care")
        self.assertIn("Sun protection", result["suggested_segments"])
        self.assertIn("vitamin c face serum", result["search_phrases"])
        self.assertIn("category template", result["confidence"])

    def test_unknown_product_uses_general_template_without_claiming_market_evidence(self):
        result = suggest_scope("foldable travel kettle", "consumer electronics")

        self.assertEqual(result["category_family"], "General consumer product")
        self.assertEqual(result["confidence"], "general template")
        self.assertIn("not evidence of demand", result["note"])


if __name__ == "__main__":
    unittest.main()
