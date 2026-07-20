"""ZIP compression helpers for barkup backups.

Barkup stores one ZIP archive per source file when compression is enabled.
Already-compressed formats are skipped (see ``COMPRESSED_EXTENSIONS``) because
re-compressing them wastes CPU and yields no space savings. Restore reads the
``compressed`` flag from the state DB to decide whether to decompress.
"""

from pathlib import Path

import zipfile

COMPRESSED_EXTENSIONS = {
    ".zip",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
    ".mp3",
    ".flac",
    ".ogg",
    ".m4a",
}


def should_compress(file_path: Path) -> bool:
    """Return True if ``file_path`` is a candidate for ZIP compression.

    Already-compressed formats (archives, common media) return False.
    Comparison is case-insensitive.
    """
    return file_path.suffix.lower() not in COMPRESSED_EXTENSIONS


def compress_file(src: Path, dest_zip: Path) -> Path:
    """Compress a single file into a ZIP archive at ``dest_zip``.

    The archive stores the file under its original base name (``arcname``),
    so restore can extract it back to that name regardless of the ZIP's path.
    """
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(src, arcname=src.name)
    return dest_zip


def decompress_file(zip_path: Path, dest: Path) -> Path:
    """Extract the single member of a barkup-created ZIP to ``dest``.

    Barkup archives contain exactly one file, so only the first member is
    extracted; its original name is ignored in favour of ``dest``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zipf:
        members = zipf.namelist()
        if not members:
            raise ValueError(f"Archive contains no files: {zip_path}")
        with zipf.open(members[0]) as src, dest.open("wb") as out:
            out.write(src.read())
    return dest
