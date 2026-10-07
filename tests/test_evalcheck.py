import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

# Unit tests never connect to providers or the database.
for name in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'DATABASE_URL', 'REDIS_URL'):
    os.environ.setdefault(name, 'unit-test-placeholder')

from app import evalcheck


class ComparisonTests(unittest.TestCase):
    def test_finished_run_needs_three_baselines(self):
        self.assertEqual(evalcheck.verdict_for('done', 1.0, [1.0, 1.0])[0], 'BUILDING_BASELINE')

    def test_high_score_can_still_regress(self):
        self.assertEqual(evalcheck.verdict_for('done', 0.9, [1.0] * 3)[0], 'REGRESSION')

    def test_partial_run_is_unreliable(self):
        self.assertEqual(evalcheck.verdict_for('partial', 1.0, [1.0] * 3)[0], 'UNRELIABLE')

    def test_pending_runs_are_checked_in_order_even_after_alert(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{'id': 26}, {'id': 30}, {'id': 31}]
        check = AsyncMock(side_effect=[SystemExit(3), None, None])
        with patch.object(evalcheck.asyncpg, 'connect', AsyncMock(return_value=conn)), patch.object(evalcheck, 'main', check):
            asyncio.run(evalcheck.pending())
        sql = conn.fetch.call_args.args[0]
        self.assertIn('verdict IS NULL', sql)
        self.assertIn('ORDER BY id', sql)
        self.assertEqual([c.args[0] for c in check.call_args_list], ['26', '30', '31'])
        conn.close.assert_awaited_once()

    def test_database_error_is_not_hidden(self):
        conn = AsyncMock()
        conn.fetch.return_value = [{'id': 26}]
        with patch.object(evalcheck.asyncpg, 'connect', AsyncMock(return_value=conn)), patch.object(evalcheck, 'main', AsyncMock(side_effect=RuntimeError('database unavailable'))):
            with self.assertRaises(RuntimeError):
                asyncio.run(evalcheck.pending())


if __name__ == '__main__':
    unittest.main()
