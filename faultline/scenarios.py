"""Synthetic workload and evaluator-only truth. Never supplied to the investigator."""
from __future__ import annotations
import copy
import random

FAMILIES = ("duplicate", "interruption", "contract")
TITLES = {"duplicate": "The revenue mirage", "interruption": "The half-written order", "contract": "The unit mismatch"}


def make(family: str, seed: int, size: int = 12) -> dict:
    if family not in FAMILIES or not 4 <= size <= 2000:
        raise ValueError("unknown family or unsupported size")
    rng = random.Random(seed)
    events = []
    for i in range(size):
        # Reused IDs across tenants and distinct events on one order are intentional.
        events.append({"tenant": "cedar" if i % 2 else "harbor", "event_id": f"evt-{i//2:04d}",
          "order_id": f"ord-{i//4:04d}", "amount_minor": rng.randint(8, 350)*100,
          "currency": "USD", "unit": "cents", "kind": "sale"})
    events[-1] = {**events[-1], "amount_minor": -rng.randint(1, 7)*100, "kind": "refund"}
    truth = {"expected_events": copy.deepcopy(events), "quarantine_sequences": []}
    deliveries = copy.deepcopy(events)
    if family == "duplicate":
        for _ in range(2 + seed % 4):
            deliveries.insert(rng.randrange(len(deliveries)+1), copy.deepcopy(rng.choice(events)))
    if family == "contract":
        bad = {**events[1], "event_id": "unit-conflict", "unit": "dollars", "amount_minor": 25000 + seed % 100}
        position = rng.randrange(len(deliveries)+1)
        deliveries.insert(position, bad)
        truth["quarantine_sequences"] = [position+1]
    return {"family": family, "seed": seed, "title": TITLES[family], "deliveries": deliveries,
            "truth": truth, "crash_after": 2 + seed % max(2, size-2)}
