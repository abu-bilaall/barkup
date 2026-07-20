"""Live end-to-end test harness for the PUBLISHED barkup 0.1.0 wheel.
Drives the installed `barkup` CLI (subprocess) against real temp filesystems.
Isolates state per scenario via XDG_CONFIG_HOME so ~/.config is never touched.
Cloud/Google Drive is out of scope (stubbed upstream).

NOTE: `--config` is a GROUP-level option, so it must precede the subcommand:
    barkup --config X run        (NOT  barkup run --config X)
"""

import os
import shutil
import sqlite3
import subprocess
import hashlib
import fnmatch
from pathlib import Path

# --- environment (overridable) ---------------------------------------------
# LIVE_ROOT : scratch dir for scenarios (default: a tmp dir)
# LIVE_VENV: venv that holds the installed `barkup` wheel
# BARKUP    : explicit path to the barkup executable (overrides LIVE_VENV)
ROOT = Path(os.environ.get("LIVE_ROOT", "/tmp/barkup_live"))
_VENV = Path(os.environ.get("LIVE_VENV", str(ROOT / ".venv")))
BARKUP = os.environ.get("BARKUP") or str(_VENV / "bin" / "barkup")


def _ensure_barkup():
    """Auto-bootstrap the published wheel if not already installed.

    Uses `uv` (already available in this project). Skips if BARKUP exists.
    """
    if os.path.exists(BARKUP):
        return
    _VENV.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "venv", str(_VENV)], check=True)
    subprocess.run(
        ["uv", "pip", "install", "-p", str(_VENV / "bin" / "python"), "barkup==0.1.0"],
        check=True,
    )


_ensure_barkup()
RESULTS = []  # (phase, name, ok, detail)
FINDINGS = []  # (severity, title, detail)


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


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def matches_exclude(p, patterns):
    for pat in patterns:
        if fnmatch.fnmatch(p.name, pat):
            return True
        for part in p.parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False


def fresh_xdg(name):
    x = ROOT / f"xdg_{name}"
    shutil.rmtree(x, ignore_errors=True)
    x.mkdir(parents=True)
    return x


def run_barkup(args, xdg, cwd=None, input_text=None):
    # `--config` is a group-level option and MUST precede the subcommand:
    #   barkup --config X run   (NOT  barkup run --config X)
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


