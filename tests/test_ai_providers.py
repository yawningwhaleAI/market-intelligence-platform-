import asyncio
import unittest

from api.ai_providers import suggest_with_providers


class AIProviderTests(unittest.TestCase):
    def test_returns_rules_when_no_provider_is_configured(self):
        result = asyncio.run(
            suggest_with_providers(
                {"product": "cold brew coffee", "industry": "food"},
                environ={},
            )
        )

        self.assertEqual(result["source"], "rule_based_fallback")
        self.assertIn("Flavours and variants", result["suggested_segments"])

    def test_fails_over_from_openrouter_to_gemini(self):
        calls = []

        async def fake_post(url, headers, payload):
            calls.append(url)
            if "openrouter.ai" in url:
                raise RuntimeError("provider unavailable")
            return {
                "candidates": [{"content": {"parts": [{"text": '{"category_family":"Food & drink","suggested_segments":["Low sugar","Variety packs"],"comparison_attributes":["Ingredients","Price per serving"],"search_phrases":["sparkling tea","low sugar tea"],"research_angles":[]}' }]}}]
            }

        result = asyncio.run(
            suggest_with_providers(
                {"product": "sparkling tea", "industry": "beverage"},
                environ={
                    "AI_PROVIDER_ORDER": "openrouter,gemini",
                    "OPENROUTER_API_KEY": "test-openrouter-key",
                    "OPENROUTER_MODEL": "test/free-model",
                    "GEMINI_API_KEY": "test-gemini-key",
                    "GEMINI_MODEL": "test-gemini-model",
                },
                post_json=fake_post,
            )
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["source"], "ai")
        self.assertEqual(result["suggested_segments"], ["Low sugar", "Variety packs"])


if __name__ == "__main__":
    unittest.main()
