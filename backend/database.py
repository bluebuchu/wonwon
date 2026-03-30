import json
import os
import aiosqlite
from datetime import datetime
from typing import List, Optional
from models import IssuePackage, WeeklyBatch
from config import settings


async def get_db_path() -> str:
    db_path = settings.database_url
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    return db_path


async def init_db():
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id TEXT PRIMARY KEY,
                week_date TEXT NOT NULL,
                track TEXT NOT NULL,
                title TEXT NOT NULL,
                data JSON NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_week_date
            ON issues (week_date)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_track
            ON issues (track)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS weekly_batches (
                week_date TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                issue_count INTEGER NOT NULL
            )
        """)
        await db.commit()


async def save_batch(batch: WeeklyBatch) -> None:
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        # Upsert the batch record
        await db.execute("""
            INSERT INTO weekly_batches (week_date, generated_at, issue_count)
            VALUES (?, ?, ?)
            ON CONFLICT(week_date) DO UPDATE SET
                generated_at = excluded.generated_at,
                issue_count = excluded.issue_count
        """, (
            batch.week_date,
            batch.generated_at.isoformat(),
            len(batch.issues)
        ))

        # Delete existing issues for this week to replace them
        await db.execute(
            "DELETE FROM issues WHERE week_date = ?",
            (batch.week_date,)
        )

        # Insert all issues
        for issue in batch.issues:
            await db.execute("""
                INSERT INTO issues (id, week_date, track, title, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                issue.id,
                issue.week_date,
                issue.track.value,
                issue.title,
                issue.model_dump_json(),
                issue.created_at.isoformat()
            ))

        await db.commit()


async def get_issues_by_week(
    week_date: Optional[str] = None,
    track: Optional[str] = None
) -> List[IssuePackage]:
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # If no week_date given, use the latest week
        if week_date is None:
            async with db.execute(
                "SELECT week_date FROM weekly_batches ORDER BY week_date DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return []
                week_date = row["week_date"]

        query = "SELECT data FROM issues WHERE week_date = ?"
        params: list = [week_date]

        if track:
            query += " AND track = ?"
            params.append(track)

        query += " ORDER BY created_at ASC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [IssuePackage.model_validate_json(row["data"]) for row in rows]


async def get_issue_by_id(issue_id: str) -> Optional[IssuePackage]:
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT data FROM issues WHERE id = ?",
            (issue_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return IssuePackage.model_validate_json(row["data"])


async def get_all_weeks() -> List[str]:
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT week_date FROM weekly_batches ORDER BY week_date DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row["week_date"] for row in rows]


async def get_latest_week() -> Optional[str]:
    db_path = await get_db_path()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT week_date FROM weekly_batches ORDER BY week_date DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return row["week_date"]
