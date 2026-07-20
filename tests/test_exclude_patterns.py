import pytest
from pathlib import Path

from barkup.exclude_patterns import (
    scan_sources,
    should_exclude,
    resolve_excluded,
)
from barkup.config_resolvers import ResolvedLocalConfig


class TestScanSources:
    def test_single_file_source(self, tmp_path):
        src = tmp_path / "note.txt"
        src.write_text("hello")

        result = scan_sources([str(src)])

        assert len(result) == 1
        assert result[0].path == src
        assert result[0].source == src
        assert result[0].source_is_dir is False

    def test_directory_source_lists_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        result = scan_sources([str(tmp_path)])

        names = sorted(f.path.name for f in result)
        assert names == ["a.txt", "b.txt"]
        for f in result:
            assert f.source == tmp_path
            assert f.source_is_dir is True

    def test_nested_directory_source_recurses(self, tmp_path):
        nested = tmp_path / "sub" / "deep"
        nested.mkdir(parents=True)
        (tmp_path / "top.txt").write_text("t")
        (nested / "inner.txt").write_text("i")

        result = scan_sources([str(tmp_path)])

        names = sorted(f.path.name for f in result)
        assert names == ["inner.txt", "top.txt"]

    def test_directory_source_ignores_subdirectories(self, tmp_path):
        (tmp_path / "file.txt").write_text("f")
        (tmp_path / "emptydir").mkdir()

        result = scan_sources([str(tmp_path)])

        # Directories themselves are never returned, only files.
        assert [f.path.name for f in result] == ["file.txt"]

    def test_preserves_multiple_sources_order(self, tmp_path):
        f1 = tmp_path / "one.txt"
        f1.write_text("1")
        other = tmp_path / "dir"
        other.mkdir()
        (other / "two.txt").write_text("2")

        result = scan_sources([str(f1), str(other)])

        assert result[0].path == f1
        assert result[1].path.name == "two.txt"

    def test_nonexistent_source_raises(self, tmp_path):
        missing = tmp_path / "does_not_exist"

        with pytest.raises(FileNotFoundError):
            scan_sources([str(missing)])

    def test_expands_user_path(self, tmp_path, monkeypatch):
        # Build a target under HOME and reference it via ~. expanduser() reads
        # the HOME environment variable, not Path.home().
        target = tmp_path / ".barkup_test_scan"
        target.write_text("x")
        monkeypatch.setenv("HOME", str(tmp_path))

        result = scan_sources(["~/.barkup_test_scan"])

        assert len(result) == 1
        assert result[0].path == target

    def test_symlink_file_is_followed(self, tmp_path):
        real = tmp_path / "real.txt"
        real.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to(real)

        # scan_sources calls resolve(), so the symlink is followed and the
        # resolved (real) path is what gets backed up.
        result = scan_sources([str(link)])

        assert len(result) == 1
        assert result[0].path == real


class TestShouldExclude:
    def test_filename_match(self):
        f = Path("/tmp/logs/app.log")
        assert should_exclude(f, ["*.log"]) is True

    def test_path_component_match(self):
        f = Path("/tmp/project/.git/config")
        assert should_exclude(f, [".git"]) is True

    def test_directory_component_match(self):
        f = Path("/tmp/project/__pycache__/mod.pyc")
        assert should_exclude(f, ["__pycache__"]) is True

    def test_no_match_returns_false(self):
        f = Path("/tmp/docs/readme.md")
        assert should_exclude(f, ["*.log", ".git"]) is False

    def test_multiple_patterns_first_wins(self):
        f = Path("/tmp/a.txt")
        assert should_exclude(f, ["*.log", "*.txt"]) is True

    def test_empty_patterns_never_excludes(self):
        f = Path("/tmp/a.log")
        assert should_exclude(f, []) is False

    def test_unicode_filename_match(self):
        f = Path("/tmp/файл.log")
        assert should_exclude(f, ["*.log"]) is True


class TestResolveExcluded:
    def _make_config(self, sources, exclude):
        return ResolvedLocalConfig(
            profile_name="default",
            dry_run=False,
            destination="/backup",
            sources=sources,
            compression=False,
            exclude=exclude,
        )

    def test_filters_out_excluded_files(self, tmp_path):
        (tmp_path / "keep.txt").write_text("k")
        (tmp_path / "skip.log").write_text("s")

        config = self._make_config(sources=[str(tmp_path)], exclude=["*.log"])
        result = resolve_excluded(config)

        names = [f.path.name for f in result]
        assert names == ["keep.txt"]

    def test_empty_exclude_keeps_all(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.log").write_text("b")

        config = self._make_config(sources=[str(tmp_path)], exclude=[])
        result = resolve_excluded(config)

        assert len(result) == 2

    def test_all_files_excluded(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        config = self._make_config(sources=[str(tmp_path)], exclude=["*.txt"])
        result = resolve_excluded(config)

        assert result == []

    def test_excludes_by_path_component(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (tmp_path / "mod.py").write_text("m")
        (cache / "mod.cpython-312.pyc").write_text("c")

        config = self._make_config(sources=[str(tmp_path)], exclude=["__pycache__"])
        result = resolve_excluded(config)

        assert [f.path.name for f in result] == ["mod.py"]


class TestDotfileExclusion:
    def test_dotfiles_excluded_by_default(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / ".hidden.txt").write_text("secret")
        (tmp_path / ".env").write_text("TOKEN=1")
        dotdir = tmp_path / ".git"
        dotdir.mkdir()
        (dotdir / "config").write_text("x")
        result = scan_sources([str(tmp_path)])
        names = {f.path.name for f in result}
        assert names == {"a.txt"}

    def test_explicit_dotfile_included(self, tmp_path):
        dotfile = tmp_path / ".bashrc"
        dotfile.write_text("export PATH=.")
        result = scan_sources([str(dotfile)])
        assert len(result) == 1
        assert result[0].path == dotfile

    def test_explicit_dotfile_dir_included_whole(self, tmp_path):
        dotdir = tmp_path / ".config"
        dotdir.mkdir()
        (dotdir / "settings.json").write_text("{}")
        nested = dotdir / ".secret"
        nested.mkdir()
        (nested / "token").write_text("x")
        result = scan_sources([str(dotdir)])
        names = {f.path.name for f in result}
        assert names == {"settings.json", "token"}

    def test_resolve_excluded_also_skips_dotfiles(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / ".hidden").write_text("h")
        cfg = ResolvedLocalConfig(
            profile_name="p",
            dry_run=False,
            destination="/tmp/bk",
            sources=[str(tmp_path)],
            compression=False,
            exclude=[],
        )
        result = resolve_excluded(cfg)
        assert [f.path.name for f in result] == ["a.txt"]
