import pytest
from barkup import barkup_file, barkup_directory

def test_barkup_file(tmp_path):
    # Arrange
    src = tmp_path / "file.txt"
    src.write_text("woof")

    dest = tmp_path / "backup"

    # Act
    barkup_file(str(src), str(dest))

    # Assert
    copied = dest / "file.txt"
    assert copied.exists()
    assert copied.read_text() == "woof"

def test_barkup_file_src_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        barkup_file(str(tmp_path / "nonexistent"), str(tmp_path / "backup"))

def test_barkup_file_src_is_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    with pytest.raises(FileNotFoundError):
        barkup_file(str(src), str(tmp_path / "backup"))

def test_barkup_file_dest_is_file(tmp_path):
    src = tmp_path / "file.txt"
    src.write_text("woof")

    dest = tmp_path / "backup"
    dest.write_text("I'm a file")

    with pytest.raises(FileExistsError):
        barkup_file(str(src), str(dest))

def test_barkup_file_overwrite(tmp_path):
    src = tmp_path / "file.txt"
    src.write_text("new_woof")

    dest = tmp_path / "backup"
    dest.mkdir()
    (dest / "file.txt").write_text("old_woof")

    barkup_file(str(src), str(dest))

    copied = dest / "file.txt"
    assert copied.read_text() == "new_woof"


def test_barkup_directory(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    (src / "a.txt").write_text("A")

    sub = src / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("B")

    dest = tmp_path / "dest"

    barkup_directory(str(src), str(dest))

    assert (dest / "src" / "a.txt").exists()
    assert (dest / "src" / "sub" / "b.txt").exists()

def test_barkup_directory_src_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        barkup_directory(str(tmp_path / "nonexistent"), str(tmp_path / "backup"))

def test_barkup_directory_src_is_file(tmp_path):
    src = tmp_path / "file.txt"
    src.write_text("woof")
    with pytest.raises(FileNotFoundError):
        barkup_directory(str(src), str(tmp_path / "backup"))

def test_barkup_directory_dest_is_file(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("A")

    dest = tmp_path / "dest"
    dest.write_text("I'm a file")

    with pytest.raises(FileExistsError):
        barkup_directory(str(src), str(dest))

def test_barkup_directory_empty_src(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "dest"

    barkup_directory(str(src), str(dest))

    assert (dest / "src").is_dir()
    assert not any((dest / "src").iterdir())

def test_barkup_directory_merges_content(tmp_path):
    # Arrange: Create a source directory with one file
    src = tmp_path / "src"
    src.mkdir()
    (src / "b.txt").write_text("B")

    # Arrange: Create a destination that already has a directory with a file
    dest = tmp_path / "dest"
    dest_src = dest / "src"
    dest_src.mkdir(parents=True)
    (dest_src / "a.txt").write_text("A")

    # Act
    barkup_directory(str(src), str(dest))

    # Assert
    assert (dest_src / "a.txt").read_text() == "A"
    assert (dest_src / "b.txt").read_text() == "B"