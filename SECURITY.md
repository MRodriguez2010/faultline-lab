# Local lab trust boundaries

FAULTLINE contains synthetic business data and intentionally vulnerable worker
behavior. The default database is loopback-only, uses local trust authentication,
and is disposable. It is unsuitable as a public database or production payment
system. The HTTP listener also binds only to loopback and rejects browser Origin
headers and non-JSON writes. It has bounded request and event sizes.

The model has no SQL, shell, file, network-destination, or arbitrary resource
arguments. Its response is validated independently of constrained generation.
The action broker owns the run identifier, permitted actions, request identity,
time and action budgets. It records pending/completed mutations. Cancellation is
cooperative between records, with bounded SQL waits, not instantaneous interruption
of a committed transaction.

Tests cover unknown operations and fields, cross-run attempts, invalid identifiers,
expired budgets, cancellation, duplicate request identities, and malformed input.
These are bounded negative tests, not a comprehensive security audit or a claim
that prompt injection has been solved. A model can choose a bad allowed action;
the independent evaluator must still reject an incorrect result.

The host/harness is trusted. Another local process with access to PostgreSQL can
alter data. Artifact hashes provide identity and tamper detection when compared
with a trusted copy; they are not remote attestation that a benchmark happened.
Reproduction on another trusted checkout is stronger evidence.

Only original code, documentation, lockfiles, and synthetic fixture definitions
belong in this public source release. Runtime database state, local connection
configuration, model weights, personal files, and raw operational histories do not.

Report suspected vulnerabilities using [private reporting](https://github.com/MRodriguez2010/faultline-lab/security/advisories/new). Only the latest main branch is maintained on a best-effort basis. Do not point the vulnerable
worker or test harness at employer/client systems or data.