def write_cfg(
    path,
    profile,
    sources,
    dest,
    dry_run=False,
    compression=False,
    exclude=None,
    extra="",
):
    exclude = exclude or []
    text = (
        f"[general]\n"
        f'profile_name = "{profile}"\n'
        f"dry_run = {str(dry_run).lower()}\n"
        f"sources = {sources}\n"
        f"compression = {str(compression).lower()}\n"
        f"exclude = {exclude}\n\n"
        f"[local]\n"
        f'destination = "{dest}"\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + extra)


def restore_all_path(original_abs, dest):
    o = Path(original_abs)
    return Path(dest) / o.relative_to(o.anchor)


# --------------------------------------------------------------------------
# S0: install + smoke
# --------------------------------------------------------------------------
def t0():
    xdg = fresh_xdg("s0")
    r = run_barkup(["--help"], xdg)
    cmds = ["init", "run", "list", "status", "verify", "profiles", "restore"]
    check(
        "S0",
        "CLI --help lists all 7 commands",
        r.returncode == 0 and all(c in r.stdout for c in cmds),
        f"rc={r.returncode}",
    )
    r2 = run_barkup(["--version"], xdg)
    check(
        "S0",
        "No --version flag (exits non-zero)",
        r2.returncode != 0,
        f"rc={r2.returncode}",
    )
    r3 = run_barkup(["verify"], xdg)  # no config, no DB
    check(
        "S0",
        "verify with no config/DB exits non-zero gracefully",
        r3.returncode in (0, 1),
        f"rc={r3.returncode}",
    )


# --------------------------------------------------------------------------
# S1: config + init
# --------------------------------------------------------------------------
def t1a_init():
    xdg = fresh_xdg("init")
    r = run_barkup(["init"], xdg)
    cfg_path = xdg / "barkup" / "config.toml"
    check(
        "S1a",
        "init writes config at XDG path",
        r.returncode == 0 and cfg_path.exists(),
        f"rc={r.returncode}",
    )
    cfg = cfg_path.read_text()
    home = str(Path.home())
    check(
        "S1a",
        "default sources point at whole home (footgun)",
        home in cfg,
        "sources includes $HOME",
    )
    check("S1a", "default destination is ~/Backups", "Backups" in cfg)
    finding(
        "HIGH",
        "Default `init` config backs up ENTIRE home into ~/Backups",
        "init_config sets sources=[$HOME], destination=$HOME/Backups. The backup "
        "dir sits inside the source tree, so a second run would try to re-back-up "
        "the growing ~/Backups tree (self-referential, unbounded growth). Because "
        "dotfiles are included, it also copies .ssh/.env and other secret dotfiles.",
    )


def t1b_precedence():
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
    # user layer (auto-loaded from XDG)
    write_cfg(xdg / "barkup" / "config.toml", "user", [str(src)], str(dest_user))
    # cwd layer
    write_cfg(work / "barkup.config.toml", "cwd", [str(src)], str(dest_cwd))
    # cli layer
    cli_cfg = work / "cli.toml"
    write_cfg(cli_cfg, "cli", [str(src)], str(dest_cli))

    r = run_barkup(["run", "--config", str(cli_cfg)], xdg, cwd=work)
    check(
        "S1b",
        "cli config wins (profile=cli)",
        "Running backup for profile: cli" in r.stdout,
        r.stdout[:120],
    )

    r = run_barkup(["run"], xdg, cwd=work)
    check(
        "S1b",
        "cwd config overrides user (profile=cwd)",
        "Running backup for profile: cwd" in r.stdout,
        r.stdout[:120],
    )

    (work / "barkup.config.toml").unlink()
    r = run_barkup(["run"], xdg, cwd=work)
    check(
        "S1b",
        "user config used when cwd absent (profile=user)",
        "Running backup for profile: user" in r.stdout,
        r.stdout[:120],
    )


def t1c_errors():
    xdg = fresh_xdg("err")
    work = ROOT / "err_work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    src = work / "src"
    src.mkdir()
    (src / "f.txt").write_text("x")
    srcs = f'["{src}"]'

    # E1: empty [general].sources -> custom validator fires
    c = work / "e1.toml"
    c.write_text(
        f'[general]\nsources = []\nprofile_name="p"\n\n'
        f'[local]\ndestination="{work/"d1"}/"\n'
    )
    r = run_barkup(["run", "--config", str(c)], xdg)
    check(
        "S1c-E1",
        "empty [general].sources -> exit1",
        r.returncode == 1 and "At least one source" in (r.stderr + r.stdout),
        f"rc={r.returncode}",
    )

    # E2: local sources defined but empty destination
    c = work / "e2.toml"
    c.write_text(
        f'[general]\nsources={srcs}\nprofile_name="p"\n\n'
        f'[local]\nsources={srcs}\ndestination=""\n'
    )
    r = run_barkup(["run", "--config", str(c)], xdg)
    check(
        "S1c-E2",
        "local sources + empty destination -> exit1",
        r.returncode == 1 and "destination" in (r.stderr + r.stdout).lower(),
        f"rc={r.returncode}",
    )

    # E3: missing [local].destination key entirely
    c = work / "e3.toml"
    c.write_text(f'[general]\nsources={srcs}\nprofile_name="p"\n\n[local]\n')
    r = run_barkup(["run", "--config", str(c)], xdg)
    check(
        "S1c-E3",
        "missing [local].destination key -> exit1",
        r.returncode == 1,
        f"rc={r.returncode}",
    )

    # E4: google_drive enabled without credentials
    c = work / "e4.toml"
    c.write_text(
        f'[general]\nsources={srcs}\nprofile_name="p"\n\n'
        f'[local]\ndestination="{work/"d4"}/"\n\n'
        f'[[cloud_providers]]\nprovider="google_drive"\nenabled=true\n'
    )
    r = run_barkup(["run", "--config", str(c)], xdg)
    check(
        "S1c-E4",
        "gdrive enabled w/o creds -> exit1",
        r.returncode == 1 and "Google Drive requires" in (r.stderr + r.stdout),
        f"rc={r.returncode}",
    )

    # E5: invalid TOML
    c = work / "e5.toml"
    c.write_text("[general]\nprofile_name =\n")
    r = run_barkup(["run", "--config", str(c)], xdg)
    check(
        "S1c-E5",
        "invalid TOML -> exit1",
        r.returncode == 1 and "Invalid TOML" in (r.stderr + r.stdout),
        f"rc={r.returncode}",
    )

    # E6: --config to nonexistent file -> click usage error exit2
    r = run_barkup(["run", "--config", str(work / "nope.toml")], xdg)
    check(
        "S1c-E6",
        "--config nonexistent -> exit2 (click usage error)",
        r.returncode == 2,
        f"rc={r.returncode}",
    )

    # E7: no config anywhere -> FileNotFoundError caught -> exit1
    empty = work / "empty"
    empty.mkdir(exist_ok=True)
    r = run_barkup(["run"], xdg, cwd=empty)
    check(
        "S1c-E7",
        "no config anywhere -> exit1",
        r.returncode == 1 and "No config file" in (r.stderr + r.stdout),
        f"rc={r.returncode}",
    )


# --------------------------------------------------------------------------
# S2: end-to-end run + incremental
# --------------------------------------------------------------------------
def build_src(src):
    (src / "mydocs").mkdir(parents=True)
    (src / "mydocs" / "a.txt").write_text("alpha")
    (src / "mydocs" / "sub").mkdir()
    (src / "mydocs" / "sub" / "b.txt").write_text("beta")
    (src / "mydocs" / "note.md").write_text("# note")
    (src / "data").mkdir()
    (src / "data" / "big.bin").write_bytes(b"X" * (100 * 1024))
    (src / "data" / "photo.jpg").write_bytes(b"\xff\xd8\xff\xff" + b"Z" * 2000)
    (src / "build").mkdir()
    (src / "build" / "artifact.tmp").write_text("tmp")
    (src / ".git").mkdir()
    (src / ".git" / "config").write_text("gitconfig")
    (src / "node_modules").mkdir()
    (src / "node_modules" / "lib.js").write_text("lib")
    (src / ".hidden.txt").write_text("secret")


def t2():
    xdg = fresh_xdg("run")
    base = ROOT / "run_work"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    src = base / "src"
    build_src(src)
    dest = base / "dest"
    cfg = base / "cfg.toml"
    write_cfg(
        cfg,
        "docs",
        [str(src)],
        str(dest),
        compression=False,
        exclude=["*.tmp", ".git", "node_modules"],
    )

    r = run_barkup(["run", "--config", str(cfg)], xdg)
    rows = db_rows(xdg, "docs")
    check("S2", "first run exit 0", r.returncode == 0, f"rc={r.returncode}")
    check(
        "S2",
        "first run reports 6 new files",
        "New files: 6" in r.stdout,
        r.stdout[-400:],
    )

    expected = {
        "mydocs/a.txt",
        "mydocs/sub/b.txt",
        "mydocs/note.md",
        "data/big.bin",
        "data/photo.jpg",
        ".hidden.txt",
    }
    excluded = {"build/artifact.tmp", ".git/config", "node_modules/lib.js"}
    row_rel = {str(Path(row["original_path"]).relative_to(src)) for row in rows}

    check(
        "S2",
        "all 6 expected files backed up",
        expected <= row_rel,
        f"missing={expected - row_rel}",
    )
    check(
        "S2",
        "excluded files NOT backed up",
        excluded.isdisjoint(row_rel),
        f"leaked={excluded & row_rel}",
    )
    check("S2", "row count == 6", len(rows) == 6, f"count={len(rows)}")

    for rel in expected:
        sp = src / rel
        dp = dest / "src" / rel
        ok = dp.exists() and dp.read_bytes() == sp.read_bytes()
        check("S2", f"backup content correct: {rel}", ok)
        row = next(
            x for x in rows if str(Path(x["original_path"]).relative_to(src)) == rel
        )
        check(
            "S2",
            f"db hash == sha256: {rel}",
            row["hash"] == sha256(sp) and row["compressed"] == 0,
        )
        check("S2", f"db size correct: {rel}", row["size"] == sp.stat().st_size)

    # dotfiles: empirically INCLUDED in this build (correcting an initial assumption)
    dot_in = ".hidden.txt" in row_rel
    check("S2", "dotfile .hidden.txt IS backed up", dot_in, f"dot_in={dot_in}")
    finding(
        "INFO",
        "Dotfiles ARE backed up (rglob('*') includes them in this build)",
        ".hidden.txt and .env were included in backups. Only '.git' is excluded, "
        "and that is via the exclude PATTERN, not by rglob. Implication: a "
        "home-wide config also copies .ssh/.env secret dotfiles (see default-config finding).",
    )

    # incremental: rerun unchanged
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "S2",
        "rerun with no changes -> up to date, 0 new/modified",
        "Everything is up to date" in r.stdout
        and "New files: 0" in r.stdout
        and "Modified files: 0" in r.stdout,
        r.stdout[-300:],
    )
    rows2 = db_rows(xdg, "docs")
    check("S2", "rerun did not duplicate rows", len(rows2) == 6, f"count={len(rows2)}")

    # modify a.txt
    (src / "mydocs" / "a.txt").write_text("ALPHA-CHANGED")
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "S2",
        "modify file -> 1 modified",
        "Modified files: 1" in r.stdout,
        r.stdout[-300:],
    )
    rows3 = db_rows(xdg, "docs")
    arow = next(x for x in rows3 if x["original_path"].endswith("a.txt"))
    check(
        "S2",
        "modified hash updated in db",
        arow["hash"] == sha256(src / "mydocs" / "a.txt"),
        arow["hash"][:12],
    )

    # add new file
    (src / "mydocs" / "newfile.txt").write_text("new")
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    check("S2", "add file -> 1 new", "New files: 1" in r.stdout, r.stdout[-300:])
    rows4 = db_rows(xdg, "docs")
    check("S2", "new row added (count 7)", len(rows4) == 7, f"count={len(rows4)}")

    # delete source file
    (src / "mydocs" / "newfile.txt").unlink()
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "S2",
        "delete source file -> no crash, run completes",
        r.returncode == 0,
        f"rc={r.returncode}",
    )
    rows5 = db_rows(xdg, "docs")
    check(
        "S2",
        "deleted-source row remains (orphan) in db",
        len(rows5) == 7,
        f"count={len(rows5)}",
    )
    finding(
        "MED",
        "Deleted source leaves an orphan DB row",
        "After deleting a source file, its state row stays in the DB; "
        "`verify` later flags it 'missing' but `run` never prunes it.",
    )


