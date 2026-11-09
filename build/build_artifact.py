"""Create a deterministic ZIP and a strictly defined manifest."""
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from build.hash_utils import hash_file, validate_hash

FIELDS = ("version", "artifact_name", "artifact_hash", "commit_hash",
          "dependencies", "timestamp", "builder_id")


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def normalize_manifest(manifest: dict) -> dict:
    if not isinstance(manifest, dict) or set(manifest) != set(FIELDS):
        raise ValueError("Manifest must contain exactly the seven documented fields")
    for field in FIELDS:
        if field != "dependencies" and (not isinstance(manifest[field], str) or not manifest[field]):
            raise ValueError(f"Manifest {field} must be a nonempty string")
    if manifest["version"] != "1.0":
        raise ValueError("Unsupported manifest version")
    validate_hash(manifest["artifact_hash"])
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", manifest["commit_hash"]):
        raise ValueError("commit_hash must be a full lowercase Git SHA-1 or SHA-256")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest["timestamp"]):
        raise ValueError("timestamp must use YYYY-MM-DDTHH:MM:SSZ")
    datetime.strptime(manifest["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
    deps = manifest["dependencies"]
    if not isinstance(deps, list):
        raise ValueError("dependencies must be a list")
    normalized = []
    names = set()
    for dep in deps:
        if not isinstance(dep, dict) or set(dep) != {"name", "version", "hash"}:
            raise ValueError("Each dependency needs name, version and hash")
        if any(not isinstance(dep[k], str) or not dep[k] for k in dep):
            raise ValueError("Dependency values must be nonempty strings")
        if dep["name"] in names:
            raise ValueError("Duplicate dependency name")
        names.add(dep["name"])
        validate_hash(dep["hash"])
        normalized.append({k: dep[k] for k in ("name", "version", "hash")})
    result = {k: manifest[k] for k in FIELDS}
    result["dependencies"] = sorted(normalized, key=lambda d: d["name"])
    return result


def create_artifact(source_folder, output_path) -> Path:
    source, output = Path(source_folder).resolve(), Path(output_path).resolve()
    if not source.is_dir():
        raise ValueError(f"Source folder does not exist: {source}")
    if output.is_relative_to(source):
        raise ValueError("Write the artifact outside the source folder")
    files = sorted(source.rglob("*"))
    if any(p.is_symlink() for p in files):
        raise ValueError("Source must not contain symbolic links")
    files = [p for p in files if p.is_file()]
    if not files:
        raise ValueError("Source folder is empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            # Fixed metadata makes unchanged source bytes produce the same archive.
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return output


def create_manifest(artifact_path, commit_hash, dependencies, builder_id) -> dict:
    return normalize_manifest({
        "version": "1.0", "artifact_name": Path(artifact_path).name,
        "artifact_hash": hash_file(artifact_path), "commit_hash": commit_hash,
        "dependencies": dependencies,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder_id": builder_id,
    })


def save_manifest(manifest, output_path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(normalize_manifest(manifest)))
    return path
