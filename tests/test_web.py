import base64
import json
import threading
import zipfile
from http.server import HTTPServer
import pytest
import requests
from eth_account import Account
from build.hash_utils import hash_file
from verify.pipeline import register_build
from web.inspection import compare_artifacts, inspect_artifact, manifest_proof, OverlayStorage
from web.server import Handler
from test_core import MemoryRegistry, MemoryStorage


@pytest.fixture
def web_build(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('hello')")
    account = Account.create()
    registry, storage = MemoryRegistry(account.address), MemoryStorage()
    result = register_build(source, tmp_path / "app.zip", "a" * 40, [], account.key, registry, storage)
    return result, registry, storage


def test_explanation_uses_production_checks(web_build):
    build, registry, storage = web_build
    report = inspect_artifact(build["artifact"], registry, storage, build["artifact_hash"], build["artifact"])
    assert report["result"]["passed"]
    assert all(step["state"] == "pass" for step in report["steps"])
    assert report["comparison"]["first_changed_byte"] is None
    assert report["computed_root"] == build["merkle_root"]


def test_zip_member_change_vs_container_change(web_build, tmp_path):
    build, registry, storage = web_build
    original = build["artifact"]
    modified = tmp_path / "changed.zip"
    with zipfile.ZipFile(modified, "w") as archive:
        archive.writestr("app.py", "unauthorized code")
        archive.writestr("extra.txt", "added")
    report = inspect_artifact(modified, registry, storage, build["artifact_hash"], original)
    assert not report["result"]["passed"]
    assert {row["name"]: row["status"] for row in report["comparison"]["files"]} == {"app.py": "modified", "extra.txt": "added"}
    assert report["steps"][2]["state"] == "fail"
    assert report["steps"][3]["state"] == "pass"
    assert "unauthorized code" in report["comparison"]["files"][0]["diff"]
    modified.write_bytes(open(original, "rb").read() + b"hidden bytes")
    comparison = compare_artifacts(original, modified)
    assert all(row["status"] == "unchanged" for row in comparison["files"])
    assert "container bytes changed" in comparison["note"]


def test_missing_record_skips_later_checks(web_build, tmp_path):
    _, registry, storage = web_build
    path = tmp_path / "unknown.bin"
    path.write_bytes(b"unregistered")
    report = inspect_artifact(path, registry, storage)
    assert report["steps"][0]["state"] == "fail"
    assert all(step["state"] == "skipped" for step in report["steps"][1:])


def test_simulated_manifest_and_proof(web_build):
    build, registry, storage = web_build
    proof = manifest_proof(storage.bundle, registry.get_build(build["artifact_hash"]), 4)
    assert proof["valid"]
    overlay = OverlayStorage(storage.bundle)
    overlay.bundle["manifest"]["commit_hash"] = "b" * 40
    report = inspect_artifact(build["artifact"], registry, overlay, build["artifact_hash"])
    assert report["steps"][3]["state"] == "fail"
    assert storage.bundle["manifest"]["commit_hash"] == "a" * 40


def test_comparison_does_not_extract_zip_paths(tmp_path):
    original, candidate = tmp_path / "a.zip", tmp_path / "b.zip"
    for path in (original, candidate):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../../escape.txt", "content")
    assert compare_artifacts(original, candidate)["files"][0]["status"] == "unchanged"
    assert not (tmp_path.parent / "escape.txt").exists()


def test_http_only_serves_static_allowlist_and_rejects_foreign_origin():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert requests.get(url, timeout=5).status_code == 200
        assert requests.get(url + "/keys/pipeline.key", timeout=5).status_code == 404
        assert requests.get(url, headers={"Host": "attacker.example"}, timeout=5).status_code == 403
        assert requests.post(url + "/api/sample", json={}, headers={"Origin": "https://attacker.example"}, timeout=5).status_code == 403
        assert requests.post(url + "/api/verify", data="form", timeout=5).status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