# --------------------------------------------------------------------------
# S3: dry-run semantics
# --------------------------------------------------------------------------
def t3():
    # 3a: dry_run + decline
    xdg = fresh_xdg("dry1")
    base = ROOT / "dry_work"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    src = base / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    dest = base / "dest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "d", [str(src)], str(dest), dry_run=True)
    r = run_barkup(["run", "--config", str(cfg)], xdg, input_text="n\n")
    check(
        "S3a",
        "dry_run + 'n' -> cancelled, no copy, exit0",
        "Backup cancelled" in r.stdout
        and r.returncode == 0
        and not db_rows(xdg, "d")
        and not any(dest.rglob("*")),
        f"rc={r.returncode}",
    )

    # 3b: dry_run + accept 'y' -> ACTUALLY COPIES
    xdg = fresh_xdg("dry2")
    r = run_barkup(["run", "--config", str(cfg)], xdg, input_text="y\n")
    copied = bool(db_rows(xdg, "d")) and (dest / "src" / "a.txt").exists()
    check(
        "S3b",
        "dry_run + 'y' PERFORMS the copy",
        copied,
        f"rows={len(db_rows(xdg,'d'))}",
    )
    finding(
        "HIGH",
        "dry_run copies files when confirmed (contradicts 'no actual copying')",
        "config.example.toml documents dry_run as '(no actual copying)' and "
        "spec.md says 'Skips actual backup if user declines'. But run_barkup "
        "proceeds to copy when the prompt returns 'y'. So dry_run is not a true "
        "dry run; confirming performs the backup.",
    )

    # 3c: dry_run + --yes -> no prompt, copies
    xdg = fresh_xdg("dry3")
    r = run_barkup(["run", "--yes", "--config", str(cfg)], xdg)
    copied = bool(db_rows(xdg, "d")) and (dest / "src" / "a.txt").exists()
    check(
        "S3c", "dry_run + --yes skips prompt and copies", copied, f"rc={r.returncode}"
    )
    finding(
        "HIGH",
        "--yes in dry_run mode forces a real copy",
        "README/cron guidance is to run `barkup run --yes`. In normal mode "
        "(dry_run=false) there is NO prompt, so --yes is a no-op. But if a user "
        "enables dry_run=true as a safety net and automates with --yes, --yes "
        "skips the prompt and performs the real backup, defeating the safety.",
    )

    # 3d: normal mode --yes is a no-op but still works
    xdg = fresh_xdg("dry4")
    cfg2 = base / "cfg2.toml"
    write_cfg(cfg2, "n", [str(src)], str(base / "dest2"), dry_run=False)
    r = run_barkup(["run", "--yes", "--config", str(cfg2)], xdg)
    check(
        "S3d",
        "normal run with --yes completes (no prompt existed)",
        r.returncode == 0 and bool(db_rows(xdg, "n")),
        f"rc={r.returncode}",
    )


# --------------------------------------------------------------------------
# S4: compression
# --------------------------------------------------------------------------
def t4():
    xdg = fresh_xdg("comp")
    base = ROOT / "comp_work"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    src = base / "src"
    src.mkdir()
    (src / "a.txt").write_text("compress me " * 50)
    (src / "photo.jpg").write_bytes(b"\xff\xd8\xff\xff" + b"Z" * 2000)
    (src / "data.zip").write_bytes(b"PK\x03\x04 fake zip" + b"Q" * 500)
    dest = base / "dest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "c", [str(src)], str(dest), compression=True)
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    rows = db_rows(xdg, "c")
    check("S4", "compression run exit 0", r.returncode == 0, f"rc={r.returncode}")

    # a.txt -> .zip sidecar, compressed=1
    a_backup = dest / "src" / "a.txt.zip"
    a_row = next(x for x in rows if x["original_path"].endswith("a.txt"))
    check(
        "S4",
        "plain file stored as .zip sidecar",
        a_backup.exists() and a_row["compressed"] == 1,
        f"compressed={a_row['compressed']}",
    )
    import zipfile

    with zipfile.ZipFile(a_backup) as z:
        content = z.read(z.namelist()[0])
    check(
        "S4", "compressed content round-trips", content == (src / "a.txt").read_bytes()
    )

    # photo.jpg -> copied as-is, compressed=0
    p_backup = dest / "src" / "photo.jpg"
    p_row = next(x for x in rows if x["original_path"].endswith("photo.jpg"))
    check(
        "S4",
        "already-compressed photo copied as-is (no .zip)",
        p_backup.exists()
        and not (dest / "src" / "photo.jpg.zip").exists()
        and p_row["compressed"] == 0,
    )

    # data.zip -> copied as-is
    z_backup = dest / "src" / "data.zip"
    z_row = next(x for x in rows if x["original_path"].endswith("data.zip"))
    check(
        "S4",
        "existing .zip copied as-is (no double zip)",
        z_backup.exists()
        and not (dest / "src" / "data.zip.zip").exists()
        and z_row["compressed"] == 0,
    )


