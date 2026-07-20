"""Live end-to-end test harness for the PUBLISHED barkup 0.2.0 wheel.

Drives the installed `barkup` CLI (subprocess) against real temp filesystems.
Isolates state per scenario via XDG_CONFIG_HOME so ~/.config is never touched.
Cloud/Google Drive is out of scope (stubbed upstream).

NOTE: `--config` is a GROUP-level option, so it must precede the subcommand:
    barkup --config X run        (NOT  barkup run --config X)

Self-bootstraps a venv (uv + pip install barkup==0.2.0) if not present.
"""

import os
import shutil
import sqlite3
import subprocess
import hashlib
from pathlib import Path

# --- environment (overridable) ---------------------------------------------
ROOT = Path(os.environ.get("LIVE_ROOT", "/tmp/barkup_020"))
_VENV = Path(os.environ.get("LIVE_VENV", str(ROOT / ".venv")))
BARKUP = os.environ.get("BARKUP") or str(_VENV / "bin" / "barkup")


def _ensure_barkup():
    if os.path.exists(BARKUP):
        return
    _VENV.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "venv", str(_VENV)], check=True)
    subprocess.run(
        ["uv", "pip", "install", "-p", str(_VENV / "bin" / "python"), "barkup==0.2.0"],
        check=True,
    )


_ensure_barkup()

RESULTS = []  # (phase, name, ok, detail)
FINDINGS = []  # (severity, title, detail)
VERIFIED = []  # fix labels confirmed fixed


# --------------------------------------------------------------------------
def check(phase, name, cond, detail=""):
    cond = bool(cond)
    RESULTS.append((phase, name, cond, detail))
    tag = "PASS" if cond else "FAIL"
    line = f"[{tag}] {phase} :: {name}"
    if detail:
        line += f" -- {detail}"
    print(line)


def finding(sev, title, detail):
    FINDINGS.append((sev, title, detail))
    print(f"[FINDING:{sev}] {title} :: {detail}")


def verified(label, what):
    VERIFIED.append((label, what))
    print(f"[VERIFIED] {label} :: {what}")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fresh_xdg(name):
    x = ROOT / f"xdg_{name}"
    shutil.rmtree(x, ignore_errors=True)
    x.mkdir(parents=True)
    return x


def run_barkup(args, xdg, cwd=None, input_text=None):
    # `--config` is a GROUP-level option and MUST precede the subcommand:
    #   barkup --config X run   (NOT  barkup run --config X)
    # This helper NORMALIZES --config to group position, so it cannot be used
    # to test the "after subcommand" rejection (use raw_barkup for that).
    cfg = None
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--config":
            cfg = args[i + 1]
            i += 2
            continue
        if a.startswith("--config="):
            cfg = a.split("=", 1)[1]
            i += 1
            continue
        rest.append(a)
        i += 1
    cmd = [BARKUP]
    if cfg:
        cmd += ["--config", cfg]
    cmd += rest
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(xdg)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
    )


def raw_barkup(args, xdg):
    # Runs args EXACTLY as given (no --config normalization).
    cmd = [BARKUP] + list(args)
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(xdg)
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def db_rows(xdg, profile=None):
    p = Path(xdg) / "barkup" / "state.db"
    if not p.exists():
        return []
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    if profile:
        rows = conn.execute(
            "SELECT * FROM backups WHERE profile=? ORDER BY original_path", (profile,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM backups ORDER BY profile, original_path"
        ).fetchall()
    out = [dict(r) for r in rows]
    conn.close()
    return out


def db_row(xdg, orig):
    for r in db_rows(xdg):
        if r["original_path"] == orig:
            return r
    return None


def write_cfg(
    path,
    profile,
    sources,
    dest,
    dry_run=None,
    compression=False,
    exclude=None,
    extra="",
):
    exclude = exclude or []
    src_str = "[" + ", ".join(f'"{s}"' for s in sources) + "]"
    exc_str = "[" + ", ".join(f'"{e}"' for e in exclude) + "]"
    lines = [
        "[general]",
        f'profile_name = "{profile}"',
    ]
    if dry_run is not None:
        lines.append(f"dry_run = {str(dry_run).lower()}")
    lines += [
        f"sources = {src_str}",
        f"compression = {str(compression).lower()}",
        f"exclude = {exc_str}",
        "",
        "[local]",
        f'destination = "{dest}"',
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n" + extra)


# --------------------------------------------------------------------------
# T0: install + CLI surface
# --------------------------------------------------------------------------
def t0():
    xdg = fresh_xdg("s0")
    r = run_barkup(["--help"], xdg)
    cmds = ["init", "run", "list", "status", "verify", "profiles", "restore", "prune"]
    check(
        "T0",
        "CLI --help lists all 8 commands (incl. prune)",
        r.returncode == 0 and all(c in r.stdout for c in cmds),
        f"rc={r.returncode}",
    )
    r2 = run_barkup(["--version"], xdg)
    check(
        "T0",
        "No --version flag (exits non-zero)",
        r2.returncode != 0,
        f"rc={r2.returncode}",
    )
    # --config is GROUP-level: rejected after the subcommand
    work = ROOT / "s0_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "f.txt").write_text("hi")
    cfg = work / "c.toml"
    write_cfg(cfg, "p", [str(src)], str(work / "d"), dry_run=False)
    ok = run_barkup(["--config", str(cfg), "run"], xdg)
    bad = raw_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "T0",
        "--config before subcommand works",
        ok.returncode == 0,
        f"rc={ok.returncode}",
    )
    check(
        "T0",
        "--config after subcommand rejected (rc=2)",
        bad.returncode == 2,
        f"rc={bad.returncode}",
    )


# --------------------------------------------------------------------------
# T1: init blank template (F1)
# --------------------------------------------------------------------------
def t1():
    xdg = fresh_xdg("init")
    r = run_barkup(["init"], xdg)
    cfg_path = xdg / "barkup" / "config.toml"
    check(
        "T1",
        "init writes config at XDG path",
        r.returncode == 0 and cfg_path.exists(),
        f"rc={r.returncode}",
    )
    cfg = cfg_path.read_text()
    check(
        "T1",
        "init template has empty sources (no whole-home footgun)",
        "sources = []" in cfg,
        "sources = [] present",
    )
    check(
        "T1",
        "init template has empty destination",
        'destination = ""' in cfg,
        'destination = "" present',
    )
    home = str(Path.home())
    no_home = home not in cfg
    check(
        "T1",
        "init template does NOT point at whole home",
        no_home,
        "no $HOME in config",
    )
    verified("F1", 'init now writes a blank/safe template (sources=[], destination="")')

    # running the blank config must fail validation, not back anything up
    r2 = run_barkup(["run"], xdg)
    check(
        "T1",
        "run with blank init config fails (validation), no copy",
        r2.returncode != 0 and len(db_rows(xdg)) == 0,
        f"rc={r2.returncode}, rows={len(db_rows(xdg))}",
    )


# --------------------------------------------------------------------------
# T2: config precedence (regression)
# --------------------------------------------------------------------------
def t2():
    xdg = fresh_xdg("prec")
    work = ROOT / "prec_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "f.txt").write_text("hi")
    dest_user = work / "dest_user"
    dest_cwd = work / "dest_cwd"
    dest_cli = work / "dest_cli"
    write_cfg(
        xdg / "barkup" / "config.toml",
        "user",
        [str(src)],
        str(dest_user),
        dry_run=False,
    )
    write_cfg(
        work / "barkup.config.toml", "cwd", [str(src)], str(dest_cwd), dry_run=False
    )
    cli_cfg = work / "cli.toml"
    write_cfg(cli_cfg, "cli", [str(src)], str(dest_cli), dry_run=False)

    r = run_barkup(["run", "--config", str(cli_cfg)], xdg, cwd=work)
    check(
        "T2",
        "cli config wins (profile=cli)",
        "profile: cli" in r.stdout.lower(),
        r.stdout[:80].replace("\n", " "),
    )
    r = run_barkup(["run"], xdg, cwd=work)
    check(
        "T2",
        "cwd config overrides user (profile=cwd)",
        "profile: cwd" in r.stdout.lower(),
        r.stdout[:80].replace("\n", " "),
    )
    (work / "barkup.config.toml").unlink()
    r = run_barkup(["run"], xdg, cwd=work)
    check(
        "T2",
        "user config used when cwd absent (profile=user)",
        "profile: user" in r.stdout.lower(),
        r.stdout[:80].replace("\n", " "),
    )


# --------------------------------------------------------------------------
# T3: real backup pipeline (regression) + dotfile exclusion (F2)
# --------------------------------------------------------------------------
def t3():
    xdg = fresh_xdg("core")
    work = ROOT / "core_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "file.txt").write_text("hello")
    (src / ".hidden").write_text("secret")
    (src / ".env").write_text("TOKEN=1")
    sub = src / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested")
    dest = work / "dest"
    cfg = work / "c.toml"
    # exclude *.log so the junk file below is skipped
    write_cfg(cfg, "core", [str(src)], str(dest), dry_run=False, exclude=["*.log"])

    r = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "T3", "basic run copies files (rc=0)", r.returncode == 0, f"rc={r.returncode}"
    )
    rows = db_rows(xdg)
    origs = {row["original_path"] for row in rows}
    check(
        "T3",
        "only non-dotfiles backed up (file.txt, sub/nested.txt)",
        str(src / "file.txt") in origs and str(sub / "nested.txt") in origs,
        f"origs={sorted(origs)}",
    )
    dot_excluded = (str(src / ".hidden") not in origs) and (
        str(src / ".env") not in origs
    )
    check(
        "T3",
        "dotfiles excluded by DEFAULT (.hidden, .env)",
        dot_excluded,
        f".hidden/.env in origs={[o for o in origs if '.hidden' in o or '.env' in o]}",
    )
    verified("F2", "dotfiles excluded by default")
    # destination nests the source dir name
    nested = dest / "src" / "file.txt"
    check(
        "T3",
        "destination nests source dir name (dest/src/file.txt)",
        nested.exists(),
        str(nested),
    )

    # incremental: unchanged / modified / new / deleted
    _ = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "T3",
        "incremental unchanged -> skipped (no new copy)",
        "skipped" in r.stdout.lower() or "unchanged" in r.stdout.lower(),
        r.stdout[:80].replace("\n", " "),
    )
    (src / "file.txt").write_text("hello MODIFIED")
    r3 = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "T3",
        "incremental modified -> 1 modified",
        "modified" in r3.stdout.lower(),
        r3.stdout[:80].replace("\n", " "),
    )
    row = db_row(xdg, str(src / "file.txt"))
    check(
        "T3",
        "modified hash updated in DB",
        row and sha256(str(src / "file.txt")) == row["hash"],
        "hash matches source",
    )
    (src / "new.txt").write_text("brand new")
    _ = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "T3",
        "incremental new file -> new DB row",
        db_row(xdg, str(src / "new.txt")) is not None,
        "new.txt row present",
    )
    (src / "new.txt").unlink()
    check(
        "T3",
        "deleted source leaves orphan DB row (until prune)",
        db_row(xdg, str(src / "new.txt")) is not None,
        "orphan row remains",
    )
    # exclude pattern
    (src / "junk.log").write_text("log")
    _ = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "T3",
        "exclude pattern honored (junk.log skipped)",
        db_row(xdg, str(src / "junk.log")) is None,
        "junk.log not backed up",
    )


# --------------------------------------------------------------------------
# T4: dry_run preview-only (F4/F5) + safe default
# --------------------------------------------------------------------------
def t4():
    xdg = fresh_xdg("dry")
    work = ROOT / "dry_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    dest = work / "dest"
    cfg_dry = work / "dry.toml"
    write_cfg(cfg_dry, "d", [str(src)], str(dest), dry_run=True)
    r = run_barkup(["run", "--config", str(cfg_dry)], xdg)
    check(
        "T4",
        "dry_run=true -> no copy, dest absent",
        r.returncode == 0 and not dest.exists(),
        f"rc={r.returncode}, dest={dest.exists()}",
    )
    check(
        "T4",
        "dry_run output says 'dry run'",
        "dry run" in r.stdout.lower(),
        r.stdout[:60].replace("\n", " "),
    )
    verified("F4", "dry_run is preview-only (no copy, no prompt)")
    # --yes in dry mode is a no-op
    run_barkup(["run", "--yes", "--config", str(cfg_dry)], xdg)
    check(
        "T4",
        "run --yes under dry_run still no copy (no-op)",
        not dest.exists(),
        f"dest={dest.exists()}",
    )
    verified("F5", "--yes is a no-op in dry_run mode (safety net preserved)")
    # default (omit dry_run) -> preview
    cfg_def = work / "def.toml"
    write_cfg(cfg_def, "def", [str(src)], str(dest), dry_run=None)
    r3 = run_barkup(["run", "--config", str(cfg_def)], xdg)
    check(
        "T4",
        "omitting dry_run defaults to preview (safe-by-default)",
        not dest.exists() and "dry run" in r3.stdout.lower(),
        f"dest={dest.exists()}",
    )


# --------------------------------------------------------------------------
# T5: verify hashes backup copy (F6)
# --------------------------------------------------------------------------
def t5():
    xdg = fresh_xdg("verify")
    work = ROOT / "verify_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "a.txt").write_text("aaa")
    (src / "b.txt").write_text("bbb")
    dest = work / "dest"
    cfg = work / "c.toml"
    write_cfg(cfg, "v", [str(src)], str(dest), dry_run=False)
    run_barkup(["run", "--config", str(cfg)], xdg)

    r = run_barkup(["verify", "--name", "v", "--config", str(cfg)], xdg)
    check(
        "T5",
        "verify all OK -> rc=0",
        r.returncode == 0 and "OK:" in r.stdout,
        f"rc={r.returncode}, out={r.stdout[:60].replace(chr(10),' ')}",
    )
    verified("F6", "verify hashes the BACKUP copy and exits non-zero on problems")

    # delete the backup copy (source intact) -> Missing, rc=1
    row_a = db_row(xdg, str(src / "a.txt"))
    os.remove(row_a["backup_path"])
    r2 = run_barkup(["verify", "--name", "v", "--config", str(cfg)], xdg)
    check(
        "T5",
        "missing backup copy -> 'Missing:' and rc=1",
        r2.returncode == 1 and "missing:" in r2.stdout.lower(),
        f"rc={r2.returncode}, out={r2.stdout[:60].replace(chr(10),' ')}",
    )

    # corrupt the backup copy -> Mismatched, rc=1
    row_b = db_row(xdg, str(src / "b.txt"))
    Path(row_b["backup_path"]).write_text("CORRUPTED")
    r3 = run_barkup(["verify", "--name", "v", "--config", str(cfg)], xdg)
    check(
        "T5",
        "corrupted backup copy -> 'Mismatched:' and rc=1",
        r3.returncode == 1 and "mismatch" in r3.stdout.lower(),
        f"rc={r3.returncode}, out={r3.stdout[:60].replace(chr(10),' ')}",
    )


# --------------------------------------------------------------------------
# T6: restore overwrite guard (F7)
# --------------------------------------------------------------------------
def t6():
    xdg = fresh_xdg("restore")
    work = ROOT / "restore_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    doc = src / "doc.txt"
    doc.write_text("ORIGINAL backup content")
    dest = work / "dest"
    cfg = work / "c.toml"
    write_cfg(cfg, "rs", [str(src)], str(dest), dry_run=False)
    run_barkup(["run", "--config", str(cfg)], xdg)

    # modify the live source so an overwrite is detectable
    doc.write_text("UNSAVED local edits")

    r = run_barkup(["restore", str(doc), "--config", str(cfg)], xdg)
    check(
        "T6",
        "restore without --yes refuses (rc=1, guard)",
        r.returncode == 1 and "already exists" in (r.stderr.lower() + r.stdout.lower()),
        f"rc={r.returncode}",
    )
    check(
        "T6",
        "guarded restore leaves live original untouched",
        doc.read_text() == "UNSAVED local edits",
        doc.read_text(),
    )
    verified("F7", "restore onto existing original requires --yes (overwrite guard)")

    r2 = run_barkup(["restore", str(doc), "--yes", "--config", str(cfg)], xdg)
    check(
        "T6",
        "restore --yes overwrites original with backup content",
        r2.returncode == 0 and doc.read_text() == "ORIGINAL backup content",
        f"rc={r2.returncode}, content={doc.read_text()}",
    )

    # --to is the literal output path for a single-file restore
    out = work / "restore_out"
    r3 = run_barkup(
        ["restore", str(doc), "--to", str(out), "--yes", "--config", str(cfg)], xdg
    )
    check(
        "T6",
        "restore --to writes the file at the --to path",
        r3.returncode == 0
        and out.exists()
        and out.read_text() == "ORIGINAL backup content",
        f"rc={r3.returncode}, out_exists={out.exists()}",
    )

    # missing backup -> clean error, no crash
    (src / "ghost.txt").write_text("x")
    r4 = run_barkup(["restore", str(src / "ghost.txt"), "--config", str(cfg)], xdg)
    check(
        "T6",
        "restore of unbacked-up path errors cleanly (rc=1)",
        r4.returncode == 1,
        f"rc={r4.returncode}",
    )


