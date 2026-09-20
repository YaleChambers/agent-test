import json
import sqlite3
from datetime import datetime
from pathlib import Path

from ..schemas import CallTrace


DATABASE_PATH = Path(__file__).parent.parent.parent / "traces.db"
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS call_traces (
    request_id TEXT PRIMARY KEY,
    timestamp TEXT,
    requested_model TEXT,
    actual_model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_tokens INTEGER,
    reasoning_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    ttft_ms REAL,
    cost_usd REAL,
    route TEXT,
    attempts INTEGER,
    status TEXT,
    error_code TEXT
)
"""

# 新增列迁移：若列已存在则忽略（SQLite 不支持 ADD COLUMN IF NOT EXISTS 的旧版本用 try/except）
_NEW_COLUMNS = [
    ("cached_tokens", "INTEGER"),
    ("reasoning_tokens", "INTEGER"),
    ("total_tokens", "INTEGER"),
    ("ttft_ms", "REAL"),
    ("cost_usd", "REAL"),
    ("route", "TEXT"),
]


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute(CREATE_TABLE_SQL)
    for col_name, col_type in _NEW_COLUMNS:
        try:
            connection.execute(
                f"ALTER TABLE call_traces ADD COLUMN {col_name} {col_type}"
            )
        except sqlite3.OperationalError:
            pass  # 列已存在
    return connection


def record_trace(trace: CallTrace) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO call_traces (
                request_id, timestamp, requested_model, actual_model,
                input_tokens, output_tokens, cached_tokens, reasoning_tokens,
                total_tokens, latency_ms, ttft_ms, cost_usd, route, attempts,
                status, error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.request_id,
                trace.timestamp.isoformat(),
                trace.requested_model,
                trace.actual_model,
                trace.input_tokens,
                trace.output_tokens,
                trace.cached_tokens,
                trace.reasoning_tokens,
                trace.total_tokens,
                trace.latency_ms,
                trace.ttft_ms,
                trace.cost_usd,
                json.dumps(trace.route, ensure_ascii=False)
                if trace.route is not None
                else None,
                trace.attempts,
                trace.status,
                trace.error_code,
            ),
        )


def get_traces(limit: int = 20) -> list[CallTrace]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT request_id, timestamp, requested_model, actual_model,
                   input_tokens, output_tokens, cached_tokens, reasoning_tokens,
                   total_tokens, latency_ms, ttft_ms, cost_usd, route, attempts,
                   status, error_code
            FROM call_traces
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        CallTrace(
            request_id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            requested_model=row[2],
            actual_model=row[3],
            input_tokens=row[4],
            output_tokens=row[5],
            cached_tokens=row[6],
            reasoning_tokens=row[7],
            total_tokens=row[8],
            latency_ms=row[9],
            ttft_ms=row[10],
            cost_usd=row[11],
            route=json.loads(row[12]) if row[12] is not None else None,
            attempts=row[13],
            status=row[14],
            error_code=row[15],
        )
        for row in rows
    ]