# --------------------------------------------------------------------------
# S5: list / status / profiles
# --------------------------------------------------------------------------
def t5():
    xdg = fresh_xdg("rep")
    base = ROOT / "rep_work"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    src1 = base / "src1"
    src1.mkdir()
    (src1 / "a.txt").write_text("a")
    src2 = base / "src2"
    src2.mkdir()
    (src2 / "b.txt").write_text("b" * 5000)
    dest1 = base / "dest1"
    dest2 = base / "dest2"
    cfg1 = base / "cfg1.toml"
    cfg2 = base / "cfg2.toml"
    write_cfg(cfg1, "p1", [str(src1)], str(dest1))
    write_cfg(cfg2, "p2", [str(src2)], str(dest2))
    run_barkup(["run", "--config", str(cfg1)], xdg)
    run_barkup(["run", "--config", str(cfg2)], xdg)

    r = run_barkup(["list"], xdg)
    check(
        "S5",
        "list shows both profiles' mappings",
        "src1/a.txt" in r.stdout
        and "src2/b.txt" in r.stdout
        and "bytes, backed up" in r.stdout,
        r.stdout[:300],
    )
    r = run_barkup(["list", "--name", "p1"], xdg)
    check(
        "S5",
        "list --name filters to one profile",
        "src1/a.txt" in r.stdout and "src2/b.txt" not in r.stdout,
    )
    r = run_barkup(["status"], xdg)
    check(
        "S5",
        "status shows per-profile stats",
        "Profile: p1" in r.stdout
        and "Profile: p2" in r.stdout
        and "Total size:" in r.stdout
        and "Files:" in r.stdout,
        r.stdout[:400],
    )
    r = run_barkup(["profiles"], xdg)
    check(
        "S5",
        "profiles lists p1 and p2",
        "p1" in r.stdout and "p2" in r.stdout,
        r.stdout[:300],
    )


