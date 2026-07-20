"""
Tests for the CLI command structure

Covers command registration and the shared profile-resolution helper.
"""

from click.testing import CliRunner
from pathlib import Path
from barkup.hashing import calculate_file_hash
from barkup.database import open_connection
from barkup.cli import cli, resolve_profile_name


class _General:
    def __init__(self, profile_name):
        self.profile_name = profile_name


class _Config:
    """Minimal stand-in for a BarkupConfig with optional general section."""

    def __init__(self, profile_name=None):
        self.general = _General(profile_name) if profile_name is not None else None


class TestCliStructure:
    def test_cli_help_shows_commands(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        output = result.output
        for command in ("init", "run", "list", "status", "verify", "restore"):
            assert command in output

    def test_cli_help_shows_description(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Barkup" in result.output

    def test_custom_config_option_is_recognized(self, tmp_path):
        # A valid existing config file should be accepted without errors.
        config_file = tmp_path / "barkup.config.toml"
        config_file.write_text("")

        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(config_file), "--help"])
        assert result.exit_code == 0

    def test_subcommands_are_registered(self):
        # Each command name maps to a callback in the group.
        names = {cmd.name for cmd in cli.commands.values()}
        assert names == {
            "init",
            "run",
            "list",
            "status",
            "verify",
            "restore",
            "profiles",
            "prune",
        }


class TestResolveProfileName:
    def test_cli_name_takes_precedence(self):
        config = _Config(profile_name="config_profile")
        assert resolve_profile_name("cli_profile", config) == "cli_profile"

    def test_uses_config_profile_when_no_cli_name(self):
        config = _Config(profile_name="config_profile")
        assert resolve_profile_name(None, config) == "config_profile"

    def test_defaults_to_default_when_nothing_specified(self):
        config = _Config(profile_name=None)
        assert resolve_profile_name(None, config) == "default"


class TestInitCommand:
    @staticmethod
    def _point_config_at(tmp_path, monkeypatch):
        target = tmp_path / "config.toml"
        monkeypatch.setattr("barkup.cli.get_user_config_path", lambda: target)
        monkeypatch.setattr("barkup.config.get_user_config_path", lambda: target)
        return target

    def test_creates_config_file_when_missing(self, tmp_path, monkeypatch):
        target = self._point_config_at(tmp_path, monkeypatch)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert target.exists()
        assert "[general]" in target.read_text()

    def test_overwrites_with_force_flag(self, tmp_path, monkeypatch):
        target = self._point_config_at(tmp_path, monkeypatch)
        target.write_text("# pre-existing config")

        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--force"])

        assert result.exit_code == 0
        assert "[general]" in target.read_text()

    def test_prompts_before_overwriting(self, tmp_path, monkeypatch):
        target = self._point_config_at(tmp_path, monkeypatch)
        original = "# pre-existing config"
        target.write_text(original)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="n\n")

        assert result.exit_code == 0
        assert target.read_text() == original
        assert "Aborted" in result.output

    def test_declines_overwrite_confirmation(self, tmp_path, monkeypatch):
        target = self._point_config_at(tmp_path, monkeypatch)
        original = "# pre-existing config"
        target.write_text(original)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="y\n")

        assert result.exit_code == 0
        assert "[general]" in target.read_text()


def _stats():
    return {
        "files_backed_up": 0,
        "new_files": 0,
        "modified_files": 0,
        "skipped_files": 0,
    }


