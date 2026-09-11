"""Execute isolated incidents, retain state, branch recovery, export honest evidence."""
from __future__ import annotations
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import platform
import select
import subprocess
import sys
import time
import urllib.request

from . import store
from .broker import Broker, observe
from .evaluator import evaluate
from .investigator import baseline, local_model
from .scenarios import make

ROOT = Path(__file__).resolve().parents[1]


def configure():
    if not os.environ.get("FAULTLINE_DSN"):
        state = json.loads((ROOT / ".runtime/database.json").read_text())
        os.environ["FAULTLINE_DSN"] = state["dsn"]


@contextlib.contextmanager
def ingestion_service():
    child = subprocess.Popen([sys.executable, "-m", "faultline.cli", "serve"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if not select.select([child.stdout], [], [], 15)[0]:
            raise RuntimeError("ingestion service startup timeout")
        line = child.stdout.readline()
        if not line:
            raise RuntimeError("ingestion service exited before readiness")
        port = json.loads(line)["port"]
        yield f"http://127.0.0.1:{port}"
    finally:
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()


def request(base: str, path: str, data=None):
    req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read())


def worker(ident, crash="none", crash_after=1):
    start = time.monotonic()
    result = subprocess.run([sys.executable, "-m", "faultline.worker", ident, "--crash", crash, "--crash-after", str(crash_after)], capture_output=True, text=True, timeout=45)
    if result.returncode not in (0, 75):
        raise RuntimeError("worker failed: " + result.stderr[-1000:])
    return {"exit_code": result.returncode, "fault_injected": result.returncode == 75,
            "elapsed_ms": round((time.monotonic()-start)*1000,3)}


def frame(ident, truth, title):
    snap = store.snapshot(ident)
    return {"title": title, "state_hash": store.digest(snap), "snapshot": snap, "verification": evaluate(snap, truth)}


def execute(family: str, seed: int, *, model: str | None = None, attempt: int = 0, size: int = 12) -> dict:
    scenario = make(family, seed, size)
    owned = []
    start = time.monotonic()
    result = {"schema_version": 1, "family": family, "seed": seed, "attempt": attempt,
      "title": scenario["title"], "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
      "execution": "local-postgresql-and-python-processes", "fixture_hash": store.digest(scenario),
      "input_hash": store.digest(scenario["deliveries"]), "truth": scenario["truth"], "branches": {}}
    try:
        with ingestion_service() as base:
            ident = request(base, "/runs", {})["run_id"]
            owned.append(ident)
            request(base, f"/runs/{ident}/events", {"events": scenario["deliveries"]})
            result["received"] = frame(ident, scenario["truth"], "Inputs received")
            result["worker"] = worker(ident, "after_write" if family == "interruption" else "none", scenario["crash_after"])
            result["incident"] = frame(ident, scenario["truth"], "Incident captured")
            result["health"] = request(base, "/health")
            observation = request(base, f"/runs/{ident}/observations")
            result["observation"] = observation
            source_hash = result["incident"]["state_hash"]
            # The tempting restart and the runbook both branch from the same captured state.
            for name, decision in [("restart", {"operation": "restart_worker", "summary": "Try restarting the current worker.", "evidence": ["OBS-1"]}),
                                   ("runbook", baseline(observation))]:
                child, initial_hash = store.branch(ident)
                owned.append(child)
                if initial_hash != source_hash:
                    raise AssertionError("branch did not start from the captured incident state")
                broker = Broker(child)
                receipt = broker.action(decision["operation"])
                result["branches"][name] = {"initial_hash": initial_hash, "decision": decision, "receipts": broker.receipts,
                    "execution_ms": receipt.get("elapsed_ms", 0), "result": frame(child, scenario["truth"], "Recovery checked")}
            if model:
                child, initial_hash = store.branch(ident)
                owned.append(child)
                if initial_hash != source_hash:
                    raise AssertionError("agent branch snapshot mismatch")
                agent = {"initial_hash": initial_hash}
                inference_started = time.monotonic()
                try:
                    inference = local_model(observation, model=model, seed=attempt)
                    agent.update(inference)
                    broker = Broker(child)
                    receipt = broker.action(inference["decision"]["operation"])
                    agent["receipts"] = broker.receipts
                    agent["execution_ms"] = receipt.get("elapsed_ms", 0)
                except Exception as exc:
                    agent["error"] = type(exc).__name__ + ": " + str(exc)[:250]
                    agent["elapsed_ms"] = round((time.monotonic()-inference_started)*1000,3)
                    agent["receipts"] = []
                agent["result"] = frame(child, scenario["truth"], "Agent proposal checked")
                result["branches"]["agent"] = agent
            result["source_unchanged"] = store.digest(store.snapshot(ident)) == source_hash
        result["elapsed_ms"] = round((time.monotonic()-start)*1000,3)
        return result
    finally:
        for ident in reversed(owned):
            store.delete(ident)


def provenance():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip())
    except subprocess.CalledProcessError:
        commit, dirty = "uncommitted", True
    with store.connect() as db:
        pg = db.execute("SHOW server_version").fetchone()["server_version"]
    return {"source_commit": commit, "source_dirty": dirty, "python": platform.python_version(),
            "postgresql": pg, "system": platform.system(), "machine": platform.machine()}


def export(output: Path, seeds: list[int], *, model: str | None, attempts: int = 1, size: int = 12):
    from .scenarios import FAMILIES
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "created_at": dt.datetime.now(dt.UTC).isoformat(),
      "environment": provenance(), "model": model, "seeds": seeds, "attempts": attempts,
      "size": size, "runs": [], "failures": [], "protocol_hash": store.digest(json.loads((ROOT / "evaluation/protocol.json").read_text()))}
    if model:
        tags = request("http://127.0.0.1:11434", "/api/tags")
        manifest["model_digest"] = next((m["digest"] for m in tags["models"] if m["name"] == model), None)
    for family in FAMILIES:
        for seed in seeds:
            for attempt in range(attempts):
                name = f"{family}-{seed}-{attempt}.json"
                try:
                    run = execute(family, seed, model=model, attempt=attempt, size=size)
                    run["environment"] = manifest["environment"]
                    raw = json.dumps(run, indent=2)+"\n"
                    (output / name).write_text(raw)
                    manifest["runs"].append({"file": name, "sha256": __import__("hashlib").sha256(raw.encode()).hexdigest()})
                    print(json.dumps({"file": name, "runbook": run["branches"]["runbook"]["result"]["verification"]["passed"],
                      "agent": run["branches"].get("agent", {}).get("result", {}).get("verification", {}).get("passed")}), flush=True)
                except Exception as exc:
                    manifest["failures"].append({"file": name, "error": type(exc).__name__+": "+str(exc)[:300]})
                    print(json.dumps({"file": name, "error": type(exc).__name__}), flush=True)
                (output / "manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest
