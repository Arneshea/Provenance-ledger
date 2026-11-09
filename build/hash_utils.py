"""All project hashes are SHA-256, represented as lowercase hex."""
import hashlib
import re


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_string(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_hash(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Expected a lowercase 64-character SHA-256 hash")
    return value
