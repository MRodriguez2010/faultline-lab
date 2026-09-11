# FAULTLINE

**Break the system. Prove the recovery.**

A local PostgreSQL and Python lab that makes business-data failures inspectable.
Inject duplicate delivery, terminate a worker between write and acknowledgement,
or introduce an incompatible monetary unit. Branch the captured incident state,
compare a restart, an explicit runbook, and a bounded local-model decision, then
reconcile every resulting record with an independent workload manifest.

[Verification workflow](https://github.com/MRodriguez2010/faultline-lab/actions/workflows/ci.yml) · [Local verification](VERIFICATION.md)

This repository contains the executable lab. It uses synthetic data throughout.
The portfolio replay at [miguel.systems](https://miguel.systems/work/faultline) is a
recorded demonstration; local runs below produce fresh evidence.

## Run locally

Requires Python 3.12+, Docker Engine, and enough room for the pinned PostgreSQL
image. The model comparison additionally requires Ollama on loopback with
`qwen3:4b` already available; there is no API billing or cloud fallback.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps -e .
python3 scripts/lab-db.py start
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m faultline.cli run --output artifacts/demo --seeds 17
# Optional real local inference, requires the named installed model:
.venv/bin/python -m faultline.cli run --output artifacts/model-demo --seeds 17 --model qwen3:4b
python3 scripts/lab-db.py stop
```

`start` creates one labelled container and disposable disk volume, exposing
PostgreSQL on an ephemeral loopback port. Synthetic lab data uses local trust
authentication. `stop` verifies both ownership labels and removes only those
resources. Do not deploy this configuration as a public database. Exported
artifacts remain after stopping. `.runtime/` and `artifacts/` stay out of Git.

For a persistent foreground ingestion endpoint, run
`.venv/bin/python -m faultline.cli serve`; it prints its selected loopback port.
The CLI normally starts this in a child process and closes it after each run.

## What is real

- HTTP ingestion executes in a separate Python process.
- Inputs, ledger entries, acknowledgements, quarantine, and receipts persist in
  PostgreSQL transactions on a Docker-managed disk volume.
- Worker fault injection invokes `os._exit(75)` in a dedicated child process.
- Recovery branches are real database copies, with equivalent initial-state
  hashes and a check that the source remains unchanged.
- The evaluator compares complete record identities and amounts, not only totals.
- Model results come from an actual local Ollama request, including failures.

## What is deliberately bounded

This is a synthetic, single-host lab, not a production payments service or a
general autonomous SRE. The model selects one operation from a small action
catalog based on observed facts. It cannot write SQL or execute shell commands.
It receives neither injected-fault labels nor the evaluator's expected records.
Evidence identifiers are checked for existence; the semantic quality of every
sentence is not scored automatically. No hidden model reasoning is displayed.

The intentionally unsafe `legacy` worker demonstrates the bugs. The corrected
worker serializes a run, validates the envelope, deduplicates on
`(tenant,event_id)`, and commits the business effect with its acknowledgement.
This proves the evaluated local behavior, not global exactly-once delivery.

## Evidence and navigation

- [Architecture and tradeoffs](docs/ARCHITECTURE.md)
- [Evaluation method](docs/EVALUATION.md) and [frozen protocol](evaluation/protocol.json)
- [Security and boundaries](SECURITY.md)
- [Operations and reproduction](docs/OPERATIONS.md)
- [Authorship](AUTHORS.md) and [contributing](CONTRIBUTING.md)

## License and support

MIT. Python and PostgreSQL dependencies retain their own licenses. No model
weights are distributed. Linux is the validated development environment; the
optional Ollama branch needs a separately installed model. See [SECURITY.md](SECURITY.md)
for trust boundaries and reporting.
