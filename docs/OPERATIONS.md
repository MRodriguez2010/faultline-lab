# Operations and recovery

`scripts/lab-db.py start` records the exact container ID, volume, ownership label,
image digest, and loopback connection in ignored `.runtime/database.json`.
`status` checks that exact resource. `stop` verifies both ownership labels before
removing this lab's disposable resources. It does not list or stop unrelated apps.

If startup fails, the script removes resources it just created. If the state file
exists, starting again refuses to create a second database. Preserve exported
artifacts before stopping. A missing/stale state file needs manual inspection of
the recorded task-owned resource; never substitute a broadly matching container.

Every CLI incident owns a list of run IDs. Its `finally` block deletes only those
runs. The HTTP child process is terminated and reaped. Worker subprocesses have a
45-second harness timeout; real fault injection is exit code 75. An unexpected
worker error is a failed run. The safe implementation never deliberately performs
the legacy split commit. PostgreSQL remains running between incidents until stop.

Local model requests use the existing Ollama service without changing its config,
downloading weights, or adding cloud fallback. They use a five-minute keep-alive;
the service may release the model afterward. Do not forcibly unload a model that
another user or application is using. Model-call failures are recorded.

## Clean reproduction

Use a new checkout of the recorded source commit, Python 3.12, the pinned
requirements, and the pinned PostgreSQL image. Start a fresh database, run the
tests, then regenerate at least one example per family. Compare fixture hashes,
expected records, invariant outcomes, and branch equality. Timing, UUIDs, and model
language need not match byte-for-byte. The source state should be clean.

## Sharing results

Record the source commit before running an evaluation. Review generated artifacts
before sharing them; include the protocol hash, source revision, environment,
model identity (if used), and failed attempts alongside successful outcomes.
Never substitute an earlier run's model scores for results from a changed build.
Only synthetic data belongs in shared examples.
