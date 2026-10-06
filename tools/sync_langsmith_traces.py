#!/usr/bin/env python3
"""Sync LangSmith traces to Postgres for Grafana dashboards.

Runs periodically (e.g., every 5 minutes via cron or systemd timer) to fetch new traces
from LangSmith and store them locally, creating a historical record for dashboards and
enabling trace linking from alerts.

    LANGSMITH_API_KEY=... python tools/sync_langsmith_traces.py [--since MINUTES_AGO]

Environment:
- LANGSMITH_API_KEY: Your LangSmith API key
- DATABASE_URL: Postgres connection string (default from .env or app.config)
"""
import os
import sys
import asyncio
import argparse
from datetime import datetime, timedelta
import logging

import httpx
import asyncpg

log = logging.getLogger("langsmith_sync")
log.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
log.addHandler(handler)


class LangSmithClient:
    """Fetch traces from LangSmith API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.smith.langchain.com"
        self.client = httpx.AsyncClient(timeout=30)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def list_runs(self, project_name: str = None, limit: int = 100, offset: int = 0):
        """Fetch recent runs from LangSmith."""
        headers = {"x-api-key": self.api_key}
        params = {"limit": limit, "offset": offset}
        if project_name:
            params["project_name"] = project_name

        try:
            resp = await self.client.get(
                f"{self.base_url}/runs", headers=headers, params=params
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error(f"Failed to fetch runs: {e}")
            return []

    async def get_run(self, run_id: str):
        """Fetch a single run with full details."""
        headers = {"x-api-key": self.api_key}
        try:
            resp = await self.client.get(
                f"{self.base_url}/runs/{run_id}", headers=headers
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.error(f"Failed to fetch run {run_id}: {e}")
            return None


async def sync_traces(api_key: str, db_url: str, since_minutes: int = 30):
    """Fetch LangSmith traces and sync to Postgres."""
    if not api_key:
        log.error("LANGSMITH_API_KEY not set")
        return 1

    conn = await asyncpg.connect(db_url)
    try:
        async with LangSmithClient(api_key) as ls:
            log.info(f"Fetching LangSmith traces from the last {since_minutes} minutes...")

            # Fetch recent runs (LangSmith API returns most recent first)
            runs = await ls.list_runs(limit=100)
            if not runs:
                log.info("No runs found")
                return 0

            synced = 0
            skipped = 0
            cutoff = datetime.utcnow() - timedelta(minutes=since_minutes)

            for run in runs:
                run_id = run.get("id")
                created_at = run.get("created_at")

                if not run_id or not created_at:
                    continue

                # Parse timestamp
                try:
                    created_ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except Exception:
                    created_ts = datetime.utcnow()

                # Skip old runs
                if created_ts < cutoff:
                    log.info(f"Skipping run {run_id} (older than {since_minutes} min)")
                    break

                # Check if already synced
                existing = await conn.fetchval(
                    "SELECT 1 FROM langsmith_traces WHERE ls_run_id = $1",
                    run_id
                )
                if existing:
                    skipped += 1
                    continue

                # Extract data
                run_name = run.get("name", "unknown")
                status = run.get("status", "pending")
                started_at = run.get("start_time")
                ended_at = run.get("end_time")

                # Try to extract request_id from metadata
                metadata = run.get("extra", {})
                request_id = None
                if "request_id" in metadata:
                    request_id = metadata["request_id"]

                # Extract input/output
                inputs = run.get("inputs", {})
                outputs = run.get("outputs", {})
                error = run.get("error")

                # Extract LangSmith metadata
                ls_metadata = metadata.copy()
                ls_provider = ls_metadata.get("ls_provider")
                ls_model_name = ls_metadata.get("ls_model_name")
                usage = ls_metadata.get("usage_metadata", {})
                cost_metadata = ls_metadata.get("cost_metadata", {})

                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
                cost_usd = cost_metadata.get("total_cost") if isinstance(cost_metadata, dict) else None

                # Calculate latency
                latency_ms = None
                if started_at and ended_at:
                    try:
                        start_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        end_dt = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
                        latency_ms = int((end_dt - start_dt).total_seconds() * 1000)
                    except Exception:
                        pass

                # Insert into Postgres
                try:
                    await conn.execute(
                        """
                        INSERT INTO langsmith_traces (
                            ls_run_id, request_id, created_at, started_at, ended_at,
                            run_type, run_name, status, input_data, output_data,
                            error_message, metadata, latency_ms, cost_usd,
                            ls_provider, ls_model_name, input_tokens, output_tokens
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                        """,
                        run_id, request_id, created_ts, started_at, ended_at,
                        run.get("run_type"), run_name, status, inputs, outputs,
                        error, ls_metadata, latency_ms, cost_usd,
                        ls_provider, ls_model_name, input_tokens, output_tokens
                    )
                    synced += 1
                    if synced % 10 == 0:
                        log.info(f"Synced {synced} traces...")
                except Exception as e:
                    log.error(f"Failed to insert run {run_id}: {e}")

            log.info(f"Sync complete: {synced} synced, {skipped} skipped")
            return 0

    finally:
        await conn.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Sync LangSmith traces to Postgres"
    )
    parser.add_argument(
        "--since", type=int, default=30,
        help="Fetch traces from the last N minutes (default 30)"
    )
    args = parser.parse_args()

    api_key = os.getenv("LANGSMITH_API_KEY", "").strip()
    db_url = os.getenv("DATABASE_URL", "")

    if not db_url:
        # Try to load from app config
        try:
            from app.config import DATABASE_URL
            db_url = DATABASE_URL
        except ImportError:
            log.error("DATABASE_URL not set and app.config not available")
            return 1

    return await sync_traces(api_key, db_url, since_minutes=args.since)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