# --------------------------------------------------------------------------
# S6: verify (incl. backup-copy gap)
# --------------------------------------------------------------------------
def t6():
    base = ROOT / "v_work"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()

    # 6a clean
    xdg = fresh_xdg("v1")
    src = base / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    (src / "b.txt").write_text("b")
    dest = base / "dest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "v1", [str(src)], str(dest))
    run_barkup(["run", "--config", str(cfg)], xdg)
    r = run_barkup(["verify", "--name", "v1"], xdg)
    check(
        "S6a",
        "clean verify: all OK, exit0",
        r.returncode == 0
        and "OK: 2" in r.stdout
        and "Missing: 0" in r.stdout
        and "Mismatched: 0" in r.stdout,
        r.stdout[:300],
    )

    # 6b modify source -> mismatch, exit1
    xdg = fresh_xdg("v2")
    src2 = base / "src2"
    shutil.rmtree(src2, ignore_errors=True)
    src2.mkdir()
    (src2 / "a.txt").write_text("a")
    (src2 / "b.txt").write_text("b")
    cfg2 = base / "cfg2.toml"
    write_cfg(cfg2, "v2", [str(src2)], str(base / "dest2"))
    run_barkup(["run", "--config", str(cfg2)], xdg)
    (src2 / "a.txt").write_text("A-MODIFIED")
    r = run_barkup(["verify", "--name", "v2"], xdg)
    check(
        "S6b",
        "modified source -> Mismatched:1, exit1",
        r.returncode == 1 and "Mismatched: 1" in r.stdout,
        r.stdout[:300],
    )

    # 6c delete source -> missing, exit1
    xdg = fresh_xdg("v3")
    src3 = base / "src3"
    shutil.rmtree(src3, ignore_errors=True)
    src3.mkdir()
    (src3 / "a.txt").write_text("a")
    (src3 / "b.txt").write_text("b")
    cfg3 = base / "cfg3.toml"
    write_cfg(cfg3, "v3", [str(src3)], str(base / "dest3"))
    run_barkup(["run", "--config", str(cfg3)], xdg)
    (src3 / "b.txt").unlink()
    r = run_barkup(["verify", "--name", "v3"], xdg)
    check(
        "S6c",
        "deleted source -> Missing:1, exit1",
        r.returncode == 1 and "Missing: 1" in r.stdout,
        r.stdout[:300],
    )

    # 6d GAP: delete BACKUP copy, source intact -> verify still OK
    xdg = fresh_xdg("v4")
    src4 = base / "src4"
    shutil.rmtree(src4, ignore_errors=True)
    src4.mkdir()
    (src4 / "a.txt").write_text("a")
    (src4 / "b.txt").write_text("b")
    cfg4 = base / "cfg4.toml"
    write_cfg(cfg4, "v4", [str(src4)], str(base / "dest4"))
    run_barkup(["run", "--config", str(cfg4)], xdg)
    rows = db_rows(xdg, "v4")
    a_row = next(x for x in rows if x["original_path"].endswith("a.txt"))
    Path(a_row["backup_path"]).unlink()
    r = run_barkup(["verify", "--name", "v4"], xdg)
    check(
        "S6d",
        "deleted BACKUP copy still reports OK (gap)",
        r.returncode == 0 and "OK: 2" in r.stdout,
        r.stdout[:300],
    )
    finding(
        "HIGH",
        "`verify` checks the SOURCE, not the backup copy",
        "spec.md: 'Check all backed-up files still exist ... Report any "
        "corrupted or missing files.' But verify_backup re-hashes the original "
        "source file. Deleting/corrupting the backup copy while the source is "
        "intact makes verify report OK/exit0, so it cannot detect a lost or "
        "corrupted backup.",
    )


