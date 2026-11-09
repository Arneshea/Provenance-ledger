"""The two project flows, kept independent of the command-line interface."""
from dataclasses import asdict, dataclass
from pathlib import Path
from eth_account import Account
from build.build_artifact import create_artifact, create_manifest, normalize_manifest, save_manifest
from build.hash_utils import hash_file, validate_hash
from merkle.merkle_tree import build_tree, get_root, leaves_from_manifest
from sign.signatures import sign_root, verify_signature


@dataclass
class VerificationResult:
    passed: bool = False
    on_chain_found: bool = False
    pipeline_authorized: bool = False
    artifact_hash_ok: bool = False
    merkle_root_ok: bool = False
    signature_ok: bool = False
    reason: str = "Verification has not completed"

    def to_dict(self):
        return asdict(self)


def register_build(source_folder, artifact_path, commit_hash, dependencies, private_key,
                   registry, storage):
    signer = Account.from_key(private_key).address
    if not registry.is_authorized(signer):
        raise ValueError("Pipeline address is not authorized")
    artifact = create_artifact(source_folder, artifact_path)
    return register_artifact(artifact, commit_hash, dependencies, private_key, registry, storage)


def register_artifact(artifact_path, commit_hash, dependencies, private_key, registry, storage):
    """Register an existing artifact without repacking or changing its bytes."""
    signer = Account.from_key(private_key).address
    if not registry.is_authorized(signer):
        raise ValueError("Pipeline address is not authorized")
    artifact = Path(artifact_path)
    manifest = create_manifest(artifact, commit_hash, dependencies, signer)
    if registry.get_build(manifest["artifact_hash"]):
        raise ValueError("This artifact is already registered; records cannot be overwritten")
    root = get_root(build_tree(leaves_from_manifest(manifest)))
    signature = sign_root(root, private_key)
    cid = storage.upload_bundle(manifest, signature, signer)
    receipt = registry.register_build(manifest["artifact_hash"], root, cid)
    manifest_path = save_manifest(manifest, Path(artifact).with_suffix(".manifest.json"))
    return {"artifact": str(artifact), "manifest": str(manifest_path),
            "artifact_hash": manifest["artifact_hash"], "merkle_root": root,
            "cid": cid, "transaction_hash": receipt["transactionHash"].hex(), "pipeline": signer}


def verify_build(artifact_path, registry, storage, expected_hash=None):
    result = VerificationResult()
    try:
        actual_hash = hash_file(artifact_path)
        lookup_hash = validate_hash(expected_hash) if expected_hash else actual_hash
        record = registry.get_build(lookup_hash)
        if record is None:
            result.reason = "No on-chain record for this artifact hash"
            return result
        result.on_chain_found = True
        result.pipeline_authorized = registry.is_authorized(record["pipeline"])
        bundle = storage.fetch_bundle(record["cid"])
        manifest = normalize_manifest(bundle["manifest"])
        result.artifact_hash_ok = actual_hash == manifest["artifact_hash"] == lookup_hash
        root = get_root(build_tree(leaves_from_manifest(manifest)))
        result.merkle_root_ok = root == record["merkle_root"] == bundle["merkle_root"]
        result.signature_ok = (
            manifest["builder_id"].lower() == record["pipeline"].lower()
            and bundle["signer"].lower() == record["pipeline"].lower()
            and verify_signature(record["merkle_root"], bundle["signature"], record["pipeline"]))
        checks = {"pipeline authorization": result.pipeline_authorized,
                  "artifact hash": result.artifact_hash_ok,
                  "Merkle root": result.merkle_root_ok, "pipeline signature": result.signature_ok}
        result.passed = all(checks.values())
        result.reason = "All checks passed: deployment allowed" if result.passed else (
            "Deployment blocked: " + ", ".join(name for name, ok in checks.items() if not ok) + " failed")
    except Exception as error:
        # At the deploy gate even an unexpected decoding/network error MUST block.
        result.reason = f"Deployment blocked: {type(error).__name__}: {error}"
    return result


def tamper_demo(artifact_path, registry, storage):
    original = Path(artifact_path)
    clean = verify_build(original, registry, storage)
    if not clean.passed:
        raise ValueError(f"Demo requires a clean registered artifact: {clean.reason}")
    # Exclusive creation keeps both the original and an earlier demo copy intact.
    tampered = original.with_name(original.stem + ".tampered" + original.suffix)
    with tampered.open("xb") as stream:
        stream.write(original.read_bytes() + b"\nTAMPERED AFTER BUILD\n")
    modified = verify_build(tampered, registry, storage, expected_hash=hash_file(original))
    return {"clean": clean.to_dict(), "tampered": modified.to_dict(), "tampered_copy": str(tampered)}
