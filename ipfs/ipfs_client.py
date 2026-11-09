"""Use Kubo's add/cat API; recompute the CID of returned bytes before trusting them."""
import json
import requests
from build.build_artifact import canonical_json, normalize_manifest
from merkle.merkle_tree import build_tree, get_root, leaves_from_manifest
from verify.config import IPFS_API_URL

MAX_BUNDLE_SIZE = 2 * 1024 * 1024


def make_bundle(manifest, signature, signer) -> dict:
    manifest = normalize_manifest(manifest)
    return {"manifest": manifest,
            "merkle_root": get_root(build_tree(leaves_from_manifest(manifest))),
            "signature": signature, "signer": signer}


class IPFSClient:
    def __init__(self, api_url=IPFS_API_URL):
        self.api_url = api_url.rstrip("/")

    def _post(self, method, **kwargs):
        try:
            response = requests.post(f"{self.api_url}/api/v0/{method}", timeout=30, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            raise RuntimeError(f"IPFS {method} failed; check the local Kubo node: {error}") from error

    def _add(self, data, only_hash=False):
        if len(data) > MAX_BUNDLE_SIZE:
            raise ValueError("Bundle exceeds 2 MiB limit")
        response = self._post("add", params={"pin": "true", "cid-version": "1",
                              "raw-leaves": "true", "chunker": "size-262144",
                              "only-hash": str(only_hash).lower()},
                              files={"file": ("bundle.json", data, "application/json")})
        return response.json()["Hash"]

    def upload_bundle(self, manifest, signature, signer):
        return self._add(canonical_json(make_bundle(manifest, signature, signer)))

    def fetch_bundle(self, cid):
        # Bounded streaming avoids loading an arbitrary gateway response into memory.
        with self._post("cat", params={"arg": cid}, stream=True) as response:
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BUNDLE_SIZE:
                    raise ValueError("Bundle exceeds 2 MiB limit")
                chunks.append(chunk)
        data = b"".join(chunks)
        if self._add(data, only_hash=True) != cid:
            raise ValueError("IPFS response content does not match the registered CID")
        bundle = json.loads(data)
        if not isinstance(bundle, dict) or set(bundle) != {"manifest", "merkle_root", "signature", "signer"}:
            raise ValueError("Malformed signed bundle")
        return bundle


def upload_bundle(manifest, signature, signer):
    return IPFSClient().upload_bundle(manifest, signature, signer)


def fetch_bundle(cid):
    return IPFSClient().fetch_bundle(cid)
