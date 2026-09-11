"""Constrained action broker. No model-supplied SQL, filesystem paths, or commands."""
from __future__ import annotations
import time
import uuid
from collections import Counter

from psycopg.types.json import Jsonb

from . import store
from .worker import contract_error, process

OPERATIONS = {"inspect", "restart_worker", "rebuild_projection", "quarantine_and_replay", "abstain"}


def observe(ident: str) -> dict:
    snap = store.snapshot(ident)
    counts = Counter((e["tenant"], e["event_id"]) for e in snap["entries"])
    duplicates = [{"tenant": t, "event_id": e, "entries": n} for (t, e), n in counts.items() if n > 1]
    invalid = [{"sequence": d["seq"], "issue": contract_error(d["payload"])} for d in snap["deliveries"] if contract_error(d["payload"])]
    return {"facts": [
      {"id": "OBS-1", "kind": "health", "database": "reachable", "worker": "available"},
      {"id": "OBS-2", "kind": "delivery", "received": len(snap["deliveries"]), "acknowledged": len(snap["ack"]), "pending": len(snap["deliveries"])-len(snap["ack"])},
      {"id": "OBS-3", "kind": "projection", "entries": len(snap["entries"]), "reported_minor": sum(e["amount_minor"] for e in snap["entries"]), "duplicate_effects": duplicates[:20]},
      {"id": "OBS-4", "kind": "contract", "invalid_envelopes": invalid[:20], "quarantined": len(snap["quarantine"])},
    ], "sample": snap["entries"][:6], "revision": snap["state"]["revision"]}


class Broker:
    def __init__(self, ident: str, *, max_actions: int = 4, seconds: float = 60):
        self.ident = store.run_id(ident)
        self.remaining = max_actions
        self.deadline = time.monotonic() + seconds
        self.receipts = []

    def execute(self, proposal: dict) -> dict:
        if not isinstance(proposal, dict) or set(proposal) != {"run_id", "request_id", "operation"}:
            return self._deny("invalid action envelope")
        if proposal["run_id"] != self.ident:
            return self._deny("cross-run request")
        op, request = proposal["operation"], proposal["request_id"]
        if not isinstance(op, str) or op not in OPERATIONS:
            return self._deny("unknown operation")
        try:
            store.run_id(request)
        except ValueError:
            return self._deny("invalid request identity")
        if time.monotonic() > self.deadline or self.remaining <= 0:
            return self._deny("action budget exhausted")
        started = time.monotonic()
        with store.connect() as db:
            state = db.execute("SELECT * FROM fl_runs WHERE id=%s FOR UPDATE", (self.ident,)).fetchone()
            if not state or state["cancelled"]:
                return self._deny("run cancelled or unavailable")
            previous = db.execute("SELECT receipt FROM fl_actions WHERE run=%s AND request_id=%s", (self.ident, request)).fetchone()
            if previous:
                if previous["receipt"]["operation"] != op:
                    return self._deny("request identity reused for different operation")
                if previous["receipt"]["status"] == "complete":
                    return {**previous["receipt"], "replayed": True}
            self.remaining -= 1
            if op == "rebuild_projection":
                raw = db.execute("SELECT payload FROM fl_deliveries WHERE run=%s", (self.ident,)).fetchall()
                if any(contract_error(row["payload"]) for row in raw):
                    return self._deny("incompatible input requires explicit quarantine")
            if not previous and op in {"rebuild_projection", "quarantine_and_replay"}:
                # Reset and select the safe worker within a single transaction.
                for table in ("entries", "ack", "quarantine", "effects"):
                    db.execute(f"DELETE FROM fl_{table} WHERE run=%s", (self.ident,))
                db.execute("UPDATE fl_runs SET mode='safe',revision=revision+1 WHERE id=%s", (self.ident,))
            receipt = {"operation": op, "accepted": True, "request_id": request, "status": "pending"}
            if not previous:
                db.execute("INSERT INTO fl_actions VALUES (%s,%s,%s)", (self.ident, request, Jsonb(receipt)))
        if op in {"restart_worker", "rebuild_projection", "quarantine_and_replay"}:
            process(self.ident, deadline=self.deadline)
        receipt.update({"status": "complete", "elapsed_ms": round((time.monotonic()-started)*1000, 3)})
        with store.connect() as db:
            db.execute("UPDATE fl_actions SET receipt=%s WHERE run=%s AND request_id=%s", (Jsonb(receipt), self.ident, request))
        if op == "inspect":
            receipt["observation"] = observe(self.ident)
        self.receipts.append(receipt)
        return receipt

    def action(self, operation: str) -> dict:
        return self.execute({"run_id": self.ident, "request_id": uuid.uuid4().hex, "operation": operation})

    def _deny(self, reason: str) -> dict:
        receipt = {"accepted": False, "status": "denied", "reason": reason}
        self.receipts.append(receipt)
        return receipt