class TestRunCommand:
    @staticmethod
    def _fake_config(monkeypatch, profile_name):
        config = _Config(profile_name=profile_name)
        monkeypatch.setattr("barkup.cli.load_config", lambda cli_path=None: config)
        return config

    def test_runs_backup_successfully(self, monkeypatch):
        self._fake_config(monkeypatch, "default")
        captured = {}

        def fake_run(cli_path=None, profile_name=None, skip_confirm=False):
            captured["profile_name"] = profile_name
            captured["skip_confirm"] = skip_confirm
            return {
                "files_backed_up": 2,
                "new_files": 1,
                "modified_files": 1,
                "skipped_files": 3,
            }

        monkeypatch.setattr("barkup.cli.run_barkup", fake_run)

        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        assert result.exit_code == 0
        assert captured["profile_name"] == "default"
        assert "Backup completed successfully" in result.output
        assert "New files: 1" in result.output
        assert "Modified files: 1" in result.output
        assert "Skipped (unchanged): 3" in result.output

    def test_yes_flag_skips_confirmation(self, monkeypatch):
        self._fake_config(monkeypatch, "default")
        captured = {}

        def fake_run(cli_path=None, profile_name=None, skip_confirm=False):
            captured["skip_confirm"] = skip_confirm
            return _stats()

        monkeypatch.setattr("barkup.cli.run_barkup", fake_run)

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--yes"])

        assert result.exit_code == 0
        assert captured["skip_confirm"] is True

    def test_name_flag_overrides_profile(self, monkeypatch):
        self._fake_config(monkeypatch, "default")
        captured = {}

        def fake_run(cli_path=None, profile_name=None, skip_confirm=False):
            captured["profile_name"] = profile_name
            return _stats()

        monkeypatch.setattr("barkup.cli.run_barkup", fake_run)

        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--name", "custom"])

        assert result.exit_code == 0
        assert captured["profile_name"] == "custom"
        assert "Running backup for profile: custom" in result.output

    def test_uses_config_profile_when_no_name_flag(self, monkeypatch):
        self._fake_config(monkeypatch, "myprofile")
        captured = {}

        def fake_run(cli_path=None, profile_name=None, skip_confirm=False):
            captured["profile_name"] = profile_name
            return _stats()

        monkeypatch.setattr("barkup.cli.run_barkup", fake_run)

        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        assert result.exit_code == 0
        assert captured["profile_name"] == "myprofile"

    def test_defaults_to_default_profile(self, monkeypatch):
        self._fake_config(monkeypatch, None)
        captured = {}

        def fake_run(cli_path=None, profile_name=None, skip_confirm=False):
            captured["profile_name"] = profile_name
            return _stats()

        monkeypatch.setattr("barkup.cli.run_barkup", fake_run)

        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        assert result.exit_code == 0
        assert captured["profile_name"] == "default"

    def test_keyboard_interrupt_exits_gracefully(self, monkeypatch):
        self._fake_config(monkeypatch, "default")

        def fake_run(cli_path=None, profile_name=None, skip_confirm=False):
            raise KeyboardInterrupt()

        monkeypatch.setattr("barkup.cli.run_barkup", fake_run)

        runner = CliRunner()
        result = runner.invoke(cli, ["run"])

        assert result.exit_code == 2
        assert "cancelled by user" in result.output


class TestListCommand:
    @staticmethod
    def _seed(monkeypatch):
        from barkup import database
        from barkup.database import open_connection, update_file_state
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        update_file_state(conn, "default", "/home/user/a.txt", "/bk/a.txt", "h1", 10)
        update_file_state(conn, "docs", "/home/user/b.txt", "/bk/b.txt", "h2", 20)
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        return conn

    def test_lists_all_profiles_when_name_omitted(self, monkeypatch):
        self._seed(monkeypatch)
        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "/home/user/a.txt" in result.output
        assert "/bk/a.txt" in result.output
        assert "/home/user/b.txt" in result.output
        assert "/bk/b.txt" in result.output

    def test_filters_by_name(self, monkeypatch):
        self._seed(monkeypatch)
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--name", "docs"])
        assert result.exit_code == 0
        assert "/home/user/b.txt" in result.output
        assert "/bk/b.txt" in result.output
        assert "/home/user/a.txt" not in result.output

    def test_empty_db_prints_message(self, monkeypatch):
        from barkup import database
        from barkup.database import open_connection
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No backups found." in result.output


