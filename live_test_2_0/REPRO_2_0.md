# barkup 0.2.0 — Live Test: how to reproduce

All checks were run against the **published PyPI wheel `barkup==0.2.0`**
(installed into an isolated venv, driven via the real CLI against real
temp filesystems). `Cloud/Google Drive` is excluded (it is a `pass` stub
upstream, per the project owner).

## Run the full suite (one command)

From the repo root:

```bash
python3 live_test_2_0/harness.py
```

The harness auto-creates a venv via `uv` and `pip install barkup==0.2.0`
if needed (overridable with `LIVE_VENV=/path/to/.venv` or
`BARKUP=/path/to/barkup`). Scenario scratch goes to `/tmp/barkup_020`
(overridable with `LIVE_ROOT=...`). Every run sets `XDG_CONFIG_HOME`
to a per-scenario temp dir, so your `~/.config` is never touched.

Expected output ends with:

```
=== SUMMARY ===
checks: 49  PASS: 47  FAIL: 2
verified fixes: 6
new findings: 3
```

The 2 failures are both the `prune` bug (below); everything else passes,
including all 6 prior 0.1.0 fixes. Detailed findings are written to
`live_test_2_0/FINDINGS_2_0.md`.

## Manual repros for the NEW findings

### [HIGH] `prune` reports success but removes nothing
```bash
export XDG=/tmp/prx && rm -rf $XDG && mkdir -p $XDG/barkup
mkdir -p /tmp/psrc && echo a >/tmp/psrc/a.txt && echo b >/tmp/psrc/b.txt
cat >/tmp/pcfg.toml <<'EOF'
[general]
profile_name = "pr"
dry_run = false
sources = ["/tmp/psrc"]
[local]
destination = "/tmp/pdst"
EOF
barkup --config /tmp/pcfg.toml run
rm /tmp/psrc/b.txt                       # delete a source -> orphan
barkup --config /tmp/pcfg.toml prune --yes
# -> prints "Removed 1 orphan record(s)."  BUT:
python3 -c "import sqlite3;c=sqlite3.connect('$XDG/barkup/state.db');print('rows=',c.execute('select count(*) from backups').fetchone()[0])"
# -> still 2 (the row was NOT removed)
# with --delete-backups, it also claims "Backup files were also deleted."
# but /tmp/pdst/psrc/{a,b}.txt are still on disk.
```

### [MED] Symlinked directories are now recursed
```bash
export XDG=/tmp/sx && rm -rf $XDG && mkdir -p $XDG/barkup
mkdir -p /tmp/ssrc/sub && echo inner >/tmp/ssrc/sub/inner.txt
ln -s /tmp/ssrc/sub /tmp/ssrc/linkdir    # symlinked directory
cat >/tmp/scfg.toml <<'EOF'
[general]
profile_name = "s"
dry_run = false
sources = ["/tmp/ssrc"]
[local]
destination = "/tmp/sdst"
EOF
barkup --config /tmp/scfg.toml run
# -> inner.txt is backed up via the linkdir symlink (0.1.0 did NOT do this).
# A symlink into a large/external tree would now be backed up in full, and a
# cyclic symlink could cause unbounded traversal.
```

## Prior (0.1.0) findings — now VERIFIED FIXED

| Label | Fix | How the harness proves it |
| --- | --- | --- |
| F1 | `init` blank/safe template | `init` writes `sources = []`, `destination = ""`; no whole-home path. `run` with the blank config fails validation, copies nothing. |
| F2 | dotfiles excluded by default | `.hidden` / `.env` are NOT backed up. |
| F4 | `dry_run` preview-only | `dry_run=true` → no copy, dest absent, "dry run" in output. |
| F5 | `--yes` no-op in dry mode | `run --yes` under `dry_run=true` still copies nothing. |
| F6 | `verify` hashes the backup copy | deleting/corrupting the backup copy → `verify` reports `Missing:`/`Mismatched:` and exits `rc=1`. |
| F7 | `restore` overwrite guard | `restore <path>` without `--yes` → `rc=1`, live original untouched; `--yes` overwrites; `--to` writes to the given path. |

## What passed (no bug)
install/CLI surface (8 commands; `--config` group-level), config precedence,
full incremental backup (new/modified/unchanged/deleted), exclude patterns,
compression sidecar + already-compressed passthrough + restore-from-compressed,
`list`/`status`/`profiles`, symlinked **file** followed, empty source, and
>64 KB chunked hashing (matches `sha256sum`).
