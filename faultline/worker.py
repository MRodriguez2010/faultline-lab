"""A real worker process. Explicit fault points terminate only this child process."""
from __future__ import annotations

import argparse
import os
import re
import time

from . import store


def contract_error(event: dict) -> str | None:
    expected = {"tenant", "event_id", "order_id", "amount_minor", "currency", "unit", "kind"}
    if set(event) != expected:
        return "unexpected fields"
    if any(not isinstance(event[key], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", event[key]) for key in ("tenant", "event_id", "order_id")):
        return "invalid identity"
    if type(event["amount_minor"]) is not int or abs(event["amount_minor"]) > 10**9:
        return "invalid amount"
    if event["currency"] != "USD" or event["unit"] != "cents":
        return "unsupported currency or unit"
    if event["kind"] not in {"sale", "refund"}:
        return "unsupported event kind"
    if (event["kind"] == "sale" and event["amount_minor"] <= 0) or (event["kind"] == "refund" and event["amount_minor"] >= 0):
        return "amount sign does not match event kind"
    return None


def process(ident: str, *, crash: str = "none", crash_after: int = 1, deadline: float | None = None) -> int:
    store.run_id(ident)
    processed = 0
    while True:
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("worker action deadline exceeded")
        with store.connect() as db:
            state = db.execute("SELECT * FROM fl_runs WHERE id=%s FOR UPDATE", (ident,)).fetchone()
            if not state or state["cancelled"]:
                return processed
            row = db.execute("""SELECT seq,payload FROM fl_deliveries d WHERE d.run=%s
              AND NOT EXISTS (SELECT 1 FROM fl_ack a WHERE a.run=d.run AND a.seq=d.seq)
              ORDER BY seq LIMIT 1""", (ident,)).fetchone()
            if not row:
                return processed
            event, seq = row["payload"], row["seq"]
            if crash == "before_write" and processed + 1 == crash_after:
                os._exit(75)
            error = contract_error(event)
            if state["mode"] == "safe" and error:
                db.execute("INSERT INTO fl_quarantine VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (ident, seq, error))
            else:
                # Legacy deliberately treats every delivery as a new business effect.
                should_insert = True
                if state["mode"] == "safe":
                    conflicting = db.execute("""SELECT payload FROM fl_deliveries WHERE run=%s AND seq<%s
                      AND payload->>'tenant'=%s AND payload->>'event_id'=%s ORDER BY seq LIMIT 1""",
                      (ident, seq, event["tenant"], event["event_id"])).fetchone()
                    if conflicting and conflicting["payload"] != event:
                        db.execute("INSERT INTO fl_quarantine VALUES (%s,%s,%s)", (ident, seq, "conflicting event identity"))
                        should_insert = False
                    else:
                        should_insert = db.execute("INSERT INTO fl_effects VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id",
                          (ident, event["tenant"], event["event_id"])).fetchone() is not None
                if should_insert:
                    # Even the fault demonstration accepts only bounded scalar envelopes.
                    if not all(key in event for key in ("tenant", "event_id", "order_id", "amount_minor")) or type(event["amount_minor"]) is not int or abs(event["amount_minor"]) > 10**9:
                        raise ValueError("legacy demonstration envelope is unsupported")
                    db.execute("INSERT INTO fl_entries(run,seq,tenant,event_id,order_id,amount_minor) VALUES (%s,%s,%s,%s,%s,%s)",
                      (ident, seq, event["tenant"], event["event_id"], event["order_id"], event["amount_minor"]))
            if crash == "before_commit" and processed + 1 == crash_after:
                os._exit(75)
            if state["mode"] == "legacy":
                # This is the intentionally broken write/ack boundary.
                db.commit()
                if crash == "after_write" and processed + 1 == crash_after:
                    os._exit(75)
                # Reacquire the lock after commit. This legacy mode is deliberately unsafe.
                db.execute("SELECT id FROM fl_runs WHERE id=%s FOR UPDATE", (ident,))
            db.execute("INSERT INTO fl_ack VALUES (%s,%s) ON CONFLICT DO NOTHING", (ident, seq))
            db.execute("UPDATE fl_runs SET revision=revision+1 WHERE id=%s", (ident,))
        processed += 1
        if crash in {"after_commit", "after_write"} and processed == crash_after:
            os._exit(75)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--crash", choices=["none", "before_write", "before_commit", "after_write", "after_commit"], default="none")
    parser.add_argument("--crash-after", type=int, default=1)
    args = parser.parse_args()
    process(args.run, crash=args.crash, crash_after=args.crash_after)


if __name__ == "__main__":
    main()
