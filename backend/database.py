from __future__ import annotations

import json
import ssl
import asyncpg
from typing import List, Optional

from models import IssuePackage, WeeklyBatch
from config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None or _pool._closed:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=1,
            max_size=5,
            statement_cache_size=0,
            ssl=ssl_ctx,
        )
    return _pool


async def init_db():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT PRIMARY KEY,
                    week_date TEXT NOT NULL,
                    track TEXT NOT NULL,
                    title TEXT NOT NULL,
                    data JSONB NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_issues_week_date ON issues (week_date)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_issues_track ON issues (track)
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_batches (
                    week_date TEXT PRIMARY KEY,
                    generated_at TEXT NOT NULL,
                    issue_count INTEGER NOT NULL
                )
            """)

            # Enable RLS on tables
            await conn.execute("ALTER TABLE issues ENABLE ROW LEVEL SECURITY")
            await conn.execute("ALTER TABLE weekly_batches ENABLE ROW LEVEL SECURITY")

            # Allow public read access (anon users can read issues)
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE policyname = 'issues_select_policy'
                    ) THEN
                        CREATE POLICY issues_select_policy ON issues
                            FOR SELECT USING (true);
                    END IF;
                END $$
            """)
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE policyname = 'weekly_batches_select_policy'
                    ) THEN
                        CREATE POLICY weekly_batches_select_policy ON weekly_batches
                            FOR SELECT USING (true);
                    END IF;
                END $$
            """)

            # Only service_role (backend) can insert/update/delete
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE policyname = 'issues_insert_policy'
                    ) THEN
                        CREATE POLICY issues_insert_policy ON issues
                            FOR INSERT WITH CHECK (current_setting('role') = 'service_role');
                    END IF;
                END $$
            """)
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE policyname = 'issues_update_policy'
                    ) THEN
                        CREATE POLICY issues_update_policy ON issues
                            FOR UPDATE USING (current_setting('role') = 'service_role');
                    END IF;
                END $$
            """)
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE policyname = 'issues_delete_policy'
                    ) THEN
                        CREATE POLICY issues_delete_policy ON issues
                            FOR DELETE USING (current_setting('role') = 'service_role');
                    END IF;
                END $$
            """)
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies WHERE policyname = 'weekly_batches_modify_policy'
                    ) THEN
                        CREATE POLICY weekly_batches_modify_policy ON weekly_batches
                            FOR ALL USING (current_setting('role') = 'service_role');
                    END IF;
                END $$
            """)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"DB init failed: {e}")
        raise


async def save_batch(batch: WeeklyBatch) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO weekly_batches (week_date, generated_at, issue_count)
            VALUES ($1, $2, $3)
            ON CONFLICT (week_date) DO UPDATE SET
                generated_at = EXCLUDED.generated_at,
                issue_count = EXCLUDED.issue_count
        """, batch.week_date, batch.generated_at.isoformat(), len(batch.issues))

        await conn.execute(
            "DELETE FROM issues WHERE week_date = $1", batch.week_date
        )

        for issue in batch.issues:
            await conn.execute("""
                INSERT INTO issues (id, week_date, track, title, data, created_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            """,
                issue.id,
                issue.week_date,
                issue.track.value,
                issue.title,
                issue.model_dump_json(),
                issue.created_at.isoformat(),
            )


async def get_issues_by_week(
    week_date: Optional[str] = None,
    track: Optional[str] = None,
) -> List[IssuePackage]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if week_date is None:
            row = await conn.fetchrow(
                "SELECT week_date FROM weekly_batches ORDER BY week_date DESC LIMIT 1"
            )
            if row is None:
                return []
            week_date = row["week_date"]

        if track:
            rows = await conn.fetch(
                "SELECT data FROM issues WHERE week_date = $1 AND track = $2 ORDER BY created_at ASC",
                week_date, track,
            )
        else:
            rows = await conn.fetch(
                "SELECT data FROM issues WHERE week_date = $1 ORDER BY created_at ASC",
                week_date,
            )

        return [IssuePackage.model_validate(json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]) for row in rows]


async def get_issue_by_id(issue_id: str) -> Optional[IssuePackage]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT data FROM issues WHERE id = $1", issue_id
        )
        if row is None:
            return None
        data = json.loads(row["data"]) if isinstance(row["data"], str) else row["data"]
        return IssuePackage.model_validate(data)


async def get_all_weeks() -> List[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT week_date FROM weekly_batches ORDER BY week_date DESC"
        )
        return [row["week_date"] for row in rows]


async def get_latest_week() -> Optional[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT week_date FROM weekly_batches ORDER BY week_date DESC LIMIT 1"
        )
        return row["week_date"] if row else None
