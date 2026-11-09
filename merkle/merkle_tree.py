"""Domain separated leaves (00) and parents (01); duplicate odd last nodes."""
from build.build_artifact import canonical_json, normalize_manifest
from build.hash_utils import hash_bytes, validate_hash


def parent_hash(left: str, right: str) -> str:
    return hash_bytes(b"\x01" + bytes.fromhex(validate_hash(left)) + bytes.fromhex(validate_hash(right)))


def entries_from_manifest(manifest: dict) -> list:
    m = normalize_manifest(manifest)
    entries = [[key, m[key]] for key in ("version", "artifact_name", "artifact_hash", "commit_hash")]
    entries.extend(["dependency", dep] for dep in m["dependencies"])
    entries.extend([["timestamp", m["timestamp"]], ["builder_id", m["builder_id"]]])
    return entries


def leaves_from_manifest(manifest: dict) -> list[str]:
    return [hash_bytes(b"\x00" + canonical_json(entry)) for entry in entries_from_manifest(manifest)]


def build_tree(leaf_hashes: list[str]) -> list[list[str]]:
    if not leaf_hashes:
        raise ValueError("A Merkle tree needs at least one leaf")
    tree = [[validate_hash(h) for h in leaf_hashes]]
    while len(tree[-1]) > 1:
        level = tree[-1]
        tree.append([parent_hash(level[i], level[i + 1] if i + 1 < len(level) else level[i])
                     for i in range(0, len(level), 2)])
    return tree


def get_root(tree: list[list[str]]) -> str:
    if not tree or len(tree[-1]) != 1:
        raise ValueError("Invalid Merkle tree")
    return validate_hash(tree[-1][0])