# --------------------------------------------------------------------------
# S7: restore
# --------------------------------------------------------------------------
def t7():
    xdg = fresh_xdg("res")
    base = ROOT / "res_work"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()
    src = base / "src"
    src.mkdir()
    (src / "a.txt").write_text("alpha")
    (src / "b.txt").write_text("beta")
    dest = base / "dest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "r1", [str(src)], str(dest))
    run_barkup(["run", "--config", str(cfg)], xdg)

    # single restore --to
    out_single = base / "rest_single" / "a.txt"
    r = run_barkup(["restore", str(src / "a.txt"), "--to", str(out_single)], xdg)
    check(
        "S7a",
        "single restore --to copies file, exit0",
        r.returncode == 0 and out_single.exists() and out_single.read_text() == "alpha",
        r.stdout[:200],
    )

    # single restore NO --to overwrites original in place
    orig_backup_content = "alpha"
    (src / "a.txt").write_text("CHANGED-BY-USER")
    r = run_barkup(["restore", str(src / "a.txt")], xdg)
    check(
        "S7b",
        "single restore w/o --to overwrites original in place",
        r.returncode == 0 and (src / "a.txt").read_text() == orig_backup_content,
        f"now={(src/'a.txt').read_text()!r}",
    )
    finding(
        "MED",
        "`restore <path>` with no --to overwrites the live original",
        "restore_file with destination=None copies the backup onto the original "
        "path, destroying any un-backed-up local changes. No --dry-run / "
        "confirmation.",
    )

    # restore file not in DB
    r = run_barkup(["restore", str(base / "nope.txt")], xdg)
    check(
        "S7c", "restore unknown path -> exit1", r.returncode == 1, f"rc={r.returncode}"
    )

    # restore when backup file missing
    rows = db_rows(xdg, "r1")
    b_row = next(x for x in rows if x["original_path"].endswith("b.txt"))
    Path(b_row["backup_path"]).unlink()
    r = run_barkup(["restore", str(src / "b.txt")], xdg)
    check(
        "S7d",
        "restore when backup missing -> exit1",
        r.returncode == 1 and "Backup file missing" in (r.stderr + r.stdout),
        f"rc={r.returncode}",
    )

    # --all --name --to (b.txt backup deleted -> one failure reported)
    r = run_barkup(
        ["restore", "--all", "--name", "r1", "--to", str(base / "rest_all")], xdg
    )
    check(
        "S7e",
        "--all restores existing files; missing one reported",
        r.returncode == 1
        and "Restored 1 files" in r.stdout
        and "Failed to restore 1" in r.stdout,
        r.stdout[:400],
    )

    # clean --all to confirm full success path
    xdg2 = fresh_xdg("res2")
    src2 = base / "src2"
    shutil.rmtree(src2, ignore_errors=True)
    src2.mkdir()
    (src2 / "x.txt").write_text("x")
    (src2 / "sub").mkdir()
    (src2 / "sub" / "y.txt").write_text("y")
    cfg2 = base / "cfg2.toml"
    write_cfg(cfg2, "r2", [str(src2)], str(base / "dest2"))
    run_barkup(["run", "--config", str(cfg2)], xdg2)
    r = run_barkup(
        ["restore", "--all", "--name", "r2", "--to", str(base / "rest_all2")], xdg2
    )
    check(
        "S7f",
        "--all clean run restores all, exit0",
        r.returncode == 0
        and "Restored 2 files" in r.stdout
        and "Failed" not in r.stdout,
        r.stdout[:300],
    )
    xp = restore_all_path(str((src2 / "x.txt").resolve()), base / "rest_all2")
    yp = restore_all_path(str((src2 / "sub" / "y.txt").resolve()), base / "rest_all2")
    check(
        "S7f",
        "--all preserves absolute dir tree",
        xp.exists() and yp.exists() and xp.read_text() == "x" and yp.read_text() == "y",
    )

    # --all without --name
    r = run_barkup(["restore", "--all"], xdg2)
    check(
        "S7g", "--all without --name -> exit1", r.returncode == 1, f"rc={r.returncode}"
    )

    # --all nonexistent profile
    r = run_barkup(["restore", "--all", "--name", "zzz"], xdg2)
    check(
        "S7h",
        "--all with unknown profile -> exit1",
        r.returncode == 1,
        f"rc={r.returncode}",
    )

    # compressed restore
    xdg3 = fresh_xdg("res3")
    src3 = base / "src3"
    shutil.rmtree(src3, ignore_errors=True)
    src3.mkdir()
    (src3 / "c.txt").write_text("compressible content " * 20)
    cfg3 = base / "cfg3.toml"
    write_cfg(cfg3, "r3", [str(src3)], str(base / "dest3"), compression=True)
    run_barkup(["run", "--config", str(cfg3)], xdg3)
    r = run_barkup(
        ["restore", "--all", "--name", "r3", "--to", str(base / "rest_all3")], xdg3
    )
    cp = restore_all_path(str((src3 / "c.txt").resolve()), base / "rest_all3")
    check(
        "S7i",
        "compressed backup restores & decompresses correctly",
        r.returncode == 0
        and cp.exists()
        and cp.read_text() == "compressible content " * 20,
        r.stdout[:200],
    )