class TestStatusCommand:
    @staticmethod
    def _seed(monkeypatch):
        """Set up in-memory DB with test data."""
        from barkup import database
        from barkup.database import open_connection, update_file_state
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        update_file_state(conn, "work", "/a.txt", "/bk/a.txt", "ha", 1024)
        update_file_state(conn, "work", "/b.txt", "/bk/b.txt", "hb", 2048)
        update_file_state(conn, "home", "/c.txt", "/bk/c.txt", "hc", 512)
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        return conn

    def test_no_backups_message(self, monkeypatch):
        from barkup import database
        from barkup.database import open_connection
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "No backups found." in result.output

    def test_single_profile_output(self, monkeypatch):
        from barkup import database
        from barkup.database import open_connection, update_file_state
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        update_file_state(conn, "docs", "/d.txt", "/bk/d.txt", "hd", 4096)
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Profile: docs" in result.output
        assert "Files: 1" in result.output
        assert "4.0 KB" in result.output

    def test_multiple_profiles(self, monkeypatch):
        self._seed(monkeypatch)
        runner = CliRunner()
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Profile: work" in result.output
        assert "Profile: home" in result.output
        assert "Files: 2" in result.output  # work has 2 files
        assert "Files: 1" in result.output  # home has 1 file

    def test_name_filter(self, monkeypatch):
        self._seed(monkeypatch)
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--name", "home"])
        assert result.exit_code == 0
        assert "Profile: home" in result.output
        assert "Profile: work" not in result.output
        assert "Files: 1" in result.output


class TestVerifyCommand:
    @staticmethod
    def _seed(monkeypatch, tmp_path):
        """Create two source files + real backup copies, then return handles."""
        from barkup import database
        from barkup.database import open_connection, update_file_state

        conn = open_connection(db_path=Path(":memory:"))
        # source files (verify now checks the backup copy, not the source)
        a = tmp_path / "a.txt"
        a.write_text("unchanged")
        b = tmp_path / "b.txt"
        b.write_text("good")
        # real backup copies that verify actually hashes
        ba = tmp_path / "bk_a.txt"
        ba.write_text("unchanged")
        bb = tmp_path / "bk_b.txt"
        bb.write_text("good")
        update_file_state(
            conn, "p", str(a), str(ba), calculate_file_hash(str(ba)), ba.stat().st_size
        )
        update_file_state(
            conn, "p", str(b), str(bb), calculate_file_hash(str(bb)), bb.stat().st_size
        )
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        return conn, ba, bb

    def test_empty_db_shows_message(self, monkeypatch):
        from barkup import database

        conn = open_connection(db_path=Path(":memory:"))
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        runner = CliRunner()
        result = runner.invoke(cli, ["verify"])
        assert result.exit_code == 0
        assert "No backups found." in result.output

    def test_all_ok_exits_zero(self, monkeypatch, tmp_path):
        _, ba, _ = self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["verify"])
        assert result.exit_code == 0
        assert "OK: 2" in result.output
        assert "Missing: 0" in result.output
        assert "Mismatched: 0" in result.output

    def test_mismatch_causes_nonzero_exit(self, monkeypatch, tmp_path):
        _, ba, bb = self._seed(monkeypatch, tmp_path)
        # corrupt the backup copy
        ba.write_text("corrupted")
        runner = CliRunner()
        result = runner.invoke(cli, ["verify"])
        assert result.exit_code == 1
        assert "Mismatched: 1" in result.output

    def test_missing_file_reported(self, monkeypatch, tmp_path):
        _, ba, bb = self._seed(monkeypatch, tmp_path)
        ba.unlink()
        runner = CliRunner()
        result = runner.invoke(cli, ["verify"])
        assert result.exit_code == 1
        assert "Missing: 1" in result.output


