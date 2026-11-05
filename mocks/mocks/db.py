"""SQLite database connection and schema management for mock services."""

import json
import os
import sqlite3
from typing import Any
from mocks.config import settings


def get_db_path() -> str:
    """Return the absolute or relative path to the SQLite database."""
    return settings.mock_db_path


def get_connection() -> sqlite3.Connection:
    """Open a SQLite connection with Row factory and foreign keys enabled."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> None:
    """Create all required tables for mock services if they do not exist."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS clock (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            virtual_time TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS faults (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            drop_response_after_commit INTEGER DEFAULT 0,
            delay_ms INTEGER DEFAULT 0,
            error_rate REAL DEFAULT 0.0,
            duplicate_webhooks INTEGER DEFAULT 0,
            webhook_down INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS idempotency (
            key TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            response_body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (key, endpoint)
        );

        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT NOT NULL,
            resource_version INTEGER NOT NULL,
            payload TEXT NOT NULL,
            delivery_attempts INTEGER DEFAULT 0,
            delivered_at TEXT,
            status TEXT DEFAULT 'pending'
        );

        CREATE TABLE IF NOT EXISTS policies (
            id TEXT PRIMARY KEY,
            policy_number TEXT UNIQUE NOT NULL,
            insurer_name TEXT NOT NULL,
            tpa_name TEXT,
            policy_type TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            sum_insured INTEGER NOT NULL,
            balance_sum_insured INTEGER NOT NULL,
            room_rent_limit_per_day INTEGER NOT NULL,
            copay_percent INTEGER DEFAULT 0,
            deductible INTEGER DEFAULT 0,
            waiting_periods TEXT DEFAULT '[]',
            exclusions TEXT DEFAULT '[]',
            sub_limits TEXT DEFAULT '[]',
            members TEXT DEFAULT '[]',
            authorised_representatives TEXT DEFAULT '[]',
            version INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS preauths (
            id TEXT PRIMARY KEY,
            policy_id TEXT NOT NULL,
            member_id TEXT NOT NULL,
            hospital_id TEXT NOT NULL,
            admission_date TEXT NOT NULL,
            diagnosis_text TEXT NOT NULL,
            estimated_amount INTEGER NOT NULL,
            status TEXT NOT NULL,
            approved_amount INTEGER DEFAULT 0,
            conditions TEXT DEFAULT '[]',
            version INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS claims (
            id TEXT PRIMARY KEY,
            client_reference TEXT,
            policy_id TEXT NOT NULL,
            member_id TEXT NOT NULL,
            claim_type TEXT NOT NULL,
            admission_date TEXT NOT NULL,
            discharge_date TEXT NOT NULL,
            claimed_amount INTEGER NOT NULL,
            line_items TEXT DEFAULT '[]',
            documents TEXT DEFAULT '[]',
            submitted_at TEXT NOT NULL,
            status TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS queries (
            id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL,
            raised_at TEXT NOT NULL,
            due_at TEXT NOT NULL,
            items TEXT DEFAULT '[]',
            status TEXT DEFAULT 'open',
            answered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            decided_at TEXT NOT NULL,
            approved_amount INTEGER NOT NULL,
            line_decisions TEXT DEFAULT '[]',
            rejection_reason TEXT,
            policy_clause TEXT,
            letter_doc_id TEXT
        );

        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            utr TEXT NOT NULL,
            paid_at TEXT NOT NULL,
            payee TEXT NOT NULL,
            bank_account_last4 TEXT
        );

        CREATE TABLE IF NOT EXISTS hospitals (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            network_insurers TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS admissions (
            id TEXT PRIMARY KEY,
            hospital_id TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            policy_number TEXT NOT NULL,
            admission_date TEXT NOT NULL,
            discharge_date TEXT,
            diagnosis_text TEXT NOT NULL,
            status TEXT NOT NULL,
            deposit_amount INTEGER DEFAULT 0,
            deposit_status TEXT DEFAULT 'held'
        );

        CREATE TABLE IF NOT EXISTS hospital_documents (
            id TEXT PRIMARY KEY,
            admission_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            issued_at TEXT NOT NULL,
            file_path TEXT
        );

        CREATE TABLE IF NOT EXISTS bank_accounts (
            id TEXT PRIMARY KEY,
            holder_name TEXT NOT NULL,
            account_last4 TEXT NOT NULL,
            ifsc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bank_credits (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            utr TEXT NOT NULL,
            credited_at TEXT NOT NULL,
            narration TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS grievances (
            id TEXT PRIMARY KEY,
            level TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            filed_at TEXT NOT NULL,
            acknowledged_at TEXT NOT NULL,
            due_at TEXT NOT NULL,
            status TEXT NOT NULL,
            resolution_text TEXT
        );

        CREATE TABLE IF NOT EXISTS ombudsman_complaints (
            id TEXT PRIMARY KEY,
            grievance_id TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            filed_at TEXT NOT NULL,
            eligible INTEGER NOT NULL,
            eligibility_reason TEXT NOT NULL,
            status TEXT NOT NULL,
            award_amount INTEGER DEFAULT 0,
            award_issued_at TEXT,
            compliance_due_at TEXT
        );
        """)

        # Initialize singletons for clock and faults if empty
        conn.execute("""
        INSERT OR IGNORE INTO clock (id, virtual_time)
        VALUES (1, '2026-10-01T10:00:00+05:30');
        """)
        conn.execute("""
        INSERT OR IGNORE INTO faults (id, drop_response_after_commit, delay_ms, error_rate, duplicate_webhooks, webhook_down)
        VALUES (1, 0, 0, 0.0, 0, 0);
        """)
        conn.commit()
    finally:
        if close_after:
            conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert a SQLite Row to a dict, deserializing JSON fields if applicable."""
    if row is None:
        return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, str) and (v.startswith("{") or v.startswith("[")):
            try:
                d[k] = json.loads(v)
            except Exception:
                pass
    return d