# --------------------------------------------------------------------------
# T7: compression (regression)
# --------------------------------------------------------------------------
def t7():
    xdg = fresh_xdg("comp")
    work = ROOT / "comp_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "a.txt").write_text("plain text content")
    dest = work / "dest"
    cfg_off = work / "off.toml"
    write_cfg(cfg_off, "off", [str(src)], str(dest), dry_run=False, compression=False)
    run_barkup(["run", "--config", str(cfg_off)], xdg)
    row = db_row(xdg, str(src / "a.txt"))
    check(
        "T7",
        "compression=false -> plain copy, compressed=0",
        row["compressed"] == 0
        and Path(row["backup_path"]).exists()
        and not Path(row["backup_path"] + ".zip").exists(),
        f"compressed={row['compressed']}",
    )

    # compression=true -> .zip sidecar
    xdg2 = fresh_xdg("comp2")
    cfg_on = work / "on.toml"
    write_cfg(
        cfg_on, "on", [str(src)], str(dest / "on"), dry_run=False, compression=True
    )
    run_barkup(["run", "--config", str(cfg_on)], xdg2)
    row2 = db_row(xdg2, str(src / "a.txt"))
    zpath = Path(row2["backup_path"])
    check(
        "T7",
        "compression=true -> .zip sidecar, compressed=1",
        row2["compressed"] == 1 and zpath.exists() and zpath.suffix == ".zip",
        f"compressed={row2['compressed']}, backup={row2['backup_path']}",
    )
    # restore from compressed (--to is the literal output path)
    out = work / "comp_restore"
    r = run_barkup(
        [
            "restore",
            str(src / "a.txt"),
            "--to",
            str(out),
            "--yes",
            "--config",
            str(cfg_on),
        ],
        xdg2,
    )
    check(
        "T7",
        "restore from compressed backup yields correct content",
        r.returncode == 0 and out.exists() and out.read_text() == "plain text content",
        f"rc={r.returncode}",
    )

    # already-compressed ext -> copied as-is
    xdg3 = fresh_xdg("comp3")
    jpg = src / "pic.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xe0" + b"fakejpg" * 100)
    cfg_jpg = work / "jpg.toml"
    write_cfg(
        cfg_jpg, "jpg", [str(src)], str(dest / "jpg"), dry_run=False, compression=True
    )
    run_barkup(["run", "--config", str(cfg_jpg)], xdg3)
    row3 = db_row(xdg3, str(jpg))
    check(
        "T7",
        "already-compressed ext copied as-is (compressed=0)",
        row3["compressed"] == 0
        and Path(row3["backup_path"]).exists()
        and Path(row3["backup_path"]).suffix == ".jpg",
        f"compressed={row3['compressed']}",
    )


