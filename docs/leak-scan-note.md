# Leak-scan false-positive record

Reviewed: 2026-10-28

An earlier generic private-network scan flagged three lines in `uv.lock`
because dotted NVIDIA package versions resemble addresses in the `10/8` range.

Manual verification:

- the matches are package versions and wheel SHA-256 metadata;
- no private IP address, hostname, token or credential is present;
- the repository leak scanner currently reports zero findings for both the
  source workspace and generated public copy.

This record applies only to the reviewed `uv.lock`. Re-run the scan after any
lock-file change; do not treat the exception as blanket permission to skip
checks.
