# barkup 0.1.0 — Live Test: how to reproduce

All checks were run against the **published PyPI wheel `barkup==0.1.0`**
(installed into an isolated venv, driven via the real CLI against real
temp filesystems). `Cloud/Google Drive` is excluded (it is a `pass` stub
upstream, per the project owner).

## Run the full suite (one command)

From the repo root:

```bash
python3 live_test/harness.py
```

The harness auto-creates a venv via `uv` and `pip install barkup==0.1.0`
if needed (overridable with `LIVE_VENV=/path/to/.venv` or
`BARKUP=/path/to/barkup`). Scenario scratch goes to `/tmp/barkup_live`
(overridable with `LIVE_ROOT=...`). Every run sets `XDG_CONFIG_HOME`
to a per-scenario temp dir, so your `~/.config` is never touched.

Expected output ends with:

```
=== SUMMARY ===
checks: 82  PASS: 82  FAIL: 0
```

Detailed findings are written to `live_test/FINDINGS.md` (generated next
to this file) and echoed as `[FINDING:...]` lines during the run.

## Manual repros for the HIGH findings

These let you confirm each bug by hand with the published package.

### H1 — `verify` checks the SOURCE, not the backup copy
```bash
export XDG=/tmp/vx && rm -rf $XDG && mkdir -p $XDG/barkup
mkdir -p /tmp/vsrc && echo aaa >/tmp/vsrc/a.txt && echo bbb >/tmp/vsrc/b.txt
cat >/tmp/vcfg.toml <<'EOF'
[general]
profile_name = "v"
sources = ["/tmp/vsrc"]
[local]
destination = "/tmp/vdest"
EOF
barkup --config /tmp/vcfg.toml run
# delete the BACKUP copy, leave the source intact:
BACKUP=$(python3 - <<'PY'
import sqlite3, os
p=os.path.join(os.environ["XDG"],"barkup","state.db")
c=sqlite3.connect(p); print(c.execute(
  "select backup_path from backups where original_path like '%a.txt'").fetchone()[0])
PY
)
rm "$BACKUP"
barkup --config /tmp/vcfg.toml verify --name v
# -> prints "OK: 2", exit 0. BUG: should report the missing backup.
```

### H2 — `dry_run` copies when confirmed
```bash
export XDG=/tmp/dx && rm -rf $XDG && mkdir -p $XDG/barkup
mkdir -p /tmp/dsrc && echo hi >/tmp/dsrc/a.txt
cat >/tmp/dcfg.toml <<'EOF'
[general]
profile_name = "d"
dry_run = true
sources = ["/tmp/dsrc"]
[local]
destination = "/tmp/ddest"
EOF
# Answer 'y' to the prompt:
echo y | barkup --config /tmp/dcfg.toml run
ls /tmp/ddest            # -> /tmp/ddest/dsrc/a.txt EXISTS (was copied)
# config.example.toml says dry_run = "(no actual copying)". BUG.
```

### H3 — `barkup run --yes` forces a copy in dry-run mode
```bash
# reuse the dry_run config from H2, then:
barkup --config /tmp/dcfg.toml run --yes
ls /tmp/ddest            # copied again, no prompt.
# README's cron guidance is `barkup run --yes`; in normal mode there is
# no prompt so --yes is a no-op, but with dry_run=true it SKIPS the
# prompt and performs the real backup -- defeating the safety net.
```

### H4 — default `init` config backs up your whole home
```bash
export XDG=/tmp/ix && rm -rf $XDG && mkdir -p $XDG
barkup init
grep -E 'sources|Backups' $XDG/barkup/config.toml
# -> sources = ["/home/..."]  and  destination = "/home/.../Backups"
# The backup dir sits INSIDE the source tree, so a 2nd run re-backs-up
# the growing ~/Backups (self-referential). Dotfiles (.ssh, .env) are
# included too.
```

## What passed (no bug)
install/CLI surface, config precedence (system→user→cwd→`--config`),
full incremental backup (new/modified/unchanged/deleted), exclude patterns,
compression sidecars + already-compressed passthrough, `list`/`status`/`profiles`,
`restore` (single/`--all`/compressed, all error exits), symlink handling,
empty-source, and >64 KB chunked hashing (matches `sha256sum`).
