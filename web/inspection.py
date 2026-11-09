"""Explain actual verifier evidence and compare ZIP members without extracting."""
import copy
import difflib
import zipfile
from pathlib import Path
from build.hash_utils import hash_bytes, hash_file
from merkle.merkle_tree import build_tree, get_root, leaves_from_manifest, entries_from_manifest
from merkle.merkle_proof import generate_proof, verify_proof
from verify.pipeline import verify_build

MAX_SIZE = 12 * 1024 * 1024


def zip_inventory(path):
    if not zipfile.is_zipfile(path):
        return None
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > 500 or sum(m.file_size for m in members) > 32 * 1024 * 1024:
            raise ValueError("ZIP comparison limit: 500 files / 32 MiB uncompressed")
        names, rows = set(), []
        for member in members:
            if member.filename in names:
                raise ValueError("ZIP contains ambiguous duplicate filenames")
            names.add(member.filename)
            if not member.is_dir():
                rows.append({"name": member.filename, "size": member.file_size,
                             "hash": hash_bytes(archive.read(member))})
        return rows


def compare_artifacts(original, candidate):
    a, b = Path(original).read_bytes(), Path(candidate).read_bytes()
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    if first is None and len(a) != len(b):
        first = min(len(a), len(b))
    comparison = {"original_size": len(a), "candidate_size": len(b), "first_changed_byte": first,
                  "files": [], "note": "Byte offsets are zero-based. This comparison cannot identify who changed a file or when."}
    try:
        left, right = zip_inventory(original), zip_inventory(candidate)
        if left is None or right is None:
            comparison["note"] = ("File bytes match. " if first is None else "File bytes differ. ") + "Member-level comparison requires two readable ZIP archives."
        else:
            left, right = {r["name"]: r for r in left}, {r["name"]: r for r in right}
            for name in sorted(left.keys() | right.keys()):
                before, after = left.get(name), right.get(name)
                status = "added" if before is None else "removed" if after is None else (
                    "unchanged" if before["hash"] == after["hash"] else "modified")
                comparison["files"].append({"name": name, "status": status,
                                            "before": before, "after": after})
                if status == "modified" and max(before["size"], after["size"]) <= 65536:
                    with zipfile.ZipFile(original) as old, zipfile.ZipFile(candidate) as new:
                        old_bytes, new_bytes = old.read(name), new.read(name)
                    try:
                        old_text, new_text = old_bytes.decode("utf-8"), new_bytes.decode("utf-8")
                        if "\x00" not in old_text + new_text:
                            lines = list(difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                         fromfile="registered/" + name, tofile="received/" + name, lineterm=""))
                            comparison["files"][-1]["diff"] = "\n".join(lines[:120])
                            comparison["files"][-1]["diff_truncated"] = len(lines) > 120
                    except UnicodeDecodeError:
                        pass
            if first is not None and all(r["status"] == "unchanged" for r in comparison["files"]):
                comparison["note"] = "ZIP container bytes changed, but file contents match. Metadata, compression, or appended bytes may have changed."
    except (ValueError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        comparison["note"] = f"Artifact hash still detects changes; ZIP detail unavailable: {error}"
    return comparison


def inspect_artifact(path, registry, storage, expected_hash=None, baseline=None):
    """Reuse the production gate while recording which external steps it reached."""
    evidence = {"actual_hash": hash_file(path), "record": None, "bundle": None}

    class RecordedRegistry:
        def get_build(self, digest):
            evidence["expected_hash"] = digest
            evidence["record"] = registry.get_build(digest)
            return evidence["record"]

        def is_authorized(self, address):
            return registry.is_authorized(address)

    class RecordedStorage:
        def fetch_bundle(self, cid):
            evidence["bundle"] = storage.fetch_bundle(cid)
            return evidence["bundle"]

    result = verify_build(path, RecordedRegistry(), RecordedStorage(), expected_hash)
    steps = []
    labels = [("on_chain_found", "Registry lookup", "Find the approved artifact hash in the immutable contract record."),
              ("pipeline_authorized", "Pipeline authorization", "Check whether the registering pipeline is still authorized."),
              ("artifact_hash_ok", "Artifact fingerprint", "Compare SHA-256 of the received bytes with the approved hash and manifest."),
              ("merkle_root_ok", "Manifest integrity", "Rebuild the Merkle tree and compare its root with the on-chain root."),
              ("signature_ok", "Signer identity", "Recover the root signer and compare it with the on-chain pipeline address.")]
    bundle = evidence["bundle"]
    computed_root = None
    if bundle:
        try:
            computed_root = get_root(build_tree(leaves_from_manifest(bundle["manifest"])))
        except (ValueError, TypeError, KeyError):
            pass
    for key, title, detail in labels:
        reached = key == "on_chain_found" or (key == "pipeline_authorized" and evidence["record"] is not None) or computed_root is not None
        steps.append({"key": key, "title": title, "detail": detail,
                      "state": ("pass" if getattr(result, key) else "fail") if reached else "skipped"})
    public = {"result": result.to_dict(), "steps": steps, "artifact_name": Path(path).name,
              "actual_hash": evidence["actual_hash"], "expected_hash": evidence.get("expected_hash"),
              "record": evidence["record"], "computed_root": computed_root,
              "manifest": bundle.get("manifest") if bundle else None}
    public["comparison"] = compare_artifacts(baseline, path) if baseline else None
    return public


def manifest_proof(bundle, record, index):
    leaves = leaves_from_manifest(bundle["manifest"])
    tree = build_tree(leaves)
    proof = generate_proof(tree, index)
    return {"entries": entries_from_manifest(bundle["manifest"]), "index": index,
            "leaf": leaves[index], "siblings": proof, "root": record["merkle_root"],
            "valid": verify_proof(leaves[index], proof, record["merkle_root"])}


class OverlayStorage:
    """Deliberately corrupted response for the labeled teaching simulation only."""
    def __init__(self, bundle):
        self.bundle = copy.deepcopy(bundle)

    def fetch_bundle(self, cid):
        return copy.deepcopy(self.bundle)
