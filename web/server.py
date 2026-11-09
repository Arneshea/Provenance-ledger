"""Local-only dashboard. Start with python -m web.server, then visit port 8000."""
import argparse
import base64
import json
import re
import shutil
import tempfile
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from build.hash_utils import hash_file, validate_hash
from contracts.registry_client import RegistryClient
from ipfs.ipfs_client import IPFSClient
from sign.signatures import sign_root
from eth_account import Account
from verify.config import ROOT, ARTIFACT_FOLDER, KEYS_FOLDER
from verify.pipeline import register_build, register_artifact
from web.inspection import MAX_SIZE, OverlayStorage, inspect_artifact, manifest_proof

STATIC = Path(__file__).parent / "static"


def clients(sign=False):
    key = (KEYS_FOLDER / "pipeline.key").read_text().strip() if sign else None
    return RegistryClient(private_key=key), IPFSClient(), key


def local_artifact(digest):
    """Only server-owned artifacts with bytes matching the on-chain lookup hash."""
    validate_hash(digest)
    for path in ARTIFACT_FOLDER.glob("*"):
        if path.is_file() and not path.name.endswith(".manifest.json") and path.stat().st_size <= MAX_SIZE and hash_file(path) == digest:
            return path
    return None


def builds(registry):
    logs = registry.contract.events.BuildRegistered().get_logs(from_block=0, to_block="latest")
    rows = []
    for log in reversed(logs):
        args = log["args"]
        digest = bytes(args["artifactHash"]).hex()
        path = local_artifact(digest)
        rows.append({"hash": digest, "merkle_root": bytes(args["merkleRoot"]).hex(),
                     "cid": args["cid"], "pipeline": args["pipeline"], "timestamp": args["timestamp"],
                     "transaction_hash": log["transactionHash"].hex(), "block": log["blockNumber"],
                     "name": path.name if path else digest[:12], "local": path is not None})
    return rows


def get_api(route, query):
    if route == "/api/status":
        state = {"chain": False, "ipfs": False, "errors": []}
        try:
            registry, _, _ = clients()
            state.update(chain=True, chain_id=registry.w3.eth.chain_id,
                         contract=registry.contract.address, block=registry.w3.eth.block_number)
        except Exception as error:
            state["errors"].append(str(error))
        try:
            state["ipfs_version"] = IPFSClient()._post("version").json()["Version"]
            state["ipfs"] = True
        except Exception as error:
            state["errors"].append(str(error))
        return state
    registry, storage, _ = clients()
    if route == "/api/builds":
        return {"builds": builds(registry)}
    if route == "/api/proof":
        digest = validate_hash(query.get("hash", [""])[0])
        record = registry.get_build(digest)
        if record is None:
            raise ValueError("Build not found")
        return manifest_proof(storage.fetch_bundle(record["cid"]), record, int(query.get("index", [0])[0]))
    raise ValueError("Unknown API route")


