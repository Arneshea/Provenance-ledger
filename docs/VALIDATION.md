# Validation performed

Validated on 9 November 2026 using Windows, Python 3.12.13, Node 24.15.0, Solidity 0.8.24, Ganache 7.9.2 (chain 1337), and Kubo 0.32.1 in offline mode. Kubo's archive was checked against the official release SHA-512 checksum.

`npm run compile` succeeded. `LEDGER_INTEGRATION=1 .venv/Scripts/python.exe -m pytest -q` (set the environment variable with PowerShell syntax in README) passed **28 tests**, including the real-node integration test. A third-party `websockets.legacy` deprecation warning does not affect this HTTP-only project.

The documented CLI setup and `scripts/demo.ps1` were executed successfully. A clean registered build passed every check. Appending bytes to a separate copy produced `artifact_hash_ok: false`, while the registered manifest's Merkle root and signature still passed. Standalone verification of the modified artifact returned exit code 1 because its new hash had no record. A Merkle inclusion proof for leaf 4 verified against the registered root.

Example run (specific to the persisted local workspace):

| Item | Value |
|---|---|
| Artifact | `artifacts/demo-20261109-155044-684.zip` |
| Artifact SHA-256 | `0982b3c2f8a020d9fb47a4b9f8d5b776994832a48ff3f24a665cea03b9c1f53f` |
| Merkle root | `2ed52bb827ca712667e22cc04ca5ac2acaa7685f033ab6e32ce7635d28ce1010` |
| CID | `bafkreid5itdmaem2qxnlqnvzqyzb4ydkiu4sfrilsqvzwnxn34tqnbug5i` |

Generated keys, service databases, deployment metadata, and example artifacts are ignored by Git. They exist locally for the demo. A clean checkout needs the one-time setup in README. Never publish the generated private key.

## Visual dashboard addition

The extended suite passes **35 tests**, including real dashboard API registration, uploaded-byte preservation, all four attack scenarios, changed-member/text-diff detection, Merkle inclusion proofs, and local HTTP boundary checks. The browser flow was checked with an actual file chooser upload: a registered ZIP passed all five checks. The controlled file-change scenario blocked deployment, identified `app.py` as modified, and displayed its added line. The Merkle explorer displayed a valid sibling path to the recorded root. Desktop and narrow responsive layouts were inspected.

The dashboard is local-only at port 8000 and uses the existing Python dependency set; it requires no frontend framework or build step. Manifest/signature lab scenarios are explicitly labeled simulations, while artifact attacks modify real temporary copies. No original artifact or existing chain record is altered by an attack.
