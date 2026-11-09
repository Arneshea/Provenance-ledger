"""Opt in: LEDGER_INTEGRATION=1 python -m pytest -m integration -v"""
import json
import os
from pathlib import Path
import pytest
from eth_account import Account
from build.hash_utils import hash_file, hash_string
from contracts.registry_client import RegistryClient, checked_receipt, configure_pipeline, deploy_registry
from ipfs.ipfs_client import IPFSClient
from verify.config import RPC_URL, IPFS_API_URL
from verify.pipeline import register_build, verify_build, tamper_demo

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.getenv("LEDGER_INTEGRATION") != "1", reason="Requires local nodes")]


def test_real_contract_and_ipfs(tmp_path):
    deployment_file = tmp_path / "deployment.json"
    deployed = deploy_registry(RPC_URL, deployment_file)
    pipeline = Account.create()
    client = RegistryClient(RPC_URL, deployment_file, pipeline.key)
    storage = IPFSClient(IPFS_API_URL)
    w3, contract = client.w3, client.contract
    owner, outsider = w3.eth.accounts[:2]
    assert contract.functions.owner().call() == owner
    assert client.get_build("a" * 64) is None
    with pytest.raises(Exception, match="Only owner"):
        contract.functions.addPipeline(pipeline.address).transact({"from": outsider})
    configure_pipeline(client, pipeline.address, fund=True)
    assert client.is_authorized(pipeline.address)
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.txt").write_text("Integration build")
    registered = register_build(source, tmp_path / "app.zip", "a" * 40, [], pipeline.key, client, storage)
    assert verify_build(registered["artifact"], client, storage).passed
    record = client.get_build(registered["artifact_hash"])
    assert record["pipeline"] == pipeline.address
    bundle = storage.fetch_bundle(record["cid"])
    assert storage.upload_bundle(bundle["manifest"], bundle["signature"], bundle["signer"]) == record["cid"]
    altered = dict(bundle["manifest"], commit_hash="b" * 40)
    assert storage.upload_bundle(altered, bundle["signature"], bundle["signer"]) != record["cid"]
    tx = w3.eth.get_transaction_receipt(registered["transaction_hash"])
    events = contract.events.BuildRegistered().process_receipt(tx)
    assert events[0]["args"]["pipeline"] == pipeline.address
    assert len(events) == 1
    assert not tamper_demo(registered["artifact"], client, storage)["tampered"]["passed"]
    digest, root = bytes.fromhex(registered["artifact_hash"]), bytes.fromhex(registered["merkle_root"])
    with pytest.raises(Exception, match="Unauthorized pipeline"):
        contract.functions.registerBuild(b"b" * 32, root, "cid").transact({"from": outsider})
    with pytest.raises(Exception, match="already registered"):
        client.register_build(registered["artifact_hash"], registered["merkle_root"], registered["cid"])
    for bad_hash, bad_root, cid in [(bytes(32), root, "cid"), (b"c" * 32, bytes(32), "cid"),
                                    (b"c" * 32, root, "")]:
        # eth_call executes the same require checks without needing an unlocked pipeline.
        with pytest.raises(Exception, match="Zero hash or root|Invalid CID length"):
            contract.functions.registerBuild(bad_hash, bad_root, cid).call({"from": pipeline.address})
    configure_pipeline(client, pipeline.address, remove=True)
    assert not client.is_authorized(pipeline.address)
    assert not verify_build(registered["artifact"], client, storage).passed
    assert client.get_build(registered["artifact_hash"]) == record
    with pytest.raises(Exception, match="Unauthorized pipeline"):
        client.register_build("c" * 64, registered["merkle_root"], registered["cid"])


def test_dashboard_real_flows():
    """Exercise the same API actions used by the browser against both real nodes."""
    from web.server import post_api, get_api
    import base64
    import uuid
    from build.hash_utils import hash_bytes
    from web.server import local_artifact
    build = post_api("/api/sample", {})
    digest = build["artifact_hash"]
    clean = post_api("/api/verify", {"expected_hash": digest})
    assert clean["result"]["passed"]
    for attack, failed in [("file", "artifact_hash_ok"), ("append", "artifact_hash_ok"),
                           ("manifest", "merkle_root_ok"), ("signature", "signature_ok")]:
        report = post_api("/api/lab", {"expected_hash": digest, "attack": attack})
        assert not report["result"]["passed"]
        assert not report["result"][failed]
        assert report["simulation"] == (attack in ("manifest", "signature"))
        if attack == "file":
            assert any(row["status"] == "modified" for row in report["comparison"]["files"])
    assert post_api("/api/verify", {"expected_hash": digest})["result"]["passed"]
    assert get_api("/api/proof", {"hash": [digest], "index": ["4"]})["valid"]
    assert any(row["hash"] == digest for row in get_api("/api/builds", {})["builds"])
    # Uploaded JSON also remains available as an original, despite its .json extension.
    content = json.dumps({"build": uuid.uuid4().hex}).encode()
    uploaded = post_api("/api/register", {"name": "release.json", "content": base64.b64encode(content).decode(),
                                         "commit": "c" * 40, "dependencies": []})
    assert uploaded["artifact_hash"] == hash_bytes(content)
    assert local_artifact(uploaded["artifact_hash"]).read_bytes() == content
    assert post_api("/api/verify", {"name": "release.json", "content": base64.b64encode(content).decode(),
                                   "expected_hash": uploaded["artifact_hash"]})["result"]["passed"]
