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
    latency_ms INTEGER,
    attempts INTEGER,
    status TEXT,
    error_code TEXT
)
"""


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute(CREATE_TABLE_SQL)
    return connection


def record_trace(trace: CallTrace) -> None:
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO call_traces (
                request_id, timestamp, requested_model, actual_model,
                input_tokens, output_tokens, latency_ms, attempts, status,
                error_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.request_id,
                trace.timestamp.isoformat(),
                trace.requested_model,
                trace.actual_model,
                trace.input_tokens,
                trace.output_tokens,
                trace.latency_ms,
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
                   input_tokens, output_tokens, latency_ms, attempts, status,
                   error_code
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
            latency_ms=row[6],
            attempts=row[7],
            status=row[8],
            error_code=row[9],
        )
        for row in rows
    ]
