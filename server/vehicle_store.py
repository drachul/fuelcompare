"""Persistent SQLite storage for vehicle specifications and manual overrides."""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from flask import Flask, current_app


SCHEMA = """
CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT NOT NULL UNIQUE,
    epa_vehicle_id TEXT,
    label TEXT NOT NULL,
    year TEXT,
    make TEXT,
    model TEXT,
    trim TEXT,
    data_json TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS vehicles_epa_vehicle_id
    ON vehicles(epa_vehicle_id)
    WHERE epa_vehicle_id IS NOT NULL AND epa_vehicle_id != '';
"""


def init_app(app: Flask) -> None:
    """Create the vehicle database and schema for an application instance."""
    path = Path(app.config["VEHICLE_DB_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as connection:
        connection.executescript(SCHEMA)


def _connect(path: Path | None = None) -> sqlite3.Connection:
    database_path = path or Path(current_app.config["VEHICLE_DB_PATH"])
    connection = sqlite3.connect(database_path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _nonempty(value: object) -> bool:
    return value is not None and value != ""


def _cache_key(data: dict) -> str:
    epa_vehicle_id = str(data.get("epa_vehicle_id") or data.get("id") or "").strip()
    if epa_vehicle_id:
        return f"epa:{epa_vehicle_id}"

    identity = [data.get(field) for field in ("year", "make", "model", "trim")]
    if all(_nonempty(value) for value in identity[:3]):
        return "manual:" + ":".join(_normalized(value) for value in identity)
    return f"manual-label:{_normalized(data.get('label') or 'vehicle')}"


def _display_label(data: dict) -> str:
    if data.get("label"):
        return str(data["label"]).strip()
    identity = [data.get(field) for field in ("year", "make", "model")]
    label = " ".join(str(value).strip() for value in identity if _nonempty(value))
    trim = str(data.get("trim") or "").strip()
    return f"{label} — {trim}" if label and trim else label or "Saved vehicle"


def _row_to_vehicle(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = json.loads(row["data_json"])
    data.update(
        {
            "record_id": row["id"],
            "epa_vehicle_id": row["epa_vehicle_id"] or data.get("epa_vehicle_id") or "",
            "label": row["label"],
            "source": row["source"],
            "saved_at": row["updated_at"],
        }
    )
    return data


def get_by_id(record_id: int | str) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM vehicles WHERE id = ?", (record_id,)
        ).fetchone()
    return _row_to_vehicle(row)


def get_by_epa_id(vehicle_id: str) -> dict | None:
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM vehicles WHERE epa_vehicle_id = ?", (str(vehicle_id),)
        ).fetchone()
    return _row_to_vehicle(row)


def list_vehicles() -> list[dict]:
    with _connect() as connection:
        rows = connection.execute(
            "SELECT * FROM vehicles ORDER BY updated_at DESC, id DESC"
        ).fetchall()
    return [_row_to_vehicle(row) for row in rows]


def save_vehicle(data: dict, source: str, record_id: int | str | None = None) -> dict:
    """Merge and save a vehicle, preserving previously collected fields."""
    incoming = {key: value for key, value in data.items() if _nonempty(value)}
    existing = get_by_id(record_id) if record_id else None
    if existing is None:
        epa_vehicle_id = incoming.get("epa_vehicle_id") or incoming.get("id")
        existing = get_by_epa_id(str(epa_vehicle_id)) if epa_vehicle_id else None

    merged = {}
    if existing:
        merged.update(
            {
                key: value
                for key, value in existing.items()
                if key not in {"record_id", "source", "saved_at"}
            }
        )
    merged.update(incoming)

    epa_vehicle_id = str(merged.get("epa_vehicle_id") or merged.get("id") or "").strip()
    if epa_vehicle_id:
        merged["epa_vehicle_id"] = epa_vehicle_id
    cache_key = _cache_key(merged)
    if existing and record_id and not epa_vehicle_id:
        # A loaded manual record keeps its identity even if its label changes.
        with _connect() as connection:
            row = connection.execute(
                "SELECT cache_key FROM vehicles WHERE id = ?", (record_id,)
            ).fetchone()
        if row:
            cache_key = row["cache_key"]

    label = _display_label(merged)
    merged["label"] = label
    serialized = json.dumps(merged, separators=(",", ":"), sort_keys=True)
    identity = [
        str(merged.get(field) or "").strip()
        for field in ("year", "make", "model", "trim")
    ]

    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO vehicles (
                cache_key, epa_vehicle_id, label, year, make, model, trim,
                data_json, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                epa_vehicle_id = excluded.epa_vehicle_id,
                label = excluded.label,
                year = excluded.year,
                make = excluded.make,
                model = excluded.model,
                trim = excluded.trim,
                data_json = excluded.data_json,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (cache_key, epa_vehicle_id or None, label, *identity, serialized, source),
        )
        row = connection.execute(
            "SELECT * FROM vehicles WHERE cache_key = ?", (cache_key,)
        ).fetchone()
    return _row_to_vehicle(row)
