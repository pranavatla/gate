import unittest

from app.provider_summary import provider_summary


class ProviderSummaryTest(unittest.TestCase):
    def test_idle_providers_are_still_listed(self):
        catalog = [("openai", "gpt-4.1-nano"), ("gemini", "gemini-3.5-flash-lite"),
                   ("anthropic", "claude-haiku-4-5-20251001"), ("bedrock", "global.amazon.nova-2-lite-v1:0")]
        models = [{"model": "bedrock/global.amazon.nova-2-lite-v1:0", "calls": 165, "tokens": 751867, "cost_usd": 0.293494},
                  {"model": "anthropic/claude-haiku-4-5-20251001", "calls": 162, "tokens": 75159, "cost_usd": 0.116579}]
        out = provider_summary(["anthropic", "openai", "gemini", "bedrock"], catalog, models)

        self.assertEqual([p["provider"] for p in out], ["anthropic", "openai", "gemini", "bedrock"])
        by = {p["provider"]: p for p in out}
        self.assertEqual(by["openai"]["calls_7d"], 0)
        self.assertEqual(by["openai"]["catalog_models"], ["openai/gpt-4.1-nano"])
        self.assertEqual(by["gemini"]["cost_usd_7d"], 0)
        self.assertEqual(by["bedrock"]["calls_7d"], 165)
        self.assertEqual(by["anthropic"]["tokens_7d"], 75159)

    def test_cache_rows_and_unknown_providers_do_not_leak_in(self):
        models = [{"model": "cache", "calls": 30, "tokens": 0, "cost_usd": 0.0}]
        out = provider_summary(["openai"], [("mistral", "x")], models)
        self.assertEqual(out, [{"provider": "openai", "catalog_models": [], "calls_7d": 0, "tokens_7d": 0, "cost_usd_7d": 0.0}])


if __name__ == "__main__":
    unittest.main()