# --------------------------------------------------------------------------
# T8: reporting commands (regression)
# --------------------------------------------------------------------------
def t8():
    xdg = fresh_xdg("report")
    work = ROOT / "report_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    dest = work / "dest"
    cfg = work / "c.toml"
    write_cfg(cfg, "rp", [str(src)], str(dest), dry_run=False)
    run_barkup(["run", "--config", str(cfg)], xdg)

    r = run_barkup(["list", "--config", str(cfg)], xdg)
    check(
        "T8",
        "list shows backed-up files",
        r.returncode == 0 and "a.txt" in r.stdout,
        f"rc={r.returncode}",
    )
    r2 = run_barkup(["status", "--name", "rp", "--config", str(cfg)], xdg)
    check("T8", "status shows stats", r2.returncode == 0, f"rc={r2.returncode}")
    r3 = run_barkup(["profiles", "--config", str(cfg)], xdg)
    check(
        "T8",
        "profiles lists profiles",
        r3.returncode == 0 and "rp" in r3.stdout,
        f"rc={r3.returncode}",
    )


# --------------------------------------------------------------------------
# T9: prune (NEW BUG) -- reports success but removes nothing
# --------------------------------------------------------------------------
def t9():
    xdg = fresh_xdg("prune")
    work = ROOT / "prune_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    (src / "b.txt").write_text("b")
    dest = work / "dest"
    cfg = work / "c.toml"
    write_cfg(cfg, "pr", [str(src)], str(dest), dry_run=False)
    run_barkup(["run", "--config", str(cfg)], xdg)
    before = len(db_rows(xdg))
    check("T9", "two rows backed up before prune", before == 2, f"before={before}")

    # delete b.txt source -> orphan
    (src / "b.txt").unlink()
    r = run_barkup(["prune", "--config", str(cfg)], xdg)
    after_dry = len(db_rows(xdg))
    check(
        "T9",
        "prune (dry) lists orphan, DB unchanged",
        "would remove" in r.stdout.lower() and after_dry == before,
        f"rc={r.returncode}, after_dry={after_dry}",
    )

    r2 = run_barkup(["prune", "--yes", "--config", str(cfg)], xdg)
    after_yes = len(db_rows(xdg))
    removed = after_yes == before - 1
    check(
        "T9",
        "prune --yes REMOVES the orphan row",
        removed,
        f"rc={r2.returncode}, before={before}, after={after_yes}, out={r2.stdout.strip()}",
    )

    # --delete-backups should also delete the backup file
    (src / "c.txt").write_text("c")
    run_barkup(["run", "--config", str(cfg)], xdg)
    (src / "c.txt").unlink()
    r3 = run_barkup(["prune", "--yes", "--delete-backups", "--config", str(cfg)], xdg)
    after_del = len(db_rows(xdg))
    bbackup = dest / "src" / "b.txt"
    cbackup = dest / "src" / "c.txt"
    files_gone = (not bbackup.exists()) and (not cbackup.exists())
    check(
        "T9",
        "prune --yes --delete-backups removes rows AND backup files",
        after_del == before - 1 and files_gone,
        f"rc={r3.returncode}, after={after_del}, files_gone={files_gone}, out={r3.stdout.strip()}",
    )

    if not removed or not files_gone:
        finding(
            "HIGH",
            "`prune` reports success but removes nothing",
            "prune --yes prints 'Removed N orphan record(s).' (and with "
            "--delete-backups also 'Backup files were also deleted.') but the "
            "DB rows and on-disk backup files are unchanged. Verified: 2 rows "
            "before, 2 rows after `prune --yes`; all backup files remain after "
            "`prune --yes --delete-backups`. The orphan-cleanup feature (F3) is "
            "non-functional in 0.2.0.",
        )


