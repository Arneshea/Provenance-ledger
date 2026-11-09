# Module interfaces

The source docstrings and `mds/API_SPEC.md` describe the module boundaries. Implemented entry points:

| Module | Functions/classes |
|---|---|
| `build.hash_utils` | `hash_file(path)`, `hash_bytes(bytes)`, `hash_string(text)`, `validate_hash(text)` |
| `build.build_artifact` | `create_artifact(source, output)`, `create_manifest(artifact, commit, dependencies, builder_id)`, `save_manifest(manifest, output)`, `normalize_manifest(manifest)`, `canonical_json(value)` |
| `merkle.merkle_tree` | `entries_from_manifest(manifest)`, `leaves_from_manifest(manifest)`, `build_tree(leaves)`, `get_root(tree)` |
| `merkle.merkle_proof` | `generate_proof(tree, index)`, `verify_proof(leaf, proof, root)` |
| `sign.signatures` | `generate_keys(folder)`, `sign_root(root, private_key)`, `verify_signature(root, signature, trusted_address)` |
| `ipfs.ipfs_client` | `IPFSClient(api_url).upload_bundle(manifest, signature, signer)`, `.fetch_bundle(cid)`; module-level default-client helpers also available |
| `contracts.registry_client` | `RegistryClient(rpc_url, deployment_file, private_key=None)`: `.register_build(hash, root, cid)`, `.get_build(hash)`, `.is_authorized(address)`; `deploy_registry`, `configure_pipeline`, `connect` |
| `verify.pipeline` | `register_build(source, artifact_path, commit_hash, dependencies, private_key, registry, storage)`, `verify_build(artifact_path, registry, storage, expected_hash=None)`, `tamper_demo(artifact_path, registry, storage)` |

`get_build` returns a dictionary of root/CID/pipeline/timestamp, or `None` for a missing record. Verification returns a `VerificationResult` dataclass with `passed`, `on_chain_found`, `pipeline_authorized`, `artifact_hash_ok`, `merkle_root_ok`, `signature_ok`, and `reason`. Call `.to_dict()` for JSON. Other bad inputs raise clear errors. Network failures have timeouts. The CLI formats errors as JSON and exits with 1.

Explicit registry/storage dependencies in the flow functions keep them testable without embedding service setup or CLI behavior. No service substitution exists in production configuration.

## Local dashboard API

Run `python -m web.server` to serve the allowlisted files in `web/static` and these JSON endpoints on `127.0.0.1:8000`:

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | Chain, deployed contract, and IPFS availability |
| `GET /api/builds` | Contract registration events with hash-validated local-original availability |
| `GET /api/proof?hash=...&index=...` | Selected manifest leaf, siblings, trusted root, and inclusion result |
| `POST /api/sample` | Register a fresh sample using the authorized local pipeline |
| `POST /api/register` | Register uploaded artifact bytes with commit/dependency metadata |
| `POST /api/verify` | Verify uploaded bytes or a locally available approved original |
| `POST /api/lab` | Run a controlled file/append attack or labeled manifest/signature simulation |

Uploads use JSON `{name, content}` where `content` is base64 (maximum 12 MiB decoded). Verification accepts an optional `expected_hash`. Registration requires `commit` and accepts `dependencies`. Lab requests require `expected_hash` and `attack` (`file`, `append`, `manifest`, `signature`). Errors return HTTP 400 with `error`; a completed but blocked verification returns HTTP 200 with `result.passed=false`. Host and Origin must match the local server. Private keys and arbitrary filesystem paths are not accepted or returned.

`verify.pipeline.register_artifact` registers an existing file without repacking. `web.inspection.inspect_artifact` records evidence while calling the same `verify_build` gate; ZIP comparison is additional explanatory evidence, not a substitute for authentication. `OverlayStorage` exists only for the explicitly selected lab simulations.
