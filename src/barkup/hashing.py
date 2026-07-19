"""
SHA256 file hashing for change detection.

Reads files in 64KB chunks so large files (videos, disk images, etc.)
don't blow up memory. The hex digest is used as the identity check
in the state database — if the hash differs, the file has changed.
"""

import hashlib
from pathlib import Path

CHUNK_SIZE = 65_536  # 64KB


def calculate_file_hash(file_path: Path) -> str:
    """Return the SHA256 hex digest of a file's contents."""
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha256.update(chunk)

    return sha256.hexdigest()