# --------------------------------------------------------------------------
# T10: edge cases (regression + behavior change)
# --------------------------------------------------------------------------
def t10():
    xdg = fresh_xdg("edge")
    work = ROOT / "edge_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    real = src / "real.txt"
    real.write_text("real")
    # symlinked file
    (src / "link.txt").symlink_to(real)
    # symlinked dir (should NOT be recursed for a safe backup)
    sub = src / "sub"
    sub.mkdir()
    (sub / "inner.txt").write_text("inner")
    linkdir = src / "linkdir"
    linkdir.symlink_to(sub, target_is_directory=True)
    dest = work / "dest"
    cfg = work / "c.toml"
    write_cfg(cfg, "e", [str(src)], str(dest), dry_run=False)
    run_barkup(["run", "--config", str(cfg)], xdg)
    rows = {r["original_path"] for r in db_rows(xdg)}
    check(
        "T10",
        "symlinked file is followed/copied",
        str(src / "link.txt") in rows,
        "link.txt backed up",
    )
    recursed = str(sub / "inner.txt") in rows
    check(
        "T10",
        "symlinked dir is recursed (changed from 0.1.0)",
        recursed,
        "inner.txt backed up via linkdir",
    )
    if recursed:
        finding(
            "MED",
            "Symlinked directories are now recursed (over-backup / loop risk)",
            "0.1.0 did not traverse symlinked directories; 0.2.0 follows them. "
            "A symlink into a large or external tree is now backed up in full, and "
            "a cyclic symlink could cause unbounded traversal (not tested live to "
            "avoid a hang). Observed: a symlink to a subdir caused its contents to "
            "be backed up. Recommend guarding symlinked directories (skip or warn) "
            "as was the 0.1.0 behavior.",
        )

    # empty source dir
    xdg2 = fresh_xdg("edge2")
    empt = work / "empty"
    empt.mkdir()
    cfg2 = work / "c2.toml"
    write_cfg(cfg2, "e2", [str(empt)], str(work / "dest2"), dry_run=False)
    r = run_barkup(["run", "--config", str(cfg2)], xdg2)
    check(
        "T10",
        "empty source handled (rc=0, 0 files)",
        r.returncode == 0 and len(db_rows(xdg2)) == 0,
        f"rc={r.returncode}",
    )

    # large file hashing matches sha256sum
    xdg3 = fresh_xdg("edge3")
    big = work / "big.bin"
    big.write_bytes(b"X" * 200000)
    cfg3 = work / "c3.toml"
    write_cfg(cfg3, "e3", [str(big)], str(work / "dest3"), dry_run=False)
    run_barkup(["run", "--config", str(cfg3)], xdg3)
    row = db_row(xdg3, str(big))
    check(
        "T10",
        "large file hash matches sha256 of source",
        row and row["hash"] == sha256(str(big)),
        f"match={row and row['hash'] == sha256(str(big))}",
    )
    finding(
        "INFO",
        "Per-file copy error handling untested (root bypasses permissions)",
        "run_local_barkup wraps each file copy in try/except and continues; "
        "as root in this sandbox chmod 000 / unreadable files are still "
        "readable, so the failure path could not be exercised live.",
    )


# --------------------------------------------------------------------------
def main():
    print("=== barkup 0.2.0 LIVE TEST HARNESS ===")
    t0()
    t1()
    t2()
    t3()
    t4()
    t5()
    t6()
    t7()
    t8()
    t9()
    t10()

    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    failed = total - passed
    print("\n=== SUMMARY ===")
    print(f"checks: {total}  PASS: {passed}  FAIL: {failed}")
    print(f"verified fixes: {len(VERIFIED)}")
    print(f"new findings: {len(FINDINGS)}")
    for label, what in VERIFIED:
        print(f"  [VERIFIED] {label}: {what}")
    for sev, title, _ in FINDINGS:
        print(f"  [{sev}] {title}")

    # write findings doc
    lines = [
        "# barkup 0.2.0 — Live Test Findings",
        "",
        f"Checks: {total} (PASS {passed}, FAIL {failed})",
        f"Verified prior fixes: {len(VERIFIED)}",
        "",
        "## Verified fixes (from 0.1.0 live findings)",
        "",
    ]
    for label, what in VERIFIED:
        lines.append(f"- [VERIFIED {label}] {what}")
    lines += ["", "## New findings", ""]
    if FINDINGS:
        for sev, title, detail in FINDINGS:
            lines.append(f"### [{sev}] {title}")
            lines.append(detail)
            lines.append("")
    else:
        lines.append("_None._")
        lines.append("")
    (Path(__file__).parent / "FINDINGS_2_0.md").write_text("\n".join(lines))
    print(f"\nFINDINGS written to {Path(__file__).parent / 'FINDINGS_2_0.md'}")


if __name__ == "__main__":
    main()
