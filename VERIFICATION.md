# Public release verification

Verified on September 11, 2026 from a fresh Git checkout on Linux.
Runtime files, dependencies, caches, and generated reports are excluded from Git.
The repository includes an executable GitHub Actions workflow; local verification
below is distinct from the status of any hosted workflow run.

- Python 3.12.3; pinned psycopg 3.3.5 and PostgreSQL image.
- All 16 backend tests passed against a newly created PostgreSQL container.
- Duplicate delivery, interrupted write, and unit-contract incidents at seed 17
  all passed the deterministic runbook's independent recovery checks.
- Test-owned containers and disposable volumes were removed afterward.
- No local-model evaluation was rerun for this source release; optional model
  results must be generated and reported separately.
- The pinned Python dependency audit reported no known vulnerabilities.

The public Git history was scanned with Gitleaks 8.30.1 with no findings. The
publication review also checked tracked files for private host paths, credentials,
operational data, and broken local documentation links. These checks do not
constitute an exhaustive security assessment. Reproduce the commands in README.md
and report any failure with the source revision and a synthetic example.
