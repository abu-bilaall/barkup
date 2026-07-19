from pathlib import Path


from barkup.dry_run import dry_run_output, dry_local_run, dry_cloud_run
from barkup.exclude_patterns import FileToBackup


def _file(path: Path, source: Path, is_dir: bool) -> FileToBackup:
    return FileToBackup(path=path, source=source, source_is_dir=is_dir)


class TestDryRunOutput:
    def test_single_file_source_labeled_as_file(self, capsys, tmp_path):
        f = tmp_path / "note.txt"
        f.write_text("x")
        files = [_file(f, f, is_dir=False)]

        dry_run_output(files)
        out = capsys.readouterr().out

        assert "📄 File:" in out
        assert str(f) in out

    def test_directory_source_lists_relative_paths(self, capsys, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("a")
        b.write_text("b")
        files = [_file(a, tmp_path, is_dir=True), _file(b, tmp_path, is_dir=True)]

        dry_run_output(files)
        out = capsys.readouterr().out

        assert "📁 Directory:" in out
        # Relative names (not absolute paths) are printed under the directory.
        assert "   - a.txt" in out
        assert "   - b.txt" in out
        # The absolute source path appears only in the directory header, never
        # in the indented file entries.
        assert "   - " + str(tmp_path) not in out

    def test_multiple_sources_grouped(self, capsys, tmp_path):
        f1 = tmp_path / "one.txt"
        f1.write_text("1")
        d2 = tmp_path / "dir"
        d2.mkdir()
        (d2 / "two.txt").write_text("2")

        files = [
            _file(f1, f1, is_dir=False),
            _file(d2 / "two.txt", d2, is_dir=True),
        ]

        dry_run_output(files)
        out = capsys.readouterr().out

        assert "📄 File:" in out
        assert "📁 Directory:" in out

    def test_truncates_beyond_five_files(self, capsys, tmp_path):
        for i in range(8):
            (tmp_path / f"f{i}.txt").write_text(str(i))
        files = [
            _file(p, tmp_path, is_dir=True) for p in sorted(tmp_path.glob("*.txt"))
        ]

        dry_run_output(files)
        out = capsys.readouterr().out

        assert "... and 3 more files" in out
        # Only 5 individual entries printed, plus the directory header.
        assert out.count("   - ") == 5

    def test_file_vs_directory_labeling(self, capsys, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("x")
        d = tmp_path / "sub"
        d.mkdir()
        (d / "y.txt").write_text("y")

        files = [
            _file(f, f, is_dir=False),
            _file(d / "y.txt", d, is_dir=True),
        ]

        dry_run_output(files)
        out = capsys.readouterr().out

        assert "📄 File:" in out
        assert "📁 Directory:" in out


class TestDryLocalRun:
    def test_shows_file_count(self, capsys, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("a")
        files = [_file(f, f, is_dir=False)]

        dry_local_run(files, "/backup/dest")
        out = capsys.readouterr().out

        assert "Local Backup" in out
        assert "Found 1 files to backup locally" in out

    def test_shows_destination(self, capsys, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("a")
        files = [_file(f, f, is_dir=False)]

        dry_local_run(files, "/backup/dest")
        out = capsys.readouterr().out

        assert "Destination: /backup/dest" in out

    def test_empty_files_list(self, capsys):
        dry_local_run([], "/backup/dest")
        out = capsys.readouterr().out

        assert "No files to backup locally." in out
        assert "Destination" not in out


class TestDryCloudRun:
    def test_shows_file_count(self, capsys, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("a")
        files = [_file(f, f, is_dir=False)]

        dry_cloud_run(files, "remote:/folder")
        out = capsys.readouterr().out

        assert "Cloud Backup" in out
        assert "Found 1 files to backup to cloud" in out

    def test_shows_destination(self, capsys, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("a")
        files = [_file(f, f, is_dir=False)]

        dry_cloud_run(files, "remote:/folder")
        out = capsys.readouterr().out

        assert "Destination: remote:/folder" in out

    def test_empty_files_list(self, capsys):
        dry_cloud_run([], "remote:/folder")
        out = capsys.readouterr().out

        assert "No files to backup to cloud." in out
        assert "Destination" not in out