class TestRestoreCommand:
    @staticmethod
    def _seed(monkeypatch, tmp_path):
        """Create real backup files + DB rows; return handles.

        Uses a file-backed DB and routes ``database.open_connection`` to a
        fresh connection on that file each call, because the restore command
        opens and closes its own connection per invocation.
        """
        from barkup import database
        from barkup.database import open_connection, update_file_state

        db_path = tmp_path / "state.db"
        conn = open_connection(db_path=db_path)
        bk = tmp_path / "bk"
        bk.mkdir()
        a = tmp_path / "a.txt"
        a.write_text("alpha")
        ba = bk / "a.txt"
        ba.write_text("alpha")
        b = tmp_path / "b.txt"
        b.write_text("beta")
        bb = bk / "b.txt"
        bb.write_text("beta")
        update_file_state(conn, "p", str(a), str(ba), "ha", a.stat().st_size)
        update_file_state(conn, "p", str(b), str(bb), "hb", b.stat().st_size)
        monkeypatch.setattr(
            database,
            "open_connection",
            lambda *a, **k: open_connection(db_path=db_path),
        )
        return conn, a, b

    def test_missing_path_argument(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["restore"])
        assert result.exit_code == 1
        assert "PATH argument required" in result.output

    def test_all_requires_name(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "--all"])
        assert result.exit_code == 1
        assert "--name required" in result.output

    def test_restores_single_file(self, monkeypatch, tmp_path):
        _, a, _ = self._seed(monkeypatch, tmp_path)
        dest = tmp_path / "restored" / "a.txt"
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", str(a), "--to", str(dest)])
        assert result.exit_code == 0
        assert dest.is_file()
        assert dest.read_text() == "alpha"
        assert "Restored" in result.output

    def test_unknown_file_errors(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "/no/such/file.txt"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_restores_all_to_destination(self, monkeypatch, tmp_path):
        _, a, b = self._seed(monkeypatch, tmp_path)
        dest_root = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["restore", "--all", "--name", "p", "--to", str(dest_root)]
        )
        assert result.exit_code == 0
        rel_a = Path(str(a)).relative_to(Path(str(a)).anchor)
        rel_b = Path(str(b)).relative_to(Path(str(b)).anchor)
        assert (dest_root / rel_a).is_file()
        assert (dest_root / rel_b).is_file()
        assert "Restored 2 files" in result.output

    def test_all_reports_missing_backup(self, monkeypatch, tmp_path):
        from barkup import database
        from barkup.database import open_connection, update_file_state

        conn = open_connection(db_path=Path(":memory:"))
        missing_bk = tmp_path / "bk" / "gone.txt"
        update_file_state(conn, "p", str(tmp_path / "src.txt"), str(missing_bk), "h", 5)
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "--all", "--name", "p"])
        assert result.exit_code == 1
        assert "Failed to restore" in result.output

    def test_all_unknown_profile(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", "--all", "--name", "nope"])
        assert result.exit_code == 1
        assert "No backups found" in result.output


class TestProfilesCommand:
    @staticmethod
    def _seed(monkeypatch):
        from barkup import database
        from barkup.database import open_connection, update_file_state
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        update_file_state(conn, "work", "/a.txt", "/bk/a.txt", "ha", 1024)
        update_file_state(conn, "work", "/b.txt", "/bk/b.txt", "hb", 2048)
        update_file_state(conn, "home", "/c.txt", "/bk/c.txt", "hc", 512)
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        return conn

    def test_lists_all_profiles(self, monkeypatch):
        self._seed(monkeypatch)
        runner = CliRunner()
        result = runner.invoke(cli, ["profiles"])
        assert result.exit_code == 0
        assert "Backup Profiles:" in result.output
        assert "work" in result.output
        assert "home" in result.output
        assert "Files: 2" in result.output
        assert "Files: 1" in result.output

    def test_empty_db_prints_message(self, monkeypatch):
        from barkup import database
        from barkup.database import open_connection
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        runner = CliRunner()
        result = runner.invoke(cli, ["profiles"])
        assert result.exit_code == 0
        assert "No backup profiles found" in result.output


class TestRunValidation:
    @staticmethod
    def _write_config(tmp_path, sources, destination):
        cfg = tmp_path / "barkup.config.toml"
        src = ", ".join(f'"{s}"' for s in sources)
        cfg.write_text(
            "[general]\n"
            'profile_name = "default"\n'
            "dry_run = false\n"
            f"sources = [{src}]\n"
            "compression = false\n"
            "exclude = []\n"
            "[local]\n"
            f'destination = "{destination}"\n'
        )
        return cfg

    def test_empty_sources_exits_1(self, tmp_path):
        cfg = self._write_config(tmp_path, [], tmp_path / "dest")
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "run"])
        assert result.exit_code == 1
        assert "No backup sources" in result.output

    def test_empty_destination_exits_1(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        cfg = self._write_config(tmp_path, [str(src)], "")
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "run"])
        assert result.exit_code == 1
        assert "No backup destination" in result.output

    def test_destination_inside_source_exits_1(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        cfg = self._write_config(tmp_path, [str(src)], str(src))
        runner = CliRunner()
        result = runner.invoke(cli, ["--config", str(cfg), "run"])
        assert result.exit_code == 1
        assert "inside source" in result.output


class TestPruneCommand:
    @staticmethod
    def _seed(monkeypatch, tmp_path):
        from barkup import database
        from barkup.database import open_connection, update_file_state

        conn = open_connection(db_path=Path(":memory:"))
        live = tmp_path / "live.txt"
        live.write_text("x")
        gone = tmp_path / "gone.txt"  # source deleted -> orphan
        update_file_state(conn, "p", str(gone), "/bk/gone.txt", "h", 3)
        update_file_state(conn, "p", str(live), "/bk/live.txt", "h", 1)
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        return conn

    def test_dry_run_lists_orphans(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["prune"])
        assert result.exit_code == 0
        assert "Would remove 1 orphan record" in result.output
        assert "Re-run with --yes" in result.output

    def test_apply_removes_orphans(self, monkeypatch, tmp_path):
        self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["prune", "--yes"])
        assert result.exit_code == 0
        assert "Removed 1 orphan record" in result.output

    def test_nothing_to_prune_message(self, monkeypatch, tmp_path):
        from barkup import database
        from barkup.database import open_connection
        from pathlib import Path

        conn = open_connection(db_path=Path(":memory:"))
        monkeypatch.setattr(database, "open_connection", lambda *a, **k: conn)
        runner = CliRunner()
        result = runner.invoke(cli, ["prune"])
        assert result.exit_code == 0
        assert "Nothing to prune" in result.output


