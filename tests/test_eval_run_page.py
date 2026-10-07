import asyncio
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

for name in ('ANTHROPIC_API_KEY','OPENAI_API_KEY','GEMINI_API_KEY','DATABASE_URL','REDIS_URL'):
    os.environ.setdefault(name, 'unit-test-placeholder')
from app import stats_quality
from fastapi import HTTPException


class RunPageTests(unittest.TestCase):
    def row(self):
        return dict(run_id=32, started_at=datetime(2026,10,6,tzinfo=timezone.utc), finished_at=datetime(2026,10,6,0,1,tzinfo=timezone.utc), eval_set='facts-guard-v2', prompt_name='atla-chatbot', prompt_version=6, status='done', n_cases=15, n_errors=0, avg_score=1, pass_rate=1, avg_latency_ms=1200, cost_usd=0.012, verdict='OK', baseline_score=.96, answer='PRIVATE ANSWER', tenant='PRIVATE TENANT')

    def test_summary_does_not_expose_private_columns(self):
        conn=AsyncMock(); conn.fetchrow.return_value=self.row()
        pool=MagicMock(); pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
        with patch.object(stats_quality.db,'pool',pool):
            run=asyncio.run(stats_quality.public_run(32))
        self.assertNotIn('answer',run); self.assertNotIn('tenant',run)
        self.assertEqual(conn.fetchrow.call_args.args[1],32)
        self.assertEqual(run['score'],1)
        self.assertEqual(run['pass_rate'],1)
        self.assertEqual(run['finished_at'],'2026-10-06T00:01:00Z')

    def test_running_run_preserves_missing_scores(self):
        row=self.row();row.update(status='running',avg_score=None,pass_rate=None,verdict=None)
        run=stats_quality._run(row)
        self.assertIsNone(run['score'])
        self.assertIsNone(run['verdict'])

    def test_route_rejects_invalid_ids(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app=FastAPI();app.include_router(stats_quality.router)
        with TestClient(app) as client:
            for value in ['0','-1','not-a-number']:
                self.assertEqual(client.get('/v1/stats/evals/'+value).status_code,422)

    def test_missing_run_returns_404(self):
        conn=AsyncMock();conn.fetchrow.return_value=None
        pool=MagicMock();pool.acquire.return_value.__aenter__=AsyncMock(return_value=conn)
        with patch.object(stats_quality.db,'pool',pool), self.assertRaises(HTTPException) as error:
            asyncio.run(stats_quality.public_run(9999))
        self.assertEqual(error.exception.status_code,404)
