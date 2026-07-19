import hashlib
from barkup.hashing import calculate_file_hash, CHUNK_SIZE


class TestCalculateFileHash:
    """Test SHA256 hashing of file contents."""

    def test_returns_correct_sha256(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("hello world")

        result = calculate_file_hash(f)
        expected = hashlib.sha256(b"hello world").hexdigest()

        assert result == expected

    def test_same_content_same_hash(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("identical")
        b.write_text("identical")

        assert calculate_file_hash(a) == calculate_file_hash(b)

    def test_different_content_different_hash(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("content A")
        b.write_text("content B")

        assert calculate_file_hash(a) != calculate_file_hash(b)

    def test_handles_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")

        result = calculate_file_hash(f)
        expected = hashlib.sha256(b"").hexdigest()

        assert result == expected

    def test_handles_large_file(self, tmp_path):
        """File larger than CHUNK_SIZE to exercise chunked reading."""
        f = tmp_path / "large.bin"
        # Write 3 chunks worth of data
        data = b"x" * (CHUNK_SIZE * 3 + 42)
        f.write_bytes(data)

        result = calculate_file_hash(f)
        expected = hashlib.sha256(data).hexdigest()

        assert result == expected

    def test_binary_file(self, tmp_path):
        """Non-text content (null bytes, high bytes)."""
        f = tmp_path / "binary.bin"
        data = bytes(range(256)) * 10
        f.write_bytes(data)

        result = calculate_file_hash(f)
        expected = hashlib.sha256(data).hexdigest()

        assert result == expected
