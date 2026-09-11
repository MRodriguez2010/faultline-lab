"""Oracle from the workload manifest; imports neither repair nor validation logic."""
from collections import Counter


def evaluate(snapshot: dict, truth: dict) -> dict:
    expected = {(e["tenant"], e["event_id"]): e for e in truth["expected_events"]}
    entries = snapshot["entries"]
    counts = Counter((e["tenant"], e["event_id"]) for e in entries)
    missing = [list(key) for key in expected if counts[key] == 0]
    duplicates = [{"tenant": key[0], "event_id": key[1], "count": count} for key, count in counts.items() if count > 1]
    unexpected = [list(key) for key in counts if key not in expected]
    wrong_values = [e for e in entries if (e["tenant"], e["event_id"]) in expected and any(
        e[field] != expected[(e["tenant"], e["event_id"])][field] for field in ("order_id", "amount_minor"))]
    quarantine = {q["seq"] for q in snapshot["quarantine"]}
    expected_quarantine = set(truth["quarantine_sequences"])
    pending = len(snapshot["deliveries"]) - len(snapshot["ack"])
    expected_total = sum(e["amount_minor"] for e in expected.values())
    actual_total = sum(e["amount_minor"] for e in entries)
    checks = [
        {"id": "unique-effects", "label": "One effect per business event", "passed": not duplicates},
        {"id": "complete", "label": "Every valid event is present", "passed": not missing and pending == 0},
        {"id": "exact-records", "label": "Amounts and identities reconcile", "passed": not unexpected and not wrong_values and expected_total == actual_total},
        {"id": "quarantine", "label": "Incompatible records remain reviewable", "passed": quarantine == expected_quarantine},
    ]
    return {"passed": all(c["passed"] for c in checks), "checks": checks,
            "expected_minor": expected_total, "actual_minor": actual_total,
            "difference_minor": actual_total - expected_total, "missing": missing,
            "duplicates": duplicates, "unexpected": unexpected, "wrong_values": wrong_values,
            "quarantined": len(quarantine), "pending": pending}