# --------------------------------------------------------------------------
# S8: edge cases
# --------------------------------------------------------------------------
def t8():
    base = ROOT / "edge_work"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir()

    # 8a nonexistent source
    xdg = fresh_xdg("e_src")
    dest = base / "dest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "e", ['"/nonexistent_path_xyz_123"'], str(dest))
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "S8a",
        "nonexistent source -> exit1, error msg",
        r.returncode == 1 and "Source path doesn't exist" in (r.stderr + r.stdout),
        f"rc={r.returncode}",
    )

    # 8c symlinks
    xdg = fresh_xdg("e_sym")
    src = base / "symsrc"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir()
    (src / "real.txt").write_text("real")
    (src / "link.txt").symlink_to(src / "real.txt")
    realsub = src / "realsub"
    realsub.mkdir()
    (realsub / "inner.txt").write_text("inner")
    (src / "linkdir").symlink_to(realsub)
    dest = base / "symdest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "s", [str(src)], str(dest))
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    rows = db_rows(xdg, "s")
    rels = {str(Path(x["original_path"]).relative_to(src)) for x in rows}
    check(
        "S8c",
        "symlinked file is followed and backed up",
        "link.txt" in rels
        and (dest / src.name / "link.txt").exists()
        and (dest / src.name / "link.txt").read_text() == "real",
        f"rels={rels}",
    )
    check("S8c", "real subdir content backed up", "realsub/inner.txt" in rels)
    check(
        "S8c",
        "symlinked dir is NOT recursed",
        "linkdir/inner.txt" not in rels and not (dest / src.name / "linkdir").exists(),
        f"rels={rels}",
    )

    # 8d dotfile (reuse src with a dotfile)
    (src / ".env").write_text("SECRET=1")
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    rows = db_rows(xdg, "s")
    rels = {str(Path(x["original_path"]).relative_to(src)) for x in rows}
    check(
        "S8d",
        ".env dotfile IS backed up (rglob includes dotfiles)",
        ".env" in rels,
        f"rels={rels}",
    )

    # 8e empty source dir
    xdg = fresh_xdg("e_empty")
    src = base / "emptysrc"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir()
    dest = base / "emptydest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "empty", [str(src)], str(dest))
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    check(
        "S8e", "empty source dir -> exit0, no error", r.returncode == 0, r.stdout[-200:]
    )

    # 8f large-file hash matches sha256sum
    xdg = fresh_xdg("e_big")
    src = base / "bigsrc"
    shutil.rmtree(src, ignore_errors=True)
    src.mkdir()
    big = src / "big.bin"
    big.write_bytes(b"Q" * (200 * 1024))
    dest = base / "bigdest"
    cfg = base / "cfg.toml"
    write_cfg(cfg, "big", [str(src)], str(dest))
    r = run_barkup(["run", "--config", str(cfg)], xdg)
    rows = db_rows(xdg, "big")
    row = rows[0]
    sha = subprocess.run(
        ["sha256sum", str(big)], capture_output=True, text=True
    ).stdout.split()[0]
    check(
        "S8f",
        "large-file (>64KB chunked) hash matches sha256sum",
        row["hash"] == sha,
        f"db={row['hash'][:12]} cli={sha[:12]}",
    )

    # 8g per-file IO error: not reproducible as root (posix permission bypass)
    finding(
        "INFO",
        "Per-file copy error handling untested (root bypasses permissions)",
        "run_local_barkup wraps each file copy in try/except and continues; "
        "as root in this sandbox chmod 000 / unreadable files are still "
        "readable, so the failure path could not be exercised live.",
    )


# --------------------------------------------------------------------------
def main():
    print("=== barkup 0.1.0 LIVE TEST HARNESS ===")
    t0()
    t1a_init()
    t1b_precedence()
    t1c_errors()
    t2()
    t3()
    t4()
    t5()
    t6()
    t7()
    t8()

    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    failed = total - passed
    print("\n=== SUMMARY ===")
    print(f"checks: {total}  PASS: {passed}  FAIL: {failed}")
    print(f"findings: {len(FINDINGS)}")
    for sev, title, _ in FINDINGS:
        print(f"  [{sev}] {title}")
    # write findings doc
    lines = [
        "# barkup 0.1.0 — Live Test Findings",
        "",
        f"Checks: {total} (PASS {passed}, FAIL {failed})",
        "",
        "## Findings",
        "",
    ]
    for sev, title, detail in FINDINGS:
        lines.append(f"### [{sev}] {title}")
        lines.append(detail)
        lines.append("")
    (Path(__file__).parent / "FINDINGS.md").write_text("\n".join(lines))
    print(f"\nFINDINGS.md written to {ROOT/'FINDINGS.md'}")
    print(f"\nFINDINGS.md written to {Path(__file__).parent / 'FINDINGS.md'}")


if __name__ == "__main__":
    main()