class TestRestoreOverwriteGuard:
    @staticmethod
    def _seed(monkeypatch, tmp_path):
        from barkup import database
        from barkup.database import open_connection, update_file_state

        db_path = tmp_path / "state.db"
        conn = open_connection(db_path=db_path)
        a = tmp_path / "a.txt"
        a.write_text("alpha")
        ba = tmp_path / "bk_a.txt"
        ba.write_text("alpha")
        b = tmp_path / "b.txt"
        b.write_text("beta")
        bb = tmp_path / "bk_b.txt"
        bb.write_text("beta")
        update_file_state(conn, "p", str(a), str(ba), "ha", a.stat().st_size)
        update_file_state(conn, "p", str(b), str(bb), "hb", b.stat().st_size)
        conn.close()
        monkeypatch.setattr(
            database,
            "open_connection",
            lambda *a, **k: open_connection(db_path=db_path),
        )
        return a

    def test_restore_onto_existing_requires_yes(self, monkeypatch, tmp_path):
        a = self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        # original `a` still exists on disk -> overwrite guard trips
        result = runner.invoke(cli, ["restore", str(a), "--name", "p"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_restore_onto_existing_with_yes(self, monkeypatch, tmp_path):
        a = self._seed(monkeypatch, tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["restore", str(a), "--name", "p", "--yes"])
        assert result.exit_code == 0
        assert "Restored" in result.output