def post_api(route, data):
    registry, storage, key = clients(sign=route in ("/api/sample", "/api/register"))
    ARTIFACT_FOLDER.mkdir(exist_ok=True)
    if route == "/api/sample":
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "sample"
            shutil.copytree(ROOT / "examples/sample-app", source)
            (source / "build-id.txt").write_text(uuid.uuid4().hex)
            output = ARTIFACT_FOLDER / f"sample-{uuid.uuid4().hex[:10]}.zip"
            return register_build(source, output, "a" * 40, [], key, registry, storage)
    digest = data.get("expected_hash") or None
    baseline = local_artifact(digest) if digest else None
    if route == "/api/lab":
        if not baseline:
            raise ValueError("Select a registered build with a local original first")
        clean = inspect_artifact(baseline, registry, storage, digest, baseline)
        if not clean["result"]["passed"]:
            raise ValueError("Lab requires an original that passes verification")
        attack = data.get("attack")
        if attack in ("file", "append"):
            with tempfile.TemporaryDirectory() as temp:
                changed = Path(temp) / "tampered.zip"
                if attack == "append":
                    changed.write_bytes(baseline.read_bytes() + b"\nTAMPERED AFTER BUILD\n")
                else:
                    if not zipfile.is_zipfile(baseline):
                        raise ValueError("Choose a ZIP artifact for the change-a-file scenario")
                    with zipfile.ZipFile(baseline) as source:
                        from web.inspection import zip_inventory
                        inventory = zip_inventory(baseline)
                        if not inventory:
                            raise ValueError("Selected build has no ZIP members to change")
                        selected = next((r["name"] for r in inventory if r["name"].endswith(".py")), inventory[0]["name"])
                        with zipfile.ZipFile(changed, "w", zipfile.ZIP_DEFLATED) as target:
                            for info in source.infolist():
                                content = source.read(info)
                                if info.filename == selected:
                                    content += b"\n# Unauthorized change in transit\n"
                                target.writestr(info, content)
                report = inspect_artifact(changed, registry, storage, digest, baseline)
            report.update(attack=attack, simulation=False,
                          explanation="A temporary copy was changed after registration. The original artifact and ledger were preserved.")
            return report
        record = registry.get_build(digest)
        overlay = OverlayStorage(storage.fetch_bundle(record["cid"]))
        if attack == "manifest":
            overlay.bundle["manifest"]["commit_hash"] = "b" * 40
            explanation = "Simulated altered manifest response: rebuilding its Merkle tree yields a different root. Real IPFS retrieval would also reject changed bytes against the CID."
        elif attack == "signature":
            overlay.bundle["signature"] = sign_root(record["merkle_root"], Account.create().key)
            explanation = "Simulated forged signature response: the root is unchanged, but the recovered signer is not the on-chain pipeline. Real IPFS retrieval would also reject changed bundle bytes."
        else:
            raise ValueError("Unknown lab scenario")
        report = inspect_artifact(baseline, registry, overlay, digest, baseline)
        report.update(attack=attack, simulation=True, explanation=explanation)
        return report
    if route not in ("/api/verify", "/api/register"):
        raise ValueError("Unknown API route")
    with tempfile.TemporaryDirectory() as temp:
        if data.get("content") is not None:
            content = base64.b64decode(data["content"], validate=True)
            if not content or len(content) > MAX_SIZE:
                raise ValueError("Choose a nonempty artifact up to 12 MiB")
            name = str(data.get("name", "artifact.bin")).replace("\\", "/").split("/")[-1]
            if name in ("", ".", "..") or re.search(r'[<>:"|?*\x00-\x1f]', name):
                raise ValueError("Invalid filename")
            candidate = Path(temp) / name
            candidate.write_bytes(content)
        elif baseline and route == "/api/verify":
            candidate = baseline
        else:
            raise ValueError("Choose an artifact file")
        if route == "/api/verify":
            return inspect_artifact(candidate, registry, storage, digest, baseline)
        # Preserve original name for the manifest, use an isolated folder to avoid overwrites.
        result = register_artifact(candidate, data.get("commit", ""), data.get("dependencies", []), key, registry, storage)
        saved = ARTIFACT_FOLDER / f"upload-{uuid.uuid4().hex[:10]}-{candidate.name}"
        shutil.copyfile(candidate, saved)
        result["artifact"] = saved.name
        result.pop("manifest", None)  # Temporary staging path is intentionally not returned.
        return result


class Handler(BaseHTTPRequestHandler):
    def send_json(self, value, status=200):
        encoded = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def allowed(self):
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
            self.send_json({"error": "Local host required"}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{host}":
            self.send_json({"error": "Same-origin requests required"}, 403)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/api/"):
                self.send_json(get_api(parsed.path, parse_qs(parsed.query)))
                return
            file = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}.get(parsed.path)
            if file is None:
                self.send_json({"error": "Not found"}, 404)
                return
            body = (STATIC / file).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript", "style.css": "text/css"}[file])
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        except Exception as error:
            self.send_json({"error": str(error)}, 400)

    def do_POST(self):
        if not self.allowed():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.headers.get("Content-Type") != "application/json" or not 0 < length <= 17 * 1024 * 1024:
                raise ValueError("Send JSON with an artifact up to 12 MiB")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            self.send_json(post_api(urlparse(self.path).path, data))
        except Exception as error:
            self.send_json({"error": str(error)}, 400)


def main():
    parser = argparse.ArgumentParser(description="Local provenance dashboard")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Provenance dashboard: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
