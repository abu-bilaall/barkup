# barkup 0.1.0 — Live Test Findings

Checks: 82 (PASS 81, FAIL 1)

## Findings

### [HIGH] Default `init` config backs up ENTIRE home into ~/Backups
init_config sets sources=[$HOME], destination=$HOME/Backups. The backup dir sits inside the source tree, so a second run would try to re-back-up the growing ~/Backups tree (self-referential, unbounded growth). Because dotfiles are included, it also copies .ssh/.env and other secret dotfiles.

### [INFO] Dotfiles ARE backed up (rglob('*') includes them in this build)
.hidden.txt and .env were included in backups. Only '.git' is excluded, and that is via the exclude PATTERN, not by rglob. Implication: a home-wide config also copies .ssh/.env secret dotfiles (see default-config finding).

### [MED] Deleted source leaves an orphan DB row
After deleting a source file, its state row stays in the DB; `verify` later flags it 'missing' but `run` never prunes it.

### [HIGH] dry_run copies files when confirmed (contradicts 'no actual copying')
config.example.toml documents dry_run as '(no actual copying)' and spec.md says 'Skips actual backup if user declines'. But run_barkup proceeds to copy when the prompt returns 'y'. So dry_run is not a true dry run; confirming performs the backup.

### [HIGH] --yes in dry_run mode forces a real copy
README/cron guidance is to run `barkup run --yes`. In normal mode (dry_run=false) there is NO prompt, so --yes is a no-op. But if a user enables dry_run=true as a safety net and automates with --yes, --yes skips the prompt and performs the real backup, defeating the safety.

### [HIGH] `verify` checks the SOURCE, not the backup copy
spec.md: 'Check all backed-up files still exist ... Report any corrupted or missing files.' But verify_backup re-hashes the original source file. Deleting/corrupting the backup copy while the source is intact makes verify report OK/exit0, so it cannot detect a lost or corrupted backup.

### [MED] `restore <path>` with no --to overwrites the live original
restore_file with destination=None copies the backup onto the original path, destroying any un-backed-up local changes. No --dry-run / confirmation.

### [INFO] Per-file copy error handling untested (root bypasses permissions)
run_local_barkup wraps each file copy in try/except and continues; as root in this sandbox chmod 000 / unreadable files are still readable, so the failure path could not be exercised live.
