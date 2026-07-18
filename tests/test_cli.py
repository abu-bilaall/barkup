"""
Tests for the CLI command structure

Covers command registration and the shared profile-resolution helper.
"""

from click.testing import CliRunner

from cli import cli, resolve_profile_name


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
        assert names == {"init", "run", "list", "status", "verify", "restore"}


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
        monkeypatch.setattr("cli.get_user_config_path", lambda: target)
        monkeypatch.setattr("config.get_user_config_path", lambda: target)
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
