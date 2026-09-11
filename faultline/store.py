"""PostgreSQL persistence. Every operation is scoped to a host-created run UUID."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise ValueError("invalid run identifier")
    return value


@contextmanager
def connect():
    dsn = os.environ.get("FAULTLINE_DSN")
    if not dsn:
        raise RuntimeError("Start the isolated database with scripts/lab-db.py start")
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5,
                         options="-c statement_timeout=10000 -c lock_timeout=5000") as conn:
        yield conn


def initialize():
    with connect() as db:
        db.execute("""
          CREATE TABLE IF NOT EXISTS fl_runs (
            id text PRIMARY KEY, parent text, mode text NOT NULL DEFAULT 'legacy',
            cancelled boolean NOT NULL DEFAULT false, revision bigint NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS fl_deliveries (
            run text REFERENCES fl_runs(id) ON DELETE CASCADE, seq integer,
            payload jsonb NOT NULL, PRIMARY KEY(run,seq));
          CREATE TABLE IF NOT EXISTS fl_entries (
            run text REFERENCES fl_runs(id) ON DELETE CASCADE, entry bigint GENERATED ALWAYS AS IDENTITY,
            seq integer NOT NULL, tenant text NOT NULL, event_id text NOT NULL,
            order_id text NOT NULL, amount_minor bigint NOT NULL, PRIMARY KEY(run,entry));
          CREATE TABLE IF NOT EXISTS fl_ack (
            run text REFERENCES fl_runs(id) ON DELETE CASCADE, seq integer, PRIMARY KEY(run,seq));
          CREATE TABLE IF NOT EXISTS fl_quarantine (
            run text REFERENCES fl_runs(id) ON DELETE CASCADE, seq integer,
            reason text NOT NULL, PRIMARY KEY(run,seq));
          CREATE TABLE IF NOT EXISTS fl_effects (
            run text REFERENCES fl_runs(id) ON DELETE CASCADE, tenant text, event_id text,
            PRIMARY KEY(run,tenant,event_id));
          CREATE TABLE IF NOT EXISTS fl_actions (
            run text REFERENCES fl_runs(id) ON DELETE CASCADE, request_id text,
            receipt jsonb NOT NULL, PRIMARY KEY(run,request_id));
        """)


def create() -> str:
    ident = uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO fl_runs(id) VALUES (%s)", (ident,))
    return ident


def ingest(ident: str, events: list[dict]):
    run_id(ident)
    if not isinstance(events, list) or not 1 <= len(events) <= 5000:
        raise ValueError("expected 1 to 5000 event envelopes")
    if any(not isinstance(event, dict) or len(json.dumps(event)) > 4096 for event in events):
        raise ValueError("invalid or oversized event envelope")
    with connect() as db:
        state = db.execute("SELECT * FROM fl_runs WHERE id=%s FOR UPDATE", (ident,)).fetchone()
        if not state or state["cancelled"]:
            raise ValueError("run unavailable")
        last = db.execute("SELECT COALESCE(MAX(seq),0) AS n FROM fl_deliveries WHERE run=%s", (ident,)).fetchone()["n"]
        if last + len(events) > 5000:
            raise ValueError("run event budget exceeded")
        with db.cursor() as cur:
            cur.executemany("INSERT INTO fl_deliveries VALUES (%s,%s,%s)",
                            [(ident, last+i+1, Jsonb(event)) for i, event in enumerate(events)])
        db.execute("UPDATE fl_runs SET revision=revision+1 WHERE id=%s", (ident,))


def snapshot(ident: str) -> dict:
    run_id(ident)
    with connect() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        state = db.execute("SELECT mode,cancelled,revision FROM fl_runs WHERE id=%s", (ident,)).fetchone()
        if not state:
            raise ValueError("unknown run")
        result = {"state": state}
        for name, cols, order in [
            ("deliveries", "seq,payload", "seq"),
            ("entries", "seq,tenant,event_id,order_id,amount_minor", "entry"),
            ("ack", "seq", "seq"), ("quarantine", "seq,reason", "seq"),
            ("effects", "tenant,event_id", "tenant,event_id")
        ]:
            # Identifiers below are constants from this closed list, never model input.
            result[name] = db.execute(f"SELECT {cols} FROM fl_{name} WHERE run=%s ORDER BY {order}", (ident,)).fetchall()
        return result


def branch(ident: str) -> tuple[str, str]:
    """Clone all business state in one serialized transaction; exclude action receipts."""
    run_id(ident)
    child = uuid.uuid4().hex
    with connect() as db:
        source = db.execute("SELECT * FROM fl_runs WHERE id=%s FOR UPDATE", (ident,)).fetchone()
        if not source or source["cancelled"]:
            raise ValueError("source unavailable")
        db.execute("INSERT INTO fl_runs(id,parent,mode,revision) VALUES (%s,%s,%s,%s)",
                   (child, ident, source["mode"], source["revision"]))
        for table, cols in [
            ("deliveries", "seq,payload"), ("entries", "seq,tenant,event_id,order_id,amount_minor"),
            ("ack", "seq"), ("quarantine", "seq,reason"), ("effects", "tenant,event_id")
        ]:
            order = " ORDER BY entry" if table == "entries" else ""
            db.execute(f"INSERT INTO fl_{table}(run,{cols}) SELECT %s,{cols} FROM fl_{table} WHERE run=%s{order}", (child, ident))
    return child, digest(snapshot(child))


def cancel(ident: str):
    with connect() as db:
        db.execute("UPDATE fl_runs SET cancelled=true WHERE id=%s", (run_id(ident),))


def delete(ident: str):
    with connect() as db:
        db.execute("DELETE FROM fl_runs WHERE id=%s", (run_id(ident),))
