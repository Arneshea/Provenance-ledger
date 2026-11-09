import copy
import json
from pathlib import Path
import pytest
from eth_account import Account
from build.hash_utils import hash_bytes, hash_file, hash_string
from build.build_artifact import create_artifact, create_manifest, normalize_manifest, canonical_json
from merkle.merkle_tree import build_tree, get_root, leaves_from_manifest
from merkle.merkle_proof import generate_proof, verify_proof
from sign.signatures import generate_keys, sign_root, verify_signature
from ipfs.ipfs_client import make_bundle
from verify.pipeline import register_build, verify_build, tamper_demo


@pytest.fixture
def artifact(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.txt").write_text("trusted application")
    return create_artifact(source, tmp_path / "app.zip")


@pytest.fixture
def manifest(artifact):
    return create_manifest(artifact, "a" * 40, [
        {"name": "zeta", "version": "1", "hash": "1" * 64},
        {"name": "alpha", "version": "2", "hash": "2" * 64}], "pipeline")


def test_hashing(artifact):
    assert hash_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert hash_string("abc") == hash_bytes(b"abc")
    assert hash_file(artifact) == hash_bytes(artifact.read_bytes())
    assert hash_bytes(b"abc") != hash_bytes(b"abd")


def test_packaging_is_deterministic(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_bytes(b"sample")
    a = create_artifact(source, tmp_path / "a.zip")
    b = create_artifact(source, tmp_path / "b.zip")
    assert a.read_bytes() == b.read_bytes()
    with pytest.raises(ValueError):
        create_artifact(source, source / "bad.zip")


def test_manifest_canonical_order(manifest):
    shuffled = dict(reversed(list(manifest.items())))
    shuffled["dependencies"] = list(reversed(shuffled["dependencies"]))
    assert canonical_json(normalize_manifest(shuffled)) == canonical_json(manifest)
    assert leaves_from_manifest(shuffled) == leaves_from_manifest(manifest)


@pytest.mark.parametrize("field,value", [("version", "2"), ("artifact_hash", "BAD"),
    ("timestamp", "today"), ("commit_hash", "short"), ("dependencies", {}), ("builder_id", "")])
def test_manifest_rejects_malformed(manifest, field, value):
    manifest[field] = value
    with pytest.raises((ValueError, TypeError)):
        leaves_from_manifest(manifest)


@pytest.mark.parametrize("count", [1, 2, 3, 5, 6, 9])
def test_merkle_proofs_for_every_leaf(count):
    leaves = [hash_string(str(i)) for i in range(count)]
    tree = build_tree(leaves)
    for i, leaf in enumerate(leaves):
        proof = generate_proof(tree, i)
        assert verify_proof(leaf, proof, get_root(tree))
        assert not verify_proof(hash_string("tampered"), proof, get_root(tree))
    with pytest.raises(ValueError):
        generate_proof(tree, count)


def test_merkle_changes_with_manifest(manifest):
    before = get_root(build_tree(leaves_from_manifest(manifest)))
    manifest["dependencies"][0]["version"] = "99"
    assert before != get_root(build_tree(leaves_from_manifest(manifest)))


def test_bad_tree_and_proof():
    with pytest.raises(ValueError):
        build_tree([])
    assert not verify_proof("0" * 64, [("1" * 64, "up")], "2" * 64)


def test_signature_identity_and_tampering():
    signer, attacker = Account.create(), Account.create()
    root = hash_string("manifest")
    signature = sign_root(root, signer.key)
    assert verify_signature(root, signature, signer.address)
    assert not verify_signature(root, signature, attacker.address)
    assert not verify_signature(hash_string("modified"), signature, signer.address)
    assert not verify_signature(root, "not a signature", signer.address)


def test_key_generation_never_overwrites(tmp_path):
    generate_keys(tmp_path)
    original = (tmp_path / "pipeline.key").read_bytes()
    with pytest.raises(FileExistsError):
        generate_keys(tmp_path)
    assert (tmp_path / "pipeline.key").read_bytes() == original


class MemoryStorage:
    """Test double only; production always uses Kubo."""
    def upload_bundle(self, manifest, signature, signer):
        self.bundle = make_bundle(manifest, signature, signer)
        return "test-cid"

    def fetch_bundle(self, cid):
        return copy.deepcopy(self.bundle)


class MemoryRegistry:
    """Test double only; production always uses the Solidity contract."""
    def __init__(self, address):
        self.address, self.records, self.authorized = address, {}, True

    def is_authorized(self, address):
        return self.authorized and address == self.address

    def get_build(self, digest):
        return self.records.get(digest)

    def register_build(self, digest, root, cid):
        self.records[digest] = {"merkle_root": root, "cid": cid, "pipeline": self.address, "timestamp": 1}
        return {"transactionHash": b"test-transaction"}


@pytest.fixture
def registered(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app").write_text("clean")
    account = Account.create()
    registry, storage = MemoryRegistry(account.address), MemoryStorage()
    result = register_build(source, tmp_path / "app.zip", "a" * 40, [], account.key, registry, storage)
    return Path(result["artifact"]), registry, storage


def test_full_clean_and_tamper_flow(registered):
    path, registry, storage = registered
    before = path.read_bytes()
    assert verify_build(path, registry, storage).passed
    demo = tamper_demo(path, registry, storage)
    assert demo["clean"]["passed"]
    assert not demo["tampered"]["passed"]
    assert not demo["tampered"]["artifact_hash_ok"]
    assert demo["tampered"]["merkle_root_ok"]
    assert path.read_bytes() == before
    assert not verify_build(demo["tampered_copy"], registry, storage).on_chain_found


@pytest.mark.parametrize("attack", ["manifest", "signature", "signer", "revoked", "storage_down", "malformed"])
def test_gate_blocks_attacks(registered, attack):
    path, registry, storage = registered
    if attack == "manifest":
        storage.bundle["manifest"]["commit_hash"] = "b" * 40
    elif attack == "signature":
        storage.bundle["signature"] = sign_root(storage.bundle["merkle_root"], Account.create().key)
    elif attack == "signer":
        storage.bundle["signer"] = Account.create().address
    elif attack == "revoked":
        registry.authorized = False
    elif attack == "storage_down":
        storage.fetch_bundle = lambda _: (_ for _ in ()).throw(RuntimeError("IPFS offline"))
    else:
        storage.bundle["manifest"] = {}
    assert not verify_build(path, registry, storage).passed


def test_missing_artifact_is_blocked(registered):
    path, registry, storage = registered
    assert not verify_build(path.parent / "missing.zip", registry, storage).passed
