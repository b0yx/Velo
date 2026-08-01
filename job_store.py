"""Small SQLite-backed download queue used by the web application."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


class JobStore:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS download_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress REAL NOT NULL DEFAULT 0,
                    filepath TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    batch_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(download_jobs)")}
            if "batch_id" not in columns:
                connection.execute(
                    "ALTER TABLE download_jobs ADD COLUMN batch_id TEXT NOT NULL DEFAULT ''")
            # A process cannot still own these after a clean application start.
            connection.execute(
                "UPDATE download_jobs SET status='queued', updated_at=? WHERE status='running'",
                (self._now(),),
            )

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        result["config"] = json.loads(result.pop("config_json") or "{}")
        return result

    def create(self, url, config, batch_id=""):
        now = self._now()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO download_jobs
                   (url, config_json, status, progress, batch_id, created_at, updated_at)
                   VALUES (?, ?, 'queued', 0, ?, ?, ?)""",
                (url, json.dumps(config), batch_id, now, now),
            )
            job_id = cursor.lastrowid
        return self.get(job_id)

    def get(self, job_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM download_jobs WHERE id=?", (job_id,)).fetchone()
        return self._row(row)

    def pending(self):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM download_jobs WHERE status='queued' ORDER BY id"
            ).fetchall()
        return [self._row(row) for row in rows]

    def failed(self, batch_id=None):
        with self._connect() as connection:
            if batch_id:
                rows = connection.execute(
                    "SELECT * FROM download_jobs WHERE status='failed' AND batch_id=? ORDER BY id",
                    (batch_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM download_jobs WHERE status='failed' ORDER BY id"
                ).fetchall()
        return [self._row(row) for row in rows]

    def update(self, job_id, status=None, progress=None, filepath=None, error=None):
        values = {"updated_at": self._now()}
        if status is not None:
            values["status"] = status
        if progress is not None:
            values["progress"] = max(0, min(float(progress), 100))
        if filepath is not None:
            values["filepath"] = filepath
        if error is not None:
            values["error"] = error
        assignments = ", ".join(f"{key}=?" for key in values)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE download_jobs SET {assignments} WHERE id=?",
                (*values.values(), job_id),
            )

    def retry_failed(self, batch_id=None):
        jobs = self.failed(batch_id)
        if not jobs:
            return []
        now = self._now()
        with self._connect() as connection:
            if batch_id:
                connection.execute(
                    """UPDATE download_jobs
                       SET status='queued', progress=0, error='', filepath='', updated_at=?
                       WHERE status='failed' AND batch_id=?""",
                    (now, batch_id),
                )
            else:
                connection.execute(
                    """UPDATE download_jobs
                       SET status='queued', progress=0, error='', filepath='', updated_at=?
                       WHERE status='failed'""",
                    (now,),
                )
        return [self.get(job["id"]) for job in jobs]

    def skip_queued(self):
        with self._connect() as connection:
            connection.execute(
                "UPDATE download_jobs SET status='skipped', updated_at=? WHERE status='queued'",
                (self._now(),),
            )

    def state(self, limit=100, batch_id=None):
        with self._connect() as connection:
            where = " WHERE batch_id=?" if batch_id else ""
            parameters = (batch_id,) if batch_id else ()
            counts = {
                row["status"]: row["count"]
                for row in connection.execute(
                    f"SELECT status, COUNT(*) AS count FROM download_jobs{where} GROUP BY status",
                    parameters,
                )
            }
            rows = connection.execute(
                f"SELECT * FROM download_jobs{where} ORDER BY id DESC LIMIT ?",
                (*parameters, limit),
            ).fetchall()
        return {
            "queued": counts.get("queued", 0),
            "running_count": counts.get("running", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "skipped": counts.get("skipped", 0),
            "failed_jobs": [self._row(row) for row in rows if row["status"] == "failed"],
            "jobs": [self._row(row) for row in rows],
        }

    def latest_batch_id(self):
        with self._connect() as connection:
            row = connection.execute(
                """SELECT batch_id FROM download_jobs
                   WHERE batch_id != '' ORDER BY id DESC LIMIT 1"""
            ).fetchone()
        return row["batch_id"] if row else ""
