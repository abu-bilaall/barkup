# barkup 0.2.0 — Live Test Findings

Checks: 49 (PASS 47, FAIL 2)
Verified prior fixes: 6

## Verified fixes (from 0.1.0 live findings)

- [VERIFIED F1] init now writes a blank/safe template (sources=[], destination="")
- [VERIFIED F2] dotfiles excluded by default
- [VERIFIED F4] dry_run is preview-only (no copy, no prompt)
- [VERIFIED F5] --yes is a no-op in dry_run mode (safety net preserved)
- [VERIFIED F6] verify hashes the BACKUP copy and exits non-zero on problems
- [VERIFIED F7] restore onto existing original requires --yes (overwrite guard)

## New findings

### [HIGH] `prune` reports success but removes nothing
prune --yes prints 'Removed N orphan record(s).' (and with --delete-backups also 'Backup files were also deleted.') but the DB rows and on-disk backup files are unchanged. Verified: 2 rows before, 2 rows after `prune --yes`; all backup files remain after `prune --yes --delete-backups`. The orphan-cleanup feature (F3) is non-functional in 0.2.0.

### [MED] Symlinked directories are now recursed (over-backup / loop risk)
0.1.0 did not traverse symlinked directories; 0.2.0 follows them. A symlink into a large or external tree is now backed up in full, and a cyclic symlink could cause unbounded traversal (not tested live to avoid a hang). Observed: a symlink to a subdir caused its contents to be backed up. Recommend guarding symlinked directories (skip or warn) as was the 0.1.0 behavior.

### [INFO] Per-file copy error handling untested (root bypasses permissions)
run_local_barkup wraps each file copy in try/except and continues; as root in this sandbox chmod 000 / unreadable files are still readable, so the failure path could not be exercised live.
